#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Skill 許願池 / Skill Wishpool — 單檔後端。

只用 Python 3 標準函式庫,零外部依賴、零 npm、零 Docker。

    python3 server.py                     # 127.0.0.1:8787,DB 在 ./data/wishes.db
    python3 server.py --seed              # DB 空的時候載入 data/seed.json 範例願望
    python3 server.py --host 0.0.0.0 --port 8787 --db /var/lib/skill-wishpool/wishes.db

環境變數
    WISHPOOL_ADMIN_TOKEN            設了才開放 /api/admin/*;沒設一律回 503(fail-closed)
    WISHPOOL_READONLY=1             唯讀模式:所有寫入 API 回 403(適合做公開展示站)
    WISHPOOL_ALLOW_ORIGIN           設了才發 CORS 標頭;預設同源,不發
    WISHPOOL_SALT_FILE              IP 雜湊用的鹽檔(預設 <db 同層>/ip_salt)
    WISHPOOL_TRUST_PROXY=1          相信 X-Forwarded-For 第一個位址(**只有**放在自己的
                                    反向代理後面才可以開,否則速率限制可被輕易繞過)

隱私:資料庫裡不存原始 IP,只存 sha256(salt + ip) 的前 32 個 hex,用來做速率限制與
投票去重。鹽檔不進版控,換掉鹽就等於把舊的關聯全部斷掉。
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import hmac
import json
import os
import re
import secrets
import sqlite3
import sys
import time
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

VERSION = "1.0.0"
ROOT = os.path.dirname(os.path.abspath(__file__))
PUBLIC_DIR = os.path.join(ROOT, "public")

# ── 輸入限制 ─────────────────────────────────────────────────────────────
# 這些是硬上限,不是建議值。改小可以,改大之前先想清楚:願望是公開顯示的,
# 越長的欄位越容易被拿來塞廣告。
TITLE_MIN_LEN = 4
TITLE_MAX_LEN = 120
TITLE_MIN_NORM_LEN = 2  # 去掉標點與空白後至少要剩兩個字,否則看不出在許什麼願
DETAIL_MAX_LEN = 2000
AUTHOR_MAX_LEN = 40
TAG_MAX_LEN = 20
TAG_MAX_COUNT = 5
DETAIL_MAX_URLS = 3
BODY_MAX_BYTES = 64 * 1024

# ── 速率限制(每個 ip_hash)─────────────────────────────────────────────
# 這是唯一真正擋得住洗版的機制。前端的蜜罐欄位只是嚇阻,不要當成防護。
# 可以用 WISHPOOL_RATE_* 環境變數調整,預設值就是下面這組。
def _env_int(name: str, default: int) -> int:
    raw = os.environ.get(name, "")
    return int(raw) if raw.isdigit() and int(raw) > 0 else default


RATE_WISH_MAX = _env_int("WISHPOOL_RATE_WISH_MAX", 5)
RATE_WISH_WINDOW = _env_int("WISHPOOL_RATE_WISH_WINDOW", 3600)
RATE_VOTE_MAX = _env_int("WISHPOOL_RATE_VOTE_MAX", 60)
RATE_VOTE_WINDOW = _env_int("WISHPOOL_RATE_VOTE_WINDOW", 3600)

STATUSES = ("open", "planned", "granted", "declined", "hidden")
PUBLIC_STATUSES = ("open", "planned", "granted", "declined")
SORTS = ("hot", "new", "top")

# ── 聯署輪次 ─────────────────────────────────────────────────────────────
# 每 CYCLE_DAYS 天結算一次:票最高的願望出線,狀態轉成 planned(有人接了),
# 讓它離開候選池,下一輪換第二名上。票數不歸零,沒選上的願望票會繼續累積。
CYCLE_DAYS_DEFAULT = 3
MIN_VOTES_DEFAULT = 1
SETTLE_MAX = 10  # 一次請求最多補結算幾輪(伺服器停很久才會用到)

SCHEMA = """
CREATE TABLE IF NOT EXISTS wishes (
  id          INTEGER PRIMARY KEY AUTOINCREMENT,
  title       TEXT NOT NULL,
  norm_title  TEXT NOT NULL UNIQUE,
  detail      TEXT NOT NULL DEFAULT '',
  tags        TEXT NOT NULL DEFAULT '',
  author      TEXT NOT NULL DEFAULT '',
  status      TEXT NOT NULL DEFAULT 'open',
  votes       INTEGER NOT NULL DEFAULT 0,
  skill_url   TEXT NOT NULL DEFAULT '',
  note        TEXT NOT NULL DEFAULT '',
  created_at  TEXT NOT NULL,
  updated_at  TEXT NOT NULL,
  ip_hash     TEXT NOT NULL DEFAULT ''
);
CREATE TABLE IF NOT EXISTS votes (
  wish_id  INTEGER NOT NULL REFERENCES wishes(id) ON DELETE CASCADE,
  ip_hash  TEXT NOT NULL,
  ts       INTEGER NOT NULL,
  PRIMARY KEY (wish_id, ip_hash)
);
CREATE TABLE IF NOT EXISTS events (
  ip_hash TEXT NOT NULL,
  kind    TEXT NOT NULL,
  ts      INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS meta (
  key   TEXT PRIMARY KEY,
  value TEXT NOT NULL
);
-- 聯署輪次:每 WISHPOOL_CYCLE_DAYS 天結算一次,票最高的願望出線。
-- 只有「已結算」的輪次才會有 row;進行中的那一輪是用 anchor 算出來的,
-- 所以不需要背景排程,任何一個請求進來都能把過期的輪次補結算掉。
CREATE TABLE IF NOT EXISTS rounds (
  idx           INTEGER PRIMARY KEY,
  started_at    INTEGER NOT NULL,
  ends_at       INTEGER NOT NULL,
  closed_at     INTEGER NOT NULL,
  winner_id     INTEGER,
  winner_votes  INTEGER NOT NULL DEFAULT 0,
  note          TEXT NOT NULL DEFAULT ''
);
CREATE INDEX IF NOT EXISTS idx_events_lookup ON events(ip_hash, kind, ts);
CREATE INDEX IF NOT EXISTS idx_wishes_status ON wishes(status);
"""

# 全域執行期設定,由 main() 填。
CFG = {
    "db": os.path.join(ROOT, "data", "wishes.db"),
    "salt": b"",
    "readonly": False,
    "admin_token": "",
    "allow_origin": "",
    "trust_proxy": False,
    "quiet": False,
    "cycle_days": CYCLE_DAYS_DEFAULT,
    "cycle_seconds": CYCLE_DAYS_DEFAULT * 86400,
    "min_votes": MIN_VOTES_DEFAULT,
    "csp_mode": "hash",     # hash | unsafe-inline | off
}


# ── 小工具 ───────────────────────────────────────────────────────────────

def now_sql() -> str:
    """SQL 友善的 UTC 時間字串;julianday() 讀得懂,排序也正確。"""
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


def to_iso(sql_ts: str) -> str:
    return (sql_ts or "").replace(" ", "T") + "Z"


def load_salt(path: str) -> bytes:
    """讀取或建立 IP 雜湊鹽。鹽檔不進版控,遺失只影響去重,不影響願望內容。"""
    try:
        with open(path, "rb") as fh:
            salt = fh.read().strip()
        if len(salt) >= 16:
            return salt
    except OSError:
        pass
    salt = secrets.token_hex(32).encode("ascii")
    os.makedirs(os.path.dirname(os.path.abspath(path)) or ".", exist_ok=True)
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "wb") as fh:
        fh.write(salt)
    return salt


def hash_ip(ip: str) -> str:
    return hashlib.sha256(CFG["salt"] + b"|" + ip.encode("utf-8", "replace")).hexdigest()[:32]


def connect() -> sqlite3.Connection:
    conn = sqlite3.connect(CFG["db"], timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=8000")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def init_db() -> None:
    os.makedirs(os.path.dirname(os.path.abspath(CFG["db"])) or ".", exist_ok=True)
    with connect() as conn:
        conn.executescript(SCHEMA)


# ── 文字清理與驗證 ───────────────────────────────────────────────────────

# 零寬字元與雙向覆寫字元:拿來假造標題、藏連結用的,一律移除。
_INVISIBLE = re.compile("[​-‏‪-‮⁦-⁩﻿]")
# 控制字元(保留 \n \t)
_CONTROL = re.compile("[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
_WS_RUN = re.compile(r"[ \t　]{2,}")
_NL_RUN = re.compile(r"\n{3,}")
_URLISH = re.compile(r"https?://", re.I)
_NORM_STRIP = re.compile(
    r"[\s　\-_—–·.。,,、!!??::;;()()\[\]【】「」『』〈〉《》\"'`~～/\\|+*#&]+"
)


def clean_text(raw, limit: int, allow_newlines: bool = False) -> str:
    if raw is None:
        return ""
    if not isinstance(raw, str):
        raw = str(raw)
    raw = _INVISIBLE.sub("", raw.replace("\r\n", "\n").replace("\r", "\n"))
    raw = _CONTROL.sub("", raw)
    if not allow_newlines:
        raw = raw.replace("\n", " ")
    raw = _WS_RUN.sub(" ", raw)
    raw = _NL_RUN.sub("\n\n", raw)
    return raw.strip()[:limit]


def normalize_title(title: str) -> str:
    """給重複偵測用的正規化:去標點空白 + casefold。中文沒有空格,所以連空白一起去。"""
    return _NORM_STRIP.sub("", title).casefold()


def parse_tags(raw) -> list:
    if isinstance(raw, str):
        items = re.split(r"[,,\s、|]+", raw)
    elif isinstance(raw, (list, tuple)):
        items = [str(x) for x in raw]
    else:
        items = []
    out = []
    for item in items:
        tag = clean_text(item, TAG_MAX_LEN).lower().lstrip("#")
        if tag and tag not in out:
            out.append(tag)
        if len(out) >= TAG_MAX_COUNT:
            break
    return out


class Invalid(Exception):
    """使用者輸入不合格。message 會直接顯示給許願的人,所以要寫成人話。"""

    def __init__(self, message: str, code: str = "invalid", field: str = ""):
        super().__init__(message)
        self.message = message
        self.code = code
        self.field = field


def validate_wish(payload: dict) -> dict:
    if not isinstance(payload, dict):
        raise Invalid("送出的內容不是合法的 JSON 物件。", "bad_body")

    # 蜜罐:真人看不到這個欄位,填了就是機器人。只是嚇阻,真正的防線是速率限制。
    if clean_text(payload.get("hp"), 200):
        raise Invalid("願望被擋下來了。如果你是真人,請重新整理再試一次。", "rejected")

    title = clean_text(payload.get("title"), TITLE_MAX_LEN + 1)
    if not title:
        raise Invalid("要許什麼願?標題不能空白。", "empty_title", "title")
    if len(title) < TITLE_MIN_LEN:
        raise Invalid(f"標題太短了,至少 {TITLE_MIN_LEN} 個字。", "short_title", "title")
    if len(title) > TITLE_MAX_LEN:
        raise Invalid(f"標題最多 {TITLE_MAX_LEN} 個字,細節寫在下面的說明就好。",
                      "long_title", "title")
    norm = normalize_title(title)
    if len(norm) < TITLE_MIN_NORM_LEN:
        raise Invalid("標題看不出在許什麼願,請用文字描述。", "weak_title", "title")

    detail = clean_text(payload.get("detail"), DETAIL_MAX_LEN + 1, allow_newlines=True)
    if len(detail) > DETAIL_MAX_LEN:
        raise Invalid(f"說明最多 {DETAIL_MAX_LEN} 個字。", "long_detail", "detail")
    if len(_URLISH.findall(detail)) > DETAIL_MAX_URLS:
        raise Invalid(f"說明裡的連結太多了(最多 {DETAIL_MAX_URLS} 個)。",
                      "too_many_links", "detail")

    author = clean_text(payload.get("author"), AUTHOR_MAX_LEN)
    if _URLISH.search(author):
        raise Invalid("暱稱裡不要放連結。", "author_link", "author")

    return {
        "title": title,
        "norm_title": norm,
        "detail": detail,
        "tags": ",".join(parse_tags(payload.get("tags"))),
        "author": author,
    }


# ── 速率限制 ─────────────────────────────────────────────────────────────

def begin_write(conn) -> None:
    """在做「先查再寫」的檢查之前,先取得寫入鎖。

    速率限制本質上是 check-then-act:先數 events 再插入。不先鎖的話,同時打進來的
    N 個請求會**全部**讀到「還沒超過上限」然後全部通過 —— 唯一真正擋洗版的機制
    就這樣被平行請求繞過(實測:20 個並行請求在上限 5 的池子裡全部成功)。
    BEGIN IMMEDIATE 會立刻取得 RESERVED 鎖,把「查 + 寫」整段序列化。
    """
    conn.execute("BEGIN IMMEDIATE")


def rate_check(conn, ip_hash: str, kind: str, limit: int, window: int) -> None:
    cutoff = int(time.time()) - window
    used = conn.execute(
        "SELECT COUNT(*) FROM events WHERE ip_hash=? AND kind=? AND ts>?",
        (ip_hash, kind, cutoff),
    ).fetchone()[0]
    if used >= limit:
        mins = max(1, window // 60)
        raise Invalid(
            f"太快了。同一個來源每 {mins} 分鐘最多 {limit} 次({kind})。等一下再來。",
            "rate_limited",
        )


def rate_record(conn, ip_hash: str, kind: str) -> None:
    conn.execute("INSERT INTO events(ip_hash,kind,ts) VALUES(?,?,?)",
                 (ip_hash, kind, int(time.time())))
    # 順手清掉過期紀錄,免得 events 無限長大。
    conn.execute("DELETE FROM events WHERE ts < ?",
                 (int(time.time()) - max(RATE_WISH_WINDOW, RATE_VOTE_WINDOW) * 3,))


# ── 資料存取 ─────────────────────────────────────────────────────────────

def row_to_wish(row) -> dict:
    return {
        "id": row["id"],
        "title": row["title"],
        "detail": row["detail"],
        "tags": [t for t in row["tags"].split(",") if t],
        "author": row["author"],
        "status": row["status"],
        "votes": row["votes"],
        "skill_url": row["skill_url"],
        "note": row["note"],
        "created_at": to_iso(row["created_at"]),
        "updated_at": to_iso(row["updated_at"]),
    }


HOT_ORDER = (
    "(votes + 1.0) / ("
    "  ((julianday('now') - julianday(created_at)) * 24.0 + 2.0)"
    "* ((julianday('now') - julianday(created_at)) * 24.0 + 2.0)"
    ") DESC, id DESC"
)


def list_wishes(conn, q="", status="", tag="", sort="hot", limit=50, offset=0,
                include_hidden=False):
    where = []
    args = []
    if include_hidden:
        if status:
            where.append("status = ?")
            args.append(status)
    elif status and status in PUBLIC_STATUSES:
        where.append("status = ?")
        args.append(status)
    else:
        where.append("status IN (%s)" % ",".join("?" * len(PUBLIC_STATUSES)))
        args.extend(PUBLIC_STATUSES)

    if q:
        like = "%" + q.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"
        where.append("(title LIKE ? ESCAPE '\\' OR detail LIKE ? ESCAPE '\\' "
                     "OR tags LIKE ? ESCAPE '\\')")
        args.extend([like, like, like])
    if tag:
        where.append("(',' || tags || ',') LIKE ? ESCAPE '\\'")
        args.append("%," + tag.replace("\\", "\\\\").replace("%", "\\%")
                    .replace("_", "\\_") + ",%")

    clause = " WHERE " + " AND ".join(where) if where else ""
    total = conn.execute("SELECT COUNT(*) FROM wishes" + clause, args).fetchone()[0]
    order = {"new": "id DESC", "top": "votes DESC, id DESC"}.get(sort, HOT_ORDER)
    rows = conn.execute(
        "SELECT * FROM wishes" + clause + " ORDER BY " + order + " LIMIT ? OFFSET ?",
        args + [limit, offset],
    ).fetchall()
    return [row_to_wish(r) for r in rows], total


def tag_counts(conn, limit: int = 20):
    """全池的標籤統計 —— **不受目前的搜尋/標籤篩選影響**。

    前端的標籤列一定要用這份。用「篩選後的結果」重算的話,按下 #excel 之後
    標籤列就只剩 excel 的共現標籤,使用者沒辦法直接換另一個標籤(要先按「全部」)。
    這個 bug 實機測試時抓到過。
    """
    counter = {}
    rows = conn.execute(
        "SELECT tags FROM wishes WHERE tags <> '' AND status IN (%s)"
        % ",".join("?" * len(PUBLIC_STATUSES)), PUBLIC_STATUSES).fetchall()
    for row in rows:
        for tag in row["tags"].split(","):
            if tag:
                counter[tag] = counter.get(tag, 0) + 1
    ordered = sorted(counter.items(), key=lambda kv: (-kv[1], kv[0]))
    return [[tag, n] for tag, n in ordered[:limit]]


def stats(conn) -> dict:
    row = conn.execute(
        "SELECT COUNT(*) AS n, COALESCE(SUM(votes),0) AS v FROM wishes "
        "WHERE status IN (%s)" % ",".join("?" * len(PUBLIC_STATUSES)),
        PUBLIC_STATUSES,
    ).fetchone()
    granted = conn.execute(
        "SELECT COUNT(*) FROM wishes WHERE status IN ('granted','planned')"
    ).fetchone()[0]
    return {"wishes": row["n"], "votes": row["v"], "granted": granted}


def register_vote(conn, wish_id: int, ip_hash: str):
    """回傳 (票數, 是否本來就投過)。同一個 ip_hash 對同一個願望只算一票。"""
    cur = conn.execute(
        "INSERT OR IGNORE INTO votes(wish_id, ip_hash, ts) VALUES(?,?,?)",
        (wish_id, ip_hash, int(time.time())),
    )
    already = cur.rowcount == 0
    if not already:
        conn.execute(
            "UPDATE wishes SET votes = (SELECT COUNT(*) FROM votes WHERE wish_id=?), "
            "updated_at=? WHERE id=?",
            (wish_id, now_sql(), wish_id),
        )
    votes = conn.execute("SELECT votes FROM wishes WHERE id=?", (wish_id,)).fetchone()
    return (votes[0] if votes else 0), already


# ── 聯署輪次 ─────────────────────────────────────────────────────────────

def get_meta(conn, key, default=None):
    row = conn.execute("SELECT value FROM meta WHERE key=?", (key,)).fetchone()
    return row["value"] if row else default


def set_meta(conn, key, value):
    conn.execute("INSERT INTO meta(key,value) VALUES(?,?) "
                 "ON CONFLICT(key) DO UPDATE SET value=excluded.value", (key, str(value)))


def cycle_anchor(conn) -> int:
    """第一輪的起算時間。第一次被問到就釘住,之後所有輪次界線都由它推算。

    釘死在 DB 裡而不是每次用 now() 推算,是為了讓倒數計時穩定 —— 不然重啟一次
    伺服器,所有人的倒數就跳一次。
    """
    raw = get_meta(conn, "cycle_anchor")
    if raw and raw.isdigit():
        return int(raw)
    anchor = int(time.time())
    set_meta(conn, "cycle_anchor", anchor)
    return anchor


def round_bounds(anchor: int, idx: int):
    return anchor + idx * CFG["cycle_seconds"], anchor + (idx + 1) * CFG["cycle_seconds"]


def pick_winner(conn, before_ts: int):
    """某個時間點的第一名:只看 open 的願望、票數要達門檻,同票者先許願的贏。"""
    return conn.execute(
        "SELECT id, title, votes FROM wishes "
        "WHERE status='open' AND votes >= ? AND julianday(created_at) < julianday(?, 'unixepoch') "
        "ORDER BY votes DESC, id ASC LIMIT 1",
        (CFG["min_votes"], before_ts),
    ).fetchone()


def ensure_rounds(conn) -> None:
    """把所有已經過期、但還沒結算的輪次補結算掉。

    沒有 cron、沒有背景執行緒 —— 任何一個 API 請求進來都會順手做這件事。
    伺服器關機期間的輪次會補記成「沒有結算」,不會假裝當時有人得標。
    """
    if CFG["readonly"]:
        return
    now = int(time.time())
    anchor = cycle_anchor(conn)
    period = CFG["cycle_seconds"]
    current_idx = (now - anchor) // period
    last_done = conn.execute("SELECT COALESCE(MAX(idx), -1) FROM rounds").fetchone()[0]
    target = current_idx - 1  # 最後一個「已經整輪跑完」的輪次
    if target <= last_done:
        return
    pending = list(range(last_done + 1, target + 1))
    # 停機太久的話,只認真結算最近幾輪,更早的誠實記成沒結算。
    unsettled, settle = pending[:-SETTLE_MAX], pending[-SETTLE_MAX:]
    for idx in unsettled:
        started, ends = round_bounds(anchor, idx)
        try:
            conn.execute(
                "INSERT INTO rounds(idx,started_at,ends_at,closed_at,winner_id,"
                "winner_votes,note) VALUES(?,?,?,?,NULL,0,?)",
                (idx, started, ends, now, "這一輪沒有結算(池子當時沒開著)"))
        except sqlite3.IntegrityError:
            pass
    for idx in settle:
        started, ends = round_bounds(anchor, idx)
        winner = pick_winner(conn, ends)
        try:
            conn.execute(
                "INSERT INTO rounds(idx,started_at,ends_at,closed_at,winner_id,"
                "winner_votes,note) VALUES(?,?,?,?,?,?,?)",
                (idx, started, ends, now,
                 winner["id"] if winner else None,
                 winner["votes"] if winner else 0,
                 "" if winner else "這一輪沒有願望達到門檻"))
        except sqlite3.IntegrityError:
            continue  # 另一個執行緒剛好搶先結算了,不要重複記。
        if winner:
            conn.execute(
                "UPDATE wishes SET status='planned', updated_at=?, "
                "note = CASE WHEN note='' THEN ? ELSE note END WHERE id=? AND status='open'",
                (now_sql(), "第 %d 輪聯署第一名(%d 票)" % (idx + 1, winner["votes"]),
                 winner["id"]))


def round_payload(conn) -> dict:
    """進行中那一輪的狀態 + 已結算的歷屆結果。"""
    ensure_rounds(conn)
    now = int(time.time())
    anchor = cycle_anchor(conn)
    period = CFG["cycle_seconds"]
    idx = (now - anchor) // period
    started, ends = round_bounds(anchor, idx)
    leader = pick_winner(conn, ends)
    rows = conn.execute(
        "SELECT r.*, w.title, w.status, w.skill_url FROM rounds r "
        "LEFT JOIN wishes w ON w.id = r.winner_id ORDER BY r.idx DESC LIMIT 20"
    ).fetchall()
    return {
        "cycle_days": CFG["cycle_days"],
        "min_votes": CFG["min_votes"],
        "index": int(idx) + 1,          # 對外從 1 開始數,比較好講
        "started_at": to_iso(datetime.fromtimestamp(started, timezone.utc)
                             .strftime("%Y-%m-%d %H:%M:%S")),
        "ends_at": to_iso(datetime.fromtimestamp(ends, timezone.utc)
                          .strftime("%Y-%m-%d %H:%M:%S")),
        "seconds_left": max(0, ends - now),
        "leader": ({"id": leader["id"], "title": leader["title"],
                    "votes": leader["votes"]} if leader else None),
        "history": [{
            "index": r["idx"] + 1,
            "ends_at": to_iso(datetime.fromtimestamp(r["ends_at"], timezone.utc)
                              .strftime("%Y-%m-%d %H:%M:%S")),
            "winner_id": r["winner_id"],
            "title": r["title"] or "",
            "votes": r["winner_votes"],
            "status": r["status"] or "",
            "skill_url": r["skill_url"] or "",
            "note": r["note"],
        } for r in rows],
    }


# ── HTTP ─────────────────────────────────────────────────────────────────

STATIC_TYPES = {
    ".html": "text/html; charset=utf-8",
    ".css": "text/css; charset=utf-8",
    ".js": "text/javascript; charset=utf-8",
    ".json": "application/json; charset=utf-8",
    ".svg": "image/svg+xml",
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".webp": "image/webp",
    ".ico": "image/x-icon",
    ".txt": "text/plain; charset=utf-8",
    ".webmanifest": "application/manifest+json",
}

_INLINE_BLOCK = re.compile(rb"<(script|style)\b[^>]*>(.*?)</\1\s*>", re.S | re.I)
_csp_cache = {}


def csp_for_html(body: bytes) -> str:
    """用實際送出去的位元組算 inline 區塊的 sha256,所以雜湊永遠不會跟內容脫節。

    這樣單檔頁面也能拿到不含 'unsafe-inline' 的 CSP:注入進 DOM 的 <script>
    雜湊對不上就不會執行(實測有效:Cloudflare 的 Web Analytics beacon 被擋掉了)。

    ⚠️ 但這也是唯一一個「CDN 會弄壞你的網站」的地方:雜湊是對**我們送出的位元組**
    算的,如果前面的 CDN 改寫了 HTML(Cloudflare 的 Rocket Loader、Auto Minify
    之類),原本那段 inline script 的雜湊就對不上 → 整頁 JS 被擋 → 白畫面。
    遇到這種環境有兩個選擇:把 CDN 的改寫功能關掉(建議),或用
    WISHPOOL_CSP=unsafe-inline 退一步(CSP 變弱,但頁面不會死)。
    """
    mode = CFG.get("csp_mode", "hash")
    if mode == "off":
        return ""
    key = hashlib.sha256(body).hexdigest() + "|" + mode
    hit = _csp_cache.get(key)
    if hit:
        return hit
    scripts, styles = [], []
    if mode == "unsafe-inline":
        scripts, styles = ["'unsafe-inline'"], ["'unsafe-inline'"]
    for tag, inner in _INLINE_BLOCK.findall(body) if mode == "hash" else ():
        digest = "'sha256-%s'" % base64.b64encode(hashlib.sha256(inner).digest()).decode()
        (scripts if tag.lower() == b"script" else styles).append(digest)
    # 保險:HTML 裡明明有 <script 卻抓不到雜湊,就退回 'unsafe-inline',
    # 寧可 CSP 弱一點也不要讓頁面整片空白。
    if b"<script" in body.lower() and not scripts:
        scripts = ["'unsafe-inline'"]
        sys.stderr.write("[warn] 抓不到 inline script 雜湊,CSP 退回 unsafe-inline\n")
    if b"<style" in body.lower() and not styles:
        styles = ["'unsafe-inline'"]
    policy = "; ".join([
        "default-src 'none'",
        "base-uri 'none'",
        "form-action 'none'",
        "frame-ancestors 'none'",
        "img-src 'self' data:",
        "connect-src 'self'",
        "font-src 'self'",
        "style-src " + (" ".join(styles) or "'none'"),
        "script-src " + (" ".join(scripts) or "'none'"),
    ])
    _csp_cache.clear()
    _csp_cache[key] = policy
    return policy


class Handler(BaseHTTPRequestHandler):
    server_version = "SkillWishpool/" + VERSION
    sys_version = ""
    protocol_version = "HTTP/1.1"

    # ── 基礎 ────────────────────────────────────────────────────────────
    def log_message(self, fmt, *args):  # noqa: A003
        """覆寫預設 log:預設會把原始 IP 寫進 stdout,這裡只寫雜湊前 8 碼。"""
        if CFG["quiet"]:
            return
        sys.stderr.write("%s [%s] %s\n" % (
            datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            hash_ip(self.real_ip())[:8], fmt % args))

    def real_ip(self) -> str:
        if CFG["trust_proxy"]:
            xff = self.headers.get("X-Forwarded-For", "")
            if xff:
                return xff.split(",")[0].strip()[:64]
        return self.client_address[0] if self.client_address else "0.0.0.0"

    def base_headers(self):
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("Permissions-Policy",
                         "geolocation=(), camera=(), microphone=(), payment=()")
        origin = CFG["allow_origin"]
        if origin:
            self.send_header("Access-Control-Allow-Origin", origin)
            self.send_header("Vary", "Origin")
            self.send_header("Access-Control-Allow-Headers", "Content-Type, X-Admin-Token")
            self.send_header("Access-Control-Allow-Methods", "GET, POST, DELETE, OPTIONS")

    def send_json(self, status: int, payload: dict):
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.base_headers()
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)

    def send_err(self, status: int, message: str, code: str = "error", field: str = ""):
        self.send_json(status, {"ok": False, "error": message, "code": code,
                                "field": field})

    def read_json(self) -> dict:
        try:
            length = int(self.headers.get("Content-Length") or 0)
        except ValueError:
            raise Invalid("Content-Length 不合法。", "bad_body")
        if length <= 0:
            raise Invalid("沒有收到內容。", "bad_body")
        if length > BODY_MAX_BYTES:
            raise Invalid("內容太大了。", "too_large")
        raw = self.rfile.read(length)
        try:
            return json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            raise Invalid("內容不是合法的 JSON。", "bad_body")

    def guard_write(self):
        if CFG["readonly"]:
            raise Invalid("這是唯讀展示站,不接受新的願望。", "readonly")

    def require_admin(self):
        token = CFG["admin_token"]
        if not token:
            raise Invalid("這台伺服器沒有設定 WISHPOOL_ADMIN_TOKEN,管理端已關閉。",
                          "admin_disabled")
        got = self.headers.get("X-Admin-Token", "")
        if not got or not hmac.compare_digest(got, token):
            raise Invalid("管理權杖不正確。", "unauthorized")

    # ── 路由 ────────────────────────────────────────────────────────────
    def do_OPTIONS(self):  # noqa: N802
        self.send_response(204)
        self.send_header("Content-Length", "0")
        self.base_headers()
        self.end_headers()

    def do_HEAD(self):  # noqa: N802
        self.route()

    def do_GET(self):  # noqa: N802
        self.route()

    def do_POST(self):  # noqa: N802
        self.route()

    def do_DELETE(self):  # noqa: N802
        self.route()

    def route(self):
        try:
            parsed = urlparse(self.path)
            path = parsed.path
            query = parse_qs(parsed.query)
            if path.startswith("/api/"):
                return self.api(path, query)
            if self.command in ("GET", "HEAD"):
                return self.static(path)
            return self.send_err(405, "這個路徑不支援這個方法。", "method_not_allowed")
        except Invalid as exc:
            status = {
                "rate_limited": 429, "readonly": 403, "unauthorized": 401,
                "admin_disabled": 503, "too_large": 413, "duplicate_hidden": 409,
            }.get(exc.code, 400)
            return self.send_err(status, exc.message, exc.code, exc.field)
        except BrokenPipeError:
            return
        except Exception as exc:  # noqa: BLE001
            sys.stderr.write("[error] %s: %s\n" % (type(exc).__name__, exc))
            return self.send_err(500, "伺服器出錯了,已記錄。", "server_error")

    def api(self, path, query):
        method = "GET" if self.command == "HEAD" else self.command

        if path == "/api/health" and method == "GET":
            with connect() as conn:
                return self.send_json(200, {
                    "ok": True, "version": VERSION, "readonly": CFG["readonly"],
                    "admin": bool(CFG["admin_token"]), "stats": stats(conn),
                    "round": round_payload(conn),
                    "limits": {
                        "title_max": TITLE_MAX_LEN, "title_min": TITLE_MIN_LEN,
                        "detail_max": DETAIL_MAX_LEN, "author_max": AUTHOR_MAX_LEN,
                        "tag_max_count": TAG_MAX_COUNT, "tag_max_len": TAG_MAX_LEN,
                        "wishes_per_hour": RATE_WISH_MAX, "votes_per_hour": RATE_VOTE_MAX,
                    },
                })

        if path == "/api/wishes" and method == "GET":
            q = clean_text(query.get("q", [""])[0], 80)
            tag = clean_text(query.get("tag", [""])[0], TAG_MAX_LEN).lower()
            status = query.get("status", [""])[0]
            sort = query.get("sort", ["hot"])[0]
            sort = sort if sort in SORTS else "hot"
            try:
                limit = min(200, max(1, int(query.get("limit", ["50"])[0])))
                offset = max(0, int(query.get("offset", ["0"])[0]))
            except ValueError:
                raise Invalid("limit / offset 必須是數字。", "bad_query")
            with connect() as conn:
                ensure_rounds(conn)
                items, total = list_wishes(conn, q, status, tag, sort, limit, offset)
                return self.send_json(200, {
                    "ok": True, "wishes": items, "total": total,
                    "limit": limit, "offset": offset, "sort": sort,
                    "stats": stats(conn), "tags": tag_counts(conn),
                    "readonly": CFG["readonly"],
                })

        if path == "/api/round" and method == "GET":
            with connect() as conn:
                return self.send_json(200, {"ok": True, "round": round_payload(conn)})

        if path == "/api/wishes" and method == "POST":
            self.guard_write()
            fields = validate_wish(self.read_json())
            ip_hash = hash_ip(self.real_ip())
            with connect() as conn:
                begin_write(conn)
                rate_check(conn, ip_hash, "wish", RATE_WISH_MAX, RATE_WISH_WINDOW)
                dup = conn.execute("SELECT * FROM wishes WHERE norm_title=?",
                                   (fields["norm_title"],)).fetchone()
                if dup is not None:
                    if dup["status"] == "hidden":
                        raise Invalid("這個願望之前被下架了,換個說法或補充說明再試。",
                                      "duplicate_hidden")
                    votes, already = register_vote(conn, dup["id"], ip_hash)
                    rate_record(conn, ip_hash, "vote")
                    row = conn.execute("SELECT * FROM wishes WHERE id=?",
                                       (dup["id"],)).fetchone()
                    return self.send_json(200, {
                        "ok": True, "merged": True, "already_voted": already,
                        "votes": votes, "wish": row_to_wish(row),
                        "message": "有人許過一樣的願了,幫你加上一票。",
                    })
                ts = now_sql()
                cur = conn.execute(
                    "INSERT INTO wishes(title,norm_title,detail,tags,author,status,"
                    "votes,created_at,updated_at,ip_hash) "
                    "VALUES(?,?,?,?,?,'open',0,?,?,?)",
                    (fields["title"], fields["norm_title"], fields["detail"],
                     fields["tags"], fields["author"], ts, ts, ip_hash),
                )
                wish_id = cur.lastrowid
                register_vote(conn, wish_id, ip_hash)  # 許願的人自動算一票
                rate_record(conn, ip_hash, "wish")
                row = conn.execute("SELECT * FROM wishes WHERE id=?", (wish_id,)).fetchone()
                return self.send_json(201, {"ok": True, "merged": False,
                                            "wish": row_to_wish(row)})

        m = re.fullmatch(r"/api/wishes/(\d+)/vote", path)
        if m and method == "POST":
            self.guard_write()
            wish_id = int(m.group(1))
            ip_hash = hash_ip(self.real_ip())
            with connect() as conn:
                begin_write(conn)
                row = conn.execute("SELECT id,status FROM wishes WHERE id=?",
                                   (wish_id,)).fetchone()
                if row is None or row["status"] == "hidden":
                    return self.send_err(404, "找不到這個願望。", "not_found")
                rate_check(conn, ip_hash, "vote", RATE_VOTE_MAX, RATE_VOTE_WINDOW)
                votes, already = register_vote(conn, wish_id, ip_hash)
                rate_record(conn, ip_hash, "vote")
                return self.send_json(200, {"ok": True, "votes": votes,
                                            "already_voted": already})

        m = re.fullmatch(r"/api/wishes/(\d+)", path)
        if m and method == "GET":
            with connect() as conn:
                row = conn.execute("SELECT * FROM wishes WHERE id=?",
                                   (int(m.group(1)),)).fetchone()
            if row is None or row["status"] == "hidden":
                return self.send_err(404, "找不到這個願望。", "not_found")
            return self.send_json(200, {"ok": True, "wish": row_to_wish(row)})

        # ── 管理端:沒設權杖就整組關閉 ──────────────────────────────
        m = re.fullmatch(r"/api/admin/wishes/(\d+)", path)
        if m and method == "POST":
            self.require_admin()
            wish_id = int(m.group(1))
            body = self.read_json()
            sets, args = [], []
            if "status" in body:
                if body["status"] not in STATUSES:
                    raise Invalid("status 必須是 %s 之一。" % "/".join(STATUSES),
                                  "bad_status", "status")
                sets.append("status=?")
                args.append(body["status"])
            if "note" in body:
                sets.append("note=?")
                args.append(clean_text(body["note"], 500, allow_newlines=True))
            if "skill_url" in body:
                url = clean_text(body["skill_url"], 300)
                if url and not url.startswith(("https://", "http://")):
                    raise Invalid("skill_url 要是 http(s) 網址。", "bad_url", "skill_url")
                sets.append("skill_url=?")
                args.append(url)
            if not sets:
                raise Invalid("沒有要更新的欄位。", "nothing_to_do")
            sets.append("updated_at=?")
            args.append(now_sql())
            args.append(wish_id)
            with connect() as conn:
                cur = conn.execute("UPDATE wishes SET %s WHERE id=?" % ",".join(sets), args)
                if cur.rowcount == 0:
                    return self.send_err(404, "找不到這個願望。", "not_found")
                row = conn.execute("SELECT * FROM wishes WHERE id=?", (wish_id,)).fetchone()
            return self.send_json(200, {"ok": True, "wish": row_to_wish(row)})

        if m and method == "DELETE":
            self.require_admin()
            if parse_qs(urlparse(self.path).query).get("confirm", [""])[0] != "1":
                raise Invalid("永久刪除要帶 ?confirm=1。想暫時下架請改成 status=hidden。",
                              "need_confirm")
            with connect() as conn:
                cur = conn.execute("DELETE FROM wishes WHERE id=?", (int(m.group(1)),))
            if cur.rowcount == 0:
                return self.send_err(404, "找不到這個願望。", "not_found")
            return self.send_json(200, {"ok": True, "deleted": int(m.group(1))})

        if path == "/api/admin/round/close" and method == "POST":
            self.require_admin()
            self.guard_write()
            with connect() as conn:
                now = int(time.time())
                anchor = cycle_anchor(conn)
                idx = (now - anchor) // CFG["cycle_seconds"]
                # 把起算點往回搬,讓「這一輪」的結束時間剛好是現在:歷屆編號不會亂,
                # 下一次 ensure_rounds() 就會把它結算掉,下一輪從現在開始。
                set_meta(conn, "cycle_anchor", now - (idx + 1) * CFG["cycle_seconds"])
                payload = round_payload(conn)
            return self.send_json(200, {"ok": True, "round": payload})

        if path == "/api/admin/export" and method == "GET":
            self.require_admin()
            with connect() as conn:
                items, total = list_wishes(conn, sort="new", limit=200,
                                           include_hidden=True)
                return self.send_json(200, {"ok": True, "wishes": items, "total": total,
                                            "stats": stats(conn)})

        return self.send_err(404, "沒有這個 API。", "not_found")

    # ── 靜態檔 ──────────────────────────────────────────────────────────
    def static(self, path):
        rel = path.lstrip("/") or "index.html"
        if rel.endswith("/"):
            rel += "index.html"
        target = os.path.realpath(os.path.join(PUBLIC_DIR, rel))
        root = os.path.realpath(PUBLIC_DIR)
        # 目錄逃脫:realpath 之後必須還在 public/ 底下,否則一律 404。
        if target != root and not target.startswith(root + os.sep):
            return self.send_err(404, "找不到檔案。", "not_found")
        ext = os.path.splitext(target)[1].lower()
        if ext not in STATIC_TYPES or not os.path.isfile(target):
            return self.send_err(404, "找不到檔案。", "not_found")
        try:
            with open(target, "rb") as fh:
                body = fh.read()
        except OSError:
            return self.send_err(404, "找不到檔案。", "not_found")

        self.send_response(200)
        self.send_header("Content-Type", STATIC_TYPES[ext])
        self.send_header("Content-Length", str(len(body)))
        if ext == ".html":
            self.send_header("Cache-Control", "no-cache")
            policy = csp_for_html(body)
            if policy:
                self.send_header("Content-Security-Policy", policy)
        elif ext == ".json":
            self.send_header("Cache-Control", "no-cache")
        else:
            self.send_header("Cache-Control", "public, max-age=3600")
        self.base_headers()
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)


# ── 啟動 ─────────────────────────────────────────────────────────────────

def seed_if_empty(path: str, zero_votes: bool = False) -> int:
    with connect() as conn:
        if conn.execute("SELECT COUNT(*) FROM wishes").fetchone()[0]:
            return 0
        try:
            with open(path, "r", encoding="utf-8") as fh:
                items = json.load(fh)
        except OSError:
            sys.stderr.write("[warn] 找不到種子檔 %s,跳過。\n" % path)
            return 0
        added = 0
        for item in items:
            try:
                fields = validate_wish(item)
            except Invalid as exc:
                sys.stderr.write("[warn] 種子資料跳過(%s):%s\n" % (exc.code, item))
                continue
            ts = now_sql()
            try:
                cur = conn.execute(
                    "INSERT INTO wishes(title,norm_title,detail,tags,author,status,votes,"
                    "skill_url,note,created_at,updated_at,ip_hash) "
                    "VALUES(?,?,?,?,?,?,?,?,?,?,?,'seed')",
                    (fields["title"], fields["norm_title"], fields["detail"],
                     fields["tags"], fields["author"],
                     item.get("status", "open") if item.get("status") in STATUSES else "open",
                     0, clean_text(item.get("skill_url"), 300),
                     clean_text(item.get("note"), 500), ts, ts),
                )
            except sqlite3.IntegrityError:
                continue
            # 種子的票數用假的 ip_hash 灌,才不會影響真人的一人一票。
            # zero_votes:對外的池子應該用這個 —— 示範用的票數會直接參加聯署,
            # 讓虛構的願望贏走第一輪,那是假的。0 票進場、低於門檻,沒有真人
            # 附議就不可能得標。
            wanted = 0 if zero_votes else max(0, int(item.get("votes", 0)))
            for i in range(wanted):
                conn.execute("INSERT OR IGNORE INTO votes(wish_id,ip_hash,ts) VALUES(?,?,?)",
                             (cur.lastrowid, "seed-%d" % i, int(time.time())))
            conn.execute("UPDATE wishes SET votes=(SELECT COUNT(*) FROM votes "
                         "WHERE wish_id=?) WHERE id=?", (cur.lastrowid, cur.lastrowid))
            added += 1
        return added


def main(argv=None):
    ap = argparse.ArgumentParser(description="Skill 許願池 後端")
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=8787)
    ap.add_argument("--db", default=os.environ.get("WISHPOOL_DB",
                                                   os.path.join(ROOT, "data", "wishes.db")))
    ap.add_argument("--seed", action="store_true", help="DB 為空時載入 data/seed.json")
    ap.add_argument("--seed-zero-votes", action="store_true",
                    help="種子願望一律 0 票進場(對外的池子請用這個,示範票數會污染聯署)")
    ap.add_argument("--seed-file", default=os.path.join(ROOT, "data", "seed.json"))
    ap.add_argument("--cycle-days", type=float,
                    default=float(os.environ.get("WISHPOOL_CYCLE_DAYS",
                                                 CYCLE_DAYS_DEFAULT)),
                    help="幾天結算一次聯署(預設 %d 天)" % CYCLE_DAYS_DEFAULT)
    ap.add_argument("--min-votes", type=int,
                    default=int(os.environ.get("WISHPOOL_MIN_VOTES", MIN_VOTES_DEFAULT)),
                    help="出線的最低票數門檻")
    ap.add_argument("--quiet", action="store_true")
    args = ap.parse_args(argv)

    CFG["db"] = os.path.abspath(args.db)
    CFG["quiet"] = args.quiet
    CFG["cycle_days"] = int(args.cycle_days) if args.cycle_days == int(args.cycle_days) \
        else args.cycle_days
    # WISHPOOL_CYCLE_SECONDS 只給測試用(把三天縮成兩秒),正常部署請用 --cycle-days。
    CFG["cycle_seconds"] = int(os.environ.get("WISHPOOL_CYCLE_SECONDS", "0")) \
        or max(1, int(args.cycle_days * 86400))
    CFG["min_votes"] = max(1, args.min_votes)
    CFG["readonly"] = os.environ.get("WISHPOOL_READONLY", "") == "1"
    CFG["admin_token"] = os.environ.get("WISHPOOL_ADMIN_TOKEN", "")
    CFG["allow_origin"] = os.environ.get("WISHPOOL_ALLOW_ORIGIN", "")
    CFG["trust_proxy"] = os.environ.get("WISHPOOL_TRUST_PROXY", "") == "1"
    csp = os.environ.get("WISHPOOL_CSP", "hash")
    CFG["csp_mode"] = csp if csp in ("hash", "unsafe-inline", "off") else "hash"
    CFG["salt"] = load_salt(os.environ.get(
        "WISHPOOL_SALT_FILE", os.path.join(os.path.dirname(CFG["db"]), "ip_salt")))

    init_db()
    if args.seed:
        added = seed_if_empty(args.seed_file, zero_votes=args.seed_zero_votes)
        if added:
            sys.stderr.write("[info] 載入 %d 筆種子願望%s\n"
                             % (added, "(0 票)" if args.seed_zero_votes else ""))

    httpd = ThreadingHTTPServer((args.host, args.port), Handler)
    httpd.daemon_threads = True
    if not args.quiet:
        sys.stderr.write(
            "Skill 許願池 %s\n  http://%s:%d\n  DB: %s\n  聯署結算週期: %s 天"
            "(門檻 %d 票)\n  唯讀: %s  管理端: %s  信任代理: %s\n" % (
                VERSION, args.host, args.port, CFG["db"],
                CFG["cycle_days"], CFG["min_votes"],
                "是" if CFG["readonly"] else "否",
                "開" if CFG["admin_token"] else "關(未設 WISHPOOL_ADMIN_TOKEN)",
                "是" if CFG["trust_proxy"] else "否"))
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        httpd.server_close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
