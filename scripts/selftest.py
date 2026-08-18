#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""端到端自我測試:真的把伺服器跑起來、真的打 HTTP。

    python3 scripts/selftest.py                 # 跑完整套,任何一項失敗就 exit 1
    python3 scripts/selftest.py --verify-gauge  # 反向對照:把防護拆掉,確認這套測試會紅

為什麼要有 --verify-gauge:一套永遠會綠的測試比沒有測試更危險。它會複製一份原始碼、
把某個防護改壞(標題長度上限、投票去重、目錄逃脫檢查、速率限制),然後要求同一套測試
**必須失敗**。如果拆掉防護測試還是全綠,那就是這把尺量錯了東西。
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import socket
import sqlite3
import subprocess
import sys
import tempfile
import threading
import time
import urllib.error
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PY = sys.executable


# ── HTTP 小工具 ──────────────────────────────────────────────────────────

def req(port, method, path, body=None, headers=None, raw=None):
    url = "http://127.0.0.1:%d%s" % (port, path)
    data = raw if raw is not None else (
        json.dumps(body, ensure_ascii=False).encode("utf-8") if body is not None else None)
    request = urllib.request.Request(url, data=data, method=method)
    if data is not None:
        request.add_header("Content-Type", "application/json")
    for key, value in (headers or {}).items():
        request.add_header(key, value)
    try:
        with urllib.request.urlopen(request, timeout=15) as res:
            payload = res.read()
            return res.status, parse(payload), dict(res.headers)
    except urllib.error.HTTPError as exc:
        payload = exc.read()
        return exc.code, parse(payload), dict(exc.headers)


def parse(payload: bytes):
    try:
        return json.loads(payload.decode("utf-8"))
    except Exception:
        return payload


def raw_get(port, path):
    """繞過 urllib 的路徑正規化,直接把原始請求行丟進 socket。

    urllib 會先幫你把 `/../x` 收成 `/x`,所以用它測目錄逃脫等於沒測 ——
    這個假綠燈是 --verify-gauge 抓出來的:把逃脫檢查整段拆掉,測試照樣全綠。
    """
    with socket.create_connection(("127.0.0.1", port), timeout=10) as sock:
        sock.sendall(("GET %s HTTP/1.1\r\nHost: 127.0.0.1\r\n"
                      "Connection: close\r\n\r\n" % path).encode("utf-8"))
        chunks = []
        while True:
            block = sock.recv(65536)
            if not block:
                break
            chunks.append(block)
    data = b"".join(chunks)
    head, _, body = data.partition(b"\r\n\r\n")
    parts = head.split(b" ")
    status = int(parts[1]) if len(parts) > 1 and parts[1].isdigit() else 0
    return status, body


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


class Server:
    """把 server.py 跑成子行程,結束時保證收乾淨。"""

    def __init__(self, src_root, env_extra=None, args=None, label=""):
        self.src_root = src_root
        self.env_extra = env_extra or {}
        self.args = args or []
        self.label = label
        self.port = free_port()
        self.dir = tempfile.mkdtemp(prefix="wishpool-test-")
        self.db = os.path.join(self.dir, "wishes.db")
        self.proc = None

    def __enter__(self):
        env = dict(os.environ)
        env.pop("WISHPOOL_ADMIN_TOKEN", None)
        env.update({k: str(v) for k, v in self.env_extra.items()})
        env["PYTHONIOENCODING"] = "utf-8"
        self.proc = subprocess.Popen(
            [PY, os.path.join(self.src_root, "server.py"),
             "--host", "127.0.0.1", "--port", str(self.port), "--db", self.db,
             "--quiet"] + self.args,
            env=env, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
        deadline = time.time() + 20
        while time.time() < deadline:
            if self.proc.poll() is not None:
                err = self.proc.stderr.read().decode("utf-8", "replace")
                raise RuntimeError("伺服器啟動就死了(%s):\n%s" % (self.label, err))
            try:
                status, _, _ = req(self.port, "GET", "/api/health")
                if status == 200:
                    return self
            except Exception:
                time.sleep(0.15)
        raise RuntimeError("伺服器 20 秒內沒有回應 /api/health(%s)" % self.label)

    def __exit__(self, *exc):
        if self.proc and self.proc.poll() is None:
            self.proc.terminate()
            try:
                self.proc.wait(timeout=10)
            except subprocess.TimeoutExpired:
                self.proc.kill()
        if self.proc:
            self.proc.stderr.close()
        shutil.rmtree(self.dir, ignore_errors=True)
        return False


class Checks:
    def __init__(self):
        self.results = []

    def ok(self, name, condition, detail=""):
        self.results.append((name, bool(condition), "" if condition else detail))
        return bool(condition)

    def eq(self, name, got, want):
        return self.ok(name, got == want, "得到 %r,預期 %r" % (got, want))

    @property
    def failed(self):
        return [r for r in self.results if not r[1]]


TOKEN = "test-token-do-not-use-in-production"
XSS = '<img src=x onerror="alert(1)">「引號」& <script>alert(2)</script>'


# ── 主要功能 ─────────────────────────────────────────────────────────────

def suite_core(c, src_root):
    env = {"WISHPOOL_ADMIN_TOKEN": TOKEN,
           "WISHPOOL_RATE_WISH_MAX": 200, "WISHPOOL_RATE_VOTE_MAX": 500,
           "WISHPOOL_TRUST_PROXY": 1, "WISHPOOL_POW": 0}
    with Server(src_root, env, label="core") as srv:
        p = srv.port

        # 健康檢查與輪次資訊
        status, health, _ = req(p, "GET", "/api/health")
        c.eq("health 回 200", status, 200)
        c.ok("health 有 round 區塊", isinstance(health.get("round"), dict), repr(health)[:200])
        c.ok("health 說管理端是開的", health.get("admin") is True)

        # 許願
        status, data, _ = req(p, "POST", "/api/wishes", {
            "title": "把發票 PDF 自動整理成報稅表格",
            "detail": "每季都要做一次,很煩。",
            "tags": "excel, 報稅, EXCEL, a, b, c, d",
            "author": "測試",
        })
        c.eq("許願回 201", status, 201)
        wish = (data or {}).get("wish") or {}
        wish_id = wish.get("id")
        c.ok("新願望有 id", bool(wish_id), repr(data)[:200])
        c.eq("許願者自動算一票", wish.get("votes"), 1)
        c.eq("標籤去重、轉小寫、砍到 5 個", wish.get("tags"), ["excel", "報稅", "a", "b", "c"])

        # 列表 / 搜尋 / 排序
        status, data, _ = req(p, "GET", "/api/wishes?limit=50")
        c.eq("列表回 200", status, 200)
        c.ok("列表看得到剛許的願", any(w["id"] == wish_id for w in data["wishes"]))
        for sort in ("hot", "new", "top"):
            status, _, _ = req(p, "GET", "/api/wishes?sort=" + sort)
            c.eq("sort=%s 可用" % sort, status, 200)
        status, data, _ = req(p, "GET", "/api/wishes?q=" + urlencode("發票"))
        c.ok("搜尋找得到", any(w["id"] == wish_id for w in data["wishes"]))
        status, data, _ = req(p, "GET", "/api/wishes?tag=excel")
        c.ok("標籤篩選找得到", any(w["id"] == wish_id for w in data["wishes"]))
        status, data, _ = req(p, "GET", "/api/wishes?q=" + urlencode("絕對不存在的字串zzz"))
        c.eq("搜不到就回空的", data["wishes"], [])

        # 標籤列的詞彙表要是「全池」的,不能只有篩選結果裡的標籤 ——
        # 否則按下一個標籤之後就換不了另一個標籤(實機測試抓到過的 bug)。
        req(p, "POST", "/api/wishes", {"title": "標籤詞彙表測試願望甲", "tags": "alpha"})
        req(p, "POST", "/api/wishes", {"title": "標籤詞彙表測試願望乙", "tags": "beta"})
        status, data, _ = req(p, "GET", "/api/wishes?tag=alpha")
        names = [t[0] for t in data.get("tags", [])]
        c.ok("篩選 alpha 時標籤清單仍看得到 beta",
             "alpha" in names and "beta" in names, repr(names))
        c.ok("篩選 alpha 時願望列表只剩 alpha",
             data["wishes"] and all("alpha" in w["tags"] for w in data["wishes"]),
             repr([w["tags"] for w in data["wishes"]]))

        # 驗證:標題
        status, data, _ = req(p, "POST", "/api/wishes", {"title": "   "})
        c.eq("空標題被擋", status, 400)
        c.eq("空標題錯誤碼", data.get("code"), "empty_title")
        status, data, _ = req(p, "POST", "/api/wishes", {"title": "字"})
        c.eq("標題太短被擋", data.get("code"), "short_title")
        status, data, _ = req(p, "POST", "/api/wishes", {"title": "長" * 200})
        c.eq("標題過長被擋", data.get("code"), "long_title")
        status, data, _ = req(p, "POST", "/api/wishes", {"title": "。。。,,,!!!"})
        c.eq("只有標點的標題被擋", data.get("code"), "weak_title")

        # 驗證:內文
        status, data, _ = req(p, "POST", "/api/wishes",
                              {"title": "說明過長測試", "detail": "字" * 2100})
        c.eq("說明過長被擋", data.get("code"), "long_detail")
        status, data, _ = req(p, "POST", "/api/wishes", {
            "title": "連結太多測試",
            "detail": " ".join("https://example.com/%d" % i for i in range(6))})
        c.eq("連結太多被擋", data.get("code"), "too_many_links")
        status, data, _ = req(p, "POST", "/api/wishes",
                              {"title": "暱稱放連結測試", "author": "http://spam.example"})
        c.eq("暱稱含連結被擋", data.get("code"), "author_link")

        # 蜜罐
        status, data, _ = req(p, "POST", "/api/wishes",
                              {"title": "蜜罐測試願望", "hp": "我是機器人"})
        c.eq("蜜罐填了就被擋", data.get("code"), "rejected")

        # 髒字元清理
        status, data, _ = req(p, "POST", "/api/wishes",
                              {"title": "零​寬‌字﻿元 清理測試"})
        c.eq("零寬字元被清掉", (data.get("wish") or {}).get("title"), "零寬字元 清理測試")

        # 重複合併
        status, data, _ = req(p, "POST", "/api/wishes",
                              {"title": "把發票 PDF,自動整理成報稅表格!!"})
        c.eq("重複標題被合併", status, 200)
        c.eq("合併標記", data.get("merged"), True)
        c.eq("合併到原本那筆", (data.get("wish") or {}).get("id"), wish_id)

        # 投票與去重(用 X-Forwarded-For 模擬不同來源)
        status, data, _ = req(p, "POST", "/api/wishes", {"title": "第二個測試願望做投票用"})
        second = data["wish"]["id"]
        status, data, _ = req(p, "POST", "/api/wishes/%d/vote" % second,
                              headers={"X-Forwarded-For": "203.0.113.7"})
        c.eq("別的來源投票成功", status, 200)
        c.eq("票數變 2", data.get("votes"), 2)
        c.eq("第一次投票不算重複", data.get("already_voted"), False)
        status, data, _ = req(p, "POST", "/api/wishes/%d/vote" % second,
                              headers={"X-Forwarded-For": "203.0.113.7"})
        c.eq("同一來源重複投票被吃掉", data.get("already_voted"), True)
        c.eq("票數沒有變成 3", data.get("votes"), 2)
        status, _, _ = req(p, "POST", "/api/wishes/999999/vote")
        c.eq("投不存在的願望回 404", status, 404)

        # XSS 字串:必須原樣存回來(前端只用 textContent,所以資料層不做逃脫)
        status, data, _ = req(p, "POST", "/api/wishes",
                              {"title": "XSS 測試", "detail": XSS})
        xss_id = data["wish"]["id"]
        c.eq("危險字串原樣存回", data["wish"]["detail"], XSS)

        # 請求體大小與格式
        status, data, _ = req(p, "POST", "/api/wishes", raw=b"x" * (70 * 1024))
        c.eq("超大請求體被擋", status, 413)
        status, data, _ = req(p, "POST", "/api/wishes", raw=b"{not json")
        c.eq("壞 JSON 被擋", status, 400)
        status, _, _ = req(p, "GET", "/api/nope")
        c.eq("不存在的 API 回 404", status, 404)

        # 讀取要能被別的網站(別人的 AI 助手)抓,寫入不能 ——
        # 願望是公開資料而且沒有 cookie,所以開放讀取不會洩漏任何人的東西;
        # 但寫入若也開放跨來源,任何網站都能借訪客的手送出願望。
        _, _, headers = req(p, "GET", "/api/wishes")
        c.eq("讀取開放跨來源", headers.get("Access-Control-Allow-Origin"), "*")
        _, _, headers = req(p, "GET", "/robots.txt")
        c.eq("robots.txt 讀得到", headers.get("Access-Control-Allow-Origin"), "*")
        _, _, headers = req(p, "POST", "/api/wishes", {"title": "跨來源寫入測試願望"})
        c.eq("寫入不開放跨來源", headers.get("Access-Control-Allow-Origin"), None)
        status, body = raw_get(p, "/robots.txt")
        c.ok("robots.txt 允許抓取", status == 200 and b"Allow: /" in body,
             "status=%s" % status)

        # 靜態檔:目錄逃脫與 CSP
        # 目標刻意選 data/seed.json —— 副檔名是白名單裡的 .json,所以只有
        # realpath 逃脫檢查擋得住它。拿 server.py 當目標會被副檔名白名單擋掉,
        # 測起來是綠的但沒測到那道防線。
        status, body = raw_get(p, "/../data/seed.json")
        c.ok("目錄逃脫拿不到 public/ 外的 .json",
             status == 404 and b"seed" not in body.lower() and "報稅".encode() not in body,
             "status=%s body=%r" % (status, body[:120]))
        status, body = raw_get(p, "/../../../../../../etc/passwd")
        c.eq("往上爬到系統路徑回 404", status, 404)
        status, body = raw_get(p, "/..%2fdata%2fseed.json")
        c.eq("編碼過的目錄逃脫也回 404", status, 404)
        status, body = raw_get(p, "/../server.py")
        c.ok("拿不到原始碼", status == 404 and b"WISHPOOL_ADMIN_TOKEN" not in body,
             "status=%s" % status)
        status, body, headers = req(p, "GET", "/")
        c.eq("首頁回 200", status, 200)
        csp = headers.get("Content-Security-Policy", "")
        c.ok("首頁有 CSP", "default-src 'none'" in csp, csp[:120])
        c.ok("CSP 用雜湊而不是 unsafe-inline",
             "sha256-" in csp and "'unsafe-inline'" not in csp, csp[:200])
        c.ok("有 nosniff", headers.get("X-Content-Type-Options") == "nosniff")

        # ── 前端原始碼層的防線 ─────────────────────────────────────
        with open(os.path.join(src_root, "public", "index.html"), "r",
                  encoding="utf-8") as fh:
            page = fh.read()

        # 第三方動畫引擎是 esbuild 打包進來的壓縮碼,裡面本來就有 innerHTML 之類的
        # 東西。掃注入接口時要把它切掉,否則這條永遠是紅的、然後就會被關掉 ——
        # 但**切掉的部分要另外驗**(下面三條),不能變成盲點。
        VSTART = "<!-- vendor:start"
        VEND = "<!-- vendor:end -->"
        c.eq("vendor 標記剛好各一個", (page.count(VSTART), page.count(VEND)), (1, 1))
        if VSTART in page and VEND in page:
            head, rest = page.split(VSTART, 1)
            vendor, tail = rest.split(VEND, 1)
            app = head + tail
        else:
            vendor, app = "", page

        # 找的是真正的注入接口,而且只看**手寫的那部分**。加了任何一個,
        # 使用者輸入就有可能被當成 HTML 執行,這條會立刻紅。
        sinks = [s for s in (".innerHTML", ".outerHTML", "insertAdjacentHTML",
                             "document.write", "eval(") if s in app]
        c.ok("手寫前端沒有用到 HTML 注入接口", not sinks,
             "index.html 的非 vendor 區塊出現 %s" % ", ".join(sinks))

        # 整頁(含第三方)都不准出現外連 —— 打包的意義就是執行時不連外。
        c.ok("整頁沒有外部資源網址",
             not any(s in page for s in ("//cdn.", "https://fonts.", "http://cdn.",
                                         "unpkg.com", "jsdelivr", "//esm.sh")),
             "index.html 出現外部資源")
        c.ok("vendor 區塊真的有東西", len(vendor) > 20000, "%d 位元組" % len(vendor))
        # 體積上限:打包很容易一路長大,超過就要有人做決定,不要靜靜變肥。
        c.ok("整頁不超過 200KB", len(page.encode("utf-8")) < 200 * 1024,
             "%.1f KB" % (len(page.encode("utf-8")) / 1024))

        # 動效預算:無限循環的 CSS 動畫每一幀都在燒電。列表上每張卡一個的那種
        # 尤其致命(12 張卡 = 12 個)。手寫 CSS 裡的 `infinite` 不准超過 4 個。
        infinite = app.count("infinite")
        c.ok("無限循環動畫不超過 4 個", infinite <= 4, "手寫 CSS 裡有 %d 個" % infinite)
        # reduced-motion 必須整套關掉,不是放慢
        c.ok("有尊重 prefers-reduced-motion",
             "prefers-reduced-motion:reduce" in app.replace(" ", ""),
             "找不到 reduced-motion 區塊")

        # 管理端
        status, _, _ = req(p, "POST", "/api/admin/wishes/%d" % wish_id, {"status": "granted"})
        c.eq("沒帶權杖回 401", status, 401)
        status, _, _ = req(p, "POST", "/api/admin/wishes/%d" % wish_id, {"status": "granted"},
                           headers={"X-Admin-Token": "wrong"})
        c.eq("錯的權杖回 401", status, 401)
        status, data, _ = req(p, "POST", "/api/admin/wishes/%d" % wish_id,
                              {"status": "granted", "skill_url": "https://example.com/skill",
                               "note": "做好了"},
                              headers={"X-Admin-Token": TOKEN})
        c.eq("管理端改狀態成功", status, 200)
        c.eq("狀態變 granted", (data.get("wish") or {}).get("status"), "granted")
        status, data, _ = req(p, "POST", "/api/admin/wishes/%d" % wish_id,
                              {"skill_url": "javascript:alert(1)"},
                              headers={"X-Admin-Token": TOKEN})
        c.eq("非 http 的 skill_url 被擋", data.get("code"), "bad_url")
        status, data, _ = req(p, "POST", "/api/admin/wishes/%d" % wish_id,
                              {"status": "not-a-status"}, headers={"X-Admin-Token": TOKEN})
        c.eq("亂填 status 被擋", data.get("code"), "bad_status")

        # 下架:公開列表與單筆查詢都要看不到
        req(p, "POST", "/api/admin/wishes/%d" % xss_id, {"status": "hidden"},
            headers={"X-Admin-Token": TOKEN})
        status, data, _ = req(p, "GET", "/api/wishes?limit=200")
        c.ok("下架的願望不在公開列表", all(w["id"] != xss_id for w in data["wishes"]))
        status, _, _ = req(p, "GET", "/api/wishes/%d" % xss_id)
        c.eq("下架的願望單筆查詢回 404", status, 404)
        status, data, _ = req(p, "GET", "/api/admin/export", headers={"X-Admin-Token": TOKEN})
        c.ok("管理端匯出看得到下架的",
             any(w["id"] == xss_id for w in data.get("wishes", [])))

        # 永久刪除要 confirm
        status, data, _ = req(p, "DELETE", "/api/admin/wishes/%d" % xss_id,
                              headers={"X-Admin-Token": TOKEN})
        c.eq("刪除沒帶 confirm 被擋", data.get("code"), "need_confirm")
        status, data, _ = req(p, "DELETE", "/api/admin/wishes/%d?confirm=1" % xss_id,
                              headers={"X-Admin-Token": TOKEN})
        c.eq("帶了 confirm 才刪得掉", status, 200)

        # 隱私:資料庫裡不能有原始 IP
        db_text = read_db_text(srv.db)
        c.ok("資料庫沒有存原始 IP",
             "127.0.0.1" not in db_text and "203.0.113.7" not in db_text,
             "在 DB 裡找到原始 IP 字串")


def suite_rate_limit(c, src_root):
    """不覆寫任何速率設定 —— 這一節同時驗「預設值是多少」跟「真的會擋」。"""
    with Server(src_root, {"WISHPOOL_POW": 0}, label="rate") as srv:
        p = srv.port
        _, health, _ = req(p, "GET", "/api/health")
        limits = health.get("limits") or {}
        c.eq("預設每小時 5 個願望", limits.get("wishes_per_hour"), 5)
        c.eq("預設每小時 60 票", limits.get("votes_per_hour"), 60)
        codes = []
        for i in range(7):
            status, data, _ = req(p, "POST", "/api/wishes",
                                  {"title": "速率限制測試願望編號 %d" % i})
            codes.append((status, (data or {}).get("code")))
        c.eq("前 5 個許願成功", [s for s, _ in codes[:5]], [201] * 5)
        c.eq("第 6 個被速率限制", codes[5], (429, "rate_limited"))


def suite_rate_limit_race(c, src_root):
    """並行洗版:速率限制是「先數再寫」,沒有鎖的話同時打進來的請求會全部通過。

    這一節就是在證明那個 check-then-act 的競態關掉了。修之前實測 20 個並行請求
    在上限 5 的池子裡全部拿到 201。
    """
    with Server(src_root, {"WISHPOOL_POW": 0}, label="race") as srv:
        p = srv.port
        req(p, "GET", "/api/health")     # 先把 DB 初始化完,不要把建表算進競態
        results = []
        lock = threading.Lock()

        def fire(i):
            try:
                status, _, _ = req(p, "POST", "/api/wishes",
                                   {"title": "並行洗版測試願望編號 %02d" % i})
            except Exception as exc:                      # noqa: BLE001
                status = "EXC:" + type(exc).__name__
            with lock:
                results.append(status)

        threads = [threading.Thread(target=fire, args=(i,)) for i in range(20)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=60)
        created = results.count(201)
        limited = results.count(429)
        c.eq("20 個並行許願只有 5 個成功(預設上限)", created, 5)
        c.eq("其餘全部是 429,沒有 500 或例外", limited, len(results) - created)
        status, data, _ = req(p, "GET", "/api/wishes?limit=200")
        c.eq("資料庫裡真的只有 5 筆", data["total"], 5)


def suite_rounds(c, src_root):
    """聯署輪次:6 秒一輪,驗證票最高的真的出線、狀態轉成 planned。

    這一節刻意寫成「先確認票真的進去了」+「輪詢等結算」而不是 sleep 固定秒數。
    原本用 time.sleep(3.5) 的版本會偶發性失敗(三次重跑才紅一次)—— 會閃的測試
    跟假綠燈一樣糟:CI 隨機變紅之後,大家就開始忽略紅燈。
    """
    env = {"WISHPOOL_ADMIN_TOKEN": TOKEN, "WISHPOOL_CYCLE_SECONDS": 6,
           "WISHPOOL_RATE_WISH_MAX": 200, "WISHPOOL_RATE_VOTE_MAX": 500,
           "WISHPOOL_TRUST_PROXY": 1, "WISHPOOL_POW": 0}
    with Server(src_root, env, label="rounds") as srv:
        p = srv.port
        _, data, _ = req(p, "POST", "/api/wishes", {"title": "輪次測試:比較少票的願望"},
                         headers={"X-Forwarded-For": "198.51.100.1"})
        low = data["wish"]["id"]
        _, data, _ = req(p, "POST", "/api/wishes", {"title": "輪次測試:應該要出線的願望"},
                         headers={"X-Forwarded-For": "198.51.100.2"})
        high = data["wish"]["id"]
        votes = []
        for ip in ("198.51.100.3", "198.51.100.4"):
            status, vd, _ = req(p, "POST", "/api/wishes/%d/vote" % high,
                                headers={"X-Forwarded-For": ip})
            votes.append((status, (vd or {}).get("votes")))
        # 票沒進去的話,得標者就會變成另一個人 —— 先在這裡擋下來,
        # 不要讓它變成下游一個看不懂的失敗。
        c.eq("兩張外部票都投進去了", votes, [(200, 2), (200, 3)])

        _, data, _ = req(p, "GET", "/api/round")
        rnd = data["round"]
        c.eq("本輪編號從 1 開始", rnd.get("index"), 1)
        c.eq("領先者是票多的那個", (rnd.get("leader") or {}).get("id"), high)
        c.ok("有倒數秒數", isinstance(rnd.get("seconds_left"), int))

        # 輪詢等結算(最多 20 秒),而不是賭一個 sleep 剛好落在正確的位置
        deadline = time.time() + 20
        first, rnd = {}, {}
        while time.time() < deadline:
            _, data, _ = req(p, "GET", "/api/round")
            rnd = data["round"]
            first = next((h for h in (rnd.get("history") or []) if h["index"] == 1), {})
            if first.get("winner_id") is not None:
                break
            time.sleep(0.5)
        c.ok("第 1 輪在時限內結算了", bool(first), "round=%s" % repr(rnd)[:300])
        c.ok("過期後至少進到第 2 輪", (rnd.get("index") or 0) >= 2, "index=%s" % rnd.get("index"))
        c.eq("第 1 輪得標者是票最多的", first.get("winner_id"), high)
        c.eq("得標票數記錄正確", first.get("votes"), 3)

        _, data, _ = req(p, "GET", "/api/wishes/%d" % high)
        c.eq("得標願望狀態轉成 planned", data["wish"]["status"], "planned")
        c.ok("得標願望自動寫了備註", "聯署第一名" in (data["wish"]["note"] or ""),
             repr(data["wish"]["note"]))

        _, data, _ = req(p, "GET", "/api/round")
        leader = (data["round"].get("leader") or {}).get("id")
        # 第二名可能已經被下一輪收走(輪次只有 6 秒),所以兩種結果都算對:
        # 還在候選 → 它就是領先者;已經出線 → 狀態是 planned。
        _, low_data, _ = req(p, "GET", "/api/wishes/%d" % low)
        c.ok("下一輪換第二名(領先或已出線)",
             leader == low or low_data["wish"]["status"] == "planned",
             "leader=%s low.status=%s" % (leader, low_data["wish"]["status"]))

        status, data, _ = req(p, "POST", "/api/admin/round/close",
                              headers={"X-Admin-Token": TOKEN})
        c.eq("管理端可以提前結算", status, 200)
        _, data, _ = req(p, "GET", "/api/wishes/%d" % low)
        c.eq("提前結算後第二名也出線", data["wish"]["status"], "planned")


def suite_read_after_write(c, src_root):
    """寫完馬上讀:回應送出時,交易一定要已經提交了。

    這一節在盯一個真的發生過的 bug:handler 原本在 `with connect()` **裡面**就
    send_json,而 commit 是離開區塊才發生 —— 客戶端拿到 201 之後立刻發的下一個
    請求,可能用另一條連線讀到還沒有這筆資料的舊快照。症狀是「剛許的願不見了」。

    它在 Windows 上剛好贏得 race 所以測不出來,在 Linux 上穩定失敗。所以這裡跑
    多輪、中間不 sleep,把時間差壓到最小。
    """
    env = {"WISHPOOL_RATE_WISH_MAX": 200, "WISHPOOL_RATE_VOTE_MAX": 500,
           "WISHPOOL_TRUST_PROXY": 1, "WISHPOOL_POW": 0}
    with Server(src_root, env, label="raw") as srv:
        p = srv.port
        missing_after_create, missing_vote = [], []
        for i in range(10):
            _, data, _ = req(p, "POST", "/api/wishes",
                             {"title": "寫完馬上讀測試願望編號 %02d" % i})
            wid = (data.get("wish") or {}).get("id")
            # 中間刻意不睡:這就是重點
            _, listing, _ = req(p, "GET", "/api/wishes?limit=200&sort=new")
            if not any(w["id"] == wid for w in listing.get("wishes", [])):
                missing_after_create.append(wid)

            _, vd, _ = req(p, "POST", "/api/wishes/%d/vote" % wid,
                           headers={"X-Forwarded-For": "198.51.100.%d" % (100 + i)})
            _, one, _ = req(p, "GET", "/api/wishes/%d" % wid)
            if one.get("wish", {}).get("votes") != vd.get("votes"):
                missing_vote.append((wid, vd.get("votes"), one.get("wish", {}).get("votes")))
        c.eq("許願後立刻查列表,10 次都看得到", missing_after_create, [])
        c.eq("附議後立刻查單筆,票數 10 次都一致", missing_vote, [])

        _, listing, _ = req(p, "GET", "/api/wishes?limit=200")
        c.eq("10 筆都真的在資料庫裡", listing["total"], 10)


def lz_bits(digest: bytes) -> int:
    n = 0
    for byte in digest:
        if byte == 0:
            n += 8
            continue
        for shift in range(7, -1, -1):
            if (byte >> shift) & 1:
                return n
            n += 1
        return n
    return n


def solve_pow(port, kind, headers=None):
    """跟伺服器要一個挑戰並解開 —— 跟前端做的是同一件事。"""
    _, ch, _ = req(port, "GET", "/api/challenge?kind=" + kind, headers=headers)
    payload = (ch or {}).get("pow")
    if not payload:
        return None
    salt, bits = payload["salt"], payload["bits"]
    n = 0
    while True:
        if lz_bits(hashlib.sha256(("%s:%d" % (salt, n)).encode()).digest()) >= bits:
            out = dict(payload)
            out["nonce"] = str(n)
            return out
        n += 1


def suite_pow(c, src_root):
    """送出前的工作量證明。

    它擋的是「腳本大量灌」,不是「證明你是人類」—— 但只要它默默失效,
    這個站就只剩速率限制一層。所以每一種繞過方式都要有一條測試盯著。
    """
    with Server(src_root, {}, label="pow-default") as srv:
        _, health, _ = req(srv.port, "GET", "/api/health")
        c.eq("預設有開工作量證明", health.get("pow") or {}, {"wish": 16, "vote": 13})
        status, data, _ = req(srv.port, "POST", "/api/wishes", {"title": "沒帶驗證的許願"})
        c.eq("沒帶驗證的許願被擋", (status, (data or {}).get("code")), (400, "pow_required"))

    env = {"WISHPOOL_POW_BITS_WISH": 10, "WISHPOOL_POW_BITS_VOTE": 8,
           "WISHPOOL_RATE_WISH_MAX": 200, "WISHPOOL_RATE_VOTE_MAX": 500,
           "WISHPOOL_TRUST_PROXY": 1}
    with Server(src_root, env, label="pow") as srv:
        p = srv.port
        _, ch, _ = req(p, "GET", "/api/challenge?kind=wish")
        c.ok("挑戰含 salt/bits/expires/sig",
             all(k in (ch.get("pow") or {}) for k in ("salt", "bits", "expires", "sig")),
             repr(ch)[:160])
        c.eq("難度吃環境變數", ch["pow"]["bits"], 10)

        good = solve_pow(p, "wish")
        status, data, _ = req(p, "POST", "/api/wishes",
                              {"title": "帶了正確驗證的許願", "pow": good})
        c.eq("正確的驗證可以通過", status, 201)
        wish_id = (data.get("wish") or {}).get("id")

        status, data, _ = req(p, "POST", "/api/wishes",
                              {"title": "重放同一份驗證", "pow": good})
        c.eq("同一份驗證不能用第二次", (data or {}).get("code"), "pow_replay")

        bad = dict(solve_pow(p, "wish")); bad["nonce"] = "0"
        _, data, _ = req(p, "POST", "/api/wishes", {"title": "亂填 nonce", "pow": bad})
        c.eq("nonce 不對被擋", (data or {}).get("code"), "pow_bad")

        forged = {"salt": "f" * 32, "bits": 10, "expires": int(time.time()) + 300,
                  "sig": "0" * 32, "nonce": "1"}
        _, data, _ = req(p, "POST", "/api/wishes", {"title": "偽造簽章", "pow": forged})
        c.eq("偽造的簽章被擋", (data or {}).get("code"), "pow_bad")

        cheat = dict(solve_pow(p, "wish")); cheat["bits"] = 1
        _, data, _ = req(p, "POST", "/api/wishes", {"title": "自己調難度", "pow": cheat})
        c.eq("自己調低難度被擋", (data or {}).get("code"), "pow_bad")

        expired = dict(solve_pow(p, "wish")); expired["expires"] = int(time.time()) - 10
        _, data, _ = req(p, "POST", "/api/wishes", {"title": "過期的驗證", "pow": expired})
        c.ok("過期或被改的驗證被擋",
             (data or {}).get("code") in ("pow_expired", "pow_bad"), repr(data)[:120])

        _, data, _ = req(p, "POST", "/api/wishes/%d/vote" % wish_id,
                         headers={"X-Forwarded-For": "203.0.113.90"})
        c.eq("沒帶驗證的投票被擋", (data or {}).get("code"), "pow_required")
        vpow = solve_pow(p, "vote", headers={"X-Forwarded-For": "203.0.113.90"})
        status, data, _ = req(p, "POST", "/api/wishes/%d/vote" % wish_id,
                              {"pow": vpow}, headers={"X-Forwarded-For": "203.0.113.90"})
        c.eq("帶了正確驗證的投票可以通過", (status, data.get("votes")), (200, 2))

        other = solve_pow(p, "vote", headers={"X-Forwarded-For": "203.0.113.91"})
        _, data, _ = req(p, "POST", "/api/wishes/%d/vote" % wish_id,
                         {"pow": other}, headers={"X-Forwarded-For": "203.0.113.92"})
        c.eq("別的來源的驗證不能挪用", (data or {}).get("code"), "pow_bad")

    with Server(src_root, {"WISHPOOL_POW": 0}, label="pow-off") as srv:
        _, health, _ = req(srv.port, "GET", "/api/health")
        c.eq("關掉時 health 說沒有 pow", health.get("pow"), None)
        status, _, _ = req(srv.port, "POST", "/api/wishes", {"title": "關掉驗證後的許願"})
        c.eq("關掉時不帶驗證也能許願", status, 201)


def suite_csp_modes(c, src_root):
    """CSP 的三種模式。

    `hash` 是預設也是最強的,但雜湊是對「我們送出的位元組」算的 —— 前面的 CDN
    如果改寫 HTML(Cloudflare Rocket Loader / Auto Minify 之類),雜湊就對不上、
    整頁 JS 被擋成白畫面。所以要有退路,而且退路必須真的有效。
    """
    with Server(src_root, {}, label="csp-hash") as srv:
        _, _, headers = req(srv.port, "GET", "/")
        csp = headers.get("Content-Security-Policy", "")
        c.ok("預設模式用 sha256 雜湊", "sha256-" in csp and "'unsafe-inline'" not in csp,
             csp[:160])
    with Server(src_root, {"WISHPOOL_CSP": "unsafe-inline"}, label="csp-unsafe") as srv:
        _, _, headers = req(srv.port, "GET", "/")
        csp = headers.get("Content-Security-Policy", "")
        c.ok("退路模式改成 unsafe-inline",
             "'unsafe-inline'" in csp and "sha256-" not in csp and "default-src 'none'" in csp,
             csp[:160])
    with Server(src_root, {"WISHPOOL_CSP": "off"}, label="csp-off") as srv:
        _, _, headers = req(srv.port, "GET", "/")
        c.ok("off 模式完全不發 CSP 標頭",
             "Content-Security-Policy" not in headers, repr(headers.get("Content-Security-Policy")))
    with Server(src_root, {"WISHPOOL_CSP": "亂填的值"}, label="csp-bad") as srv:
        _, _, headers = req(srv.port, "GET", "/")
        csp = headers.get("Content-Security-Policy", "")
        c.ok("亂填的值退回最嚴格的 hash,不是變成沒有 CSP", "sha256-" in csp, csp[:120])


def suite_readonly(c, src_root):
    with Server(src_root, {"WISHPOOL_READONLY": 1}, label="readonly") as srv:
        p = srv.port
        _, health, _ = req(p, "GET", "/api/health")
        c.eq("health 說自己是唯讀", health.get("readonly"), True)
        status, data, _ = req(p, "POST", "/api/wishes", {"title": "唯讀模式應該擋下這個"})
        c.eq("唯讀模式擋掉許願", status, 403)
        c.eq("唯讀錯誤碼", data.get("code"), "readonly")
        status, _, _ = req(p, "GET", "/api/wishes")
        c.eq("唯讀模式還是讀得到", status, 200)


def suite_admin_disabled(c, src_root):
    """沒設權杖時管理端必須整組關閉(fail-closed),不是變成誰都能改。"""
    with Server(src_root, {}, label="no-admin") as srv:
        p = srv.port
        _, health, _ = req(p, "GET", "/api/health")
        c.eq("health 說管理端是關的", health.get("admin"), False)
        for method, path in (("POST", "/api/admin/wishes/1"),
                             ("GET", "/api/admin/export"),
                             ("POST", "/api/admin/round/close")):
            status, data, _ = req(p, method, path,
                                  {"status": "granted"} if method == "POST" else None,
                                  headers={"X-Admin-Token": "anything"})
            c.eq("沒設權杖時 %s 回 503" % path, status, 503)


# ── 小工具 ───────────────────────────────────────────────────────────────

def urlencode(text):
    from urllib.parse import quote
    return quote(text)


def as_bytes(value):
    if isinstance(value, bytes):
        return value
    return json.dumps(value, ensure_ascii=False).encode("utf-8")


def read_db_text(db_path):
    """把 DB 每一張表的每一格都轉成字串,拿來找不該出現的東西。"""
    out = []
    conn = sqlite3.connect(db_path)
    try:
        tables = [r[0] for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'")]
        for table in tables:
            for row in conn.execute("SELECT * FROM %s" % table):
                out.extend(str(cell) for cell in row)
    finally:
        conn.close()
    return "\n".join(out)


def run_all(src_root):
    c = Checks()
    for suite in (suite_core, suite_rate_limit, suite_rate_limit_race,
                  suite_read_after_write, suite_rounds, suite_pow, suite_csp_modes,
                  suite_readonly, suite_admin_disabled):
        try:
            suite(c, src_root)
        except Exception as exc:  # 一節炸掉不要影響其他節,但要記成失敗
            c.ok("%s 執行完成" % suite.__name__, False,
                 "%s: %s" % (type(exc).__name__, exc))
    return c


# ── 反向對照:拆掉防護,這套測試必須紅 ────────────────────────────────

# 這張表用**內容錨點**定位程式碼,錨點對不上會直接失敗而不是安靜跳過 —— 故意的。
#
# 有一個防護刻意**不放**在這裡:「回應必須在交易提交之後才送出」。把它改壞的效果
# 是時間相依的(在贏得 race 的機器上照樣會綠),要求它必須變紅會讓 --verify-gauge
# 自己開始閃。盯著它的是 suite_read_after_write 的多輪無延遲讀寫。
MUTATIONS = [
    ("拿掉標題長度上限",
     "    if len(title) > TITLE_MAX_LEN:", "    if False:"),
    ("拿掉投票去重",
     '"INSERT OR IGNORE INTO votes(wish_id, ip_hash, ts) VALUES(?,?,?)"',
     '"INSERT OR REPLACE INTO votes(wish_id, ip_hash, ts) VALUES(?,?,?)"'),
    ("拿掉目錄逃脫檢查",
     "        if target != root and not target.startswith(root + os.sep):",
     "        if False:"),
    ("拿掉速率限制",
     "    if used >= limit:", "    if False:"),
    ("拿掉寫入鎖(速率限制的競態就會回來)",
     '    conn.execute("BEGIN IMMEDIATE")', "    pass"),
    ("拿掉工作量證明的雜湊檢查",
     "    if leading_zero_bits(digest) < bits:", "    if False:"),
    ("拿掉工作量證明的防重放",
     '        conn.execute("INSERT INTO pow_used(salt, ts) VALUES(?,?)",',
     "        _ = (lambda *a: None)("),
    ("拿掉輪次得標判定",
     "        winner = pick_winner(conn, ends)", "        winner = None"),
]


def verify_gauge():
    print("反向對照:每一項都會把一個防護改壞,然後要求測試必須失敗。\n")
    with open(os.path.join(ROOT, "server.py"), "r", encoding="utf-8") as fh:
        original = fh.read()
    all_good = True
    for label, anchor, replacement in MUTATIONS:
        # 錨點找不到就直接失敗:代表原始碼變了、這支反向對照已經量錯地方。
        if original.count(anchor) != 1:
            print("  ✗ %s:錨點在 server.py 裡出現 %d 次(需要剛好 1 次),"
                  "請更新 MUTATIONS" % (label, original.count(anchor)))
            all_good = False
            continue
        tmp = tempfile.mkdtemp(prefix="wishpool-mutant-")
        try:
            dst = os.path.join(tmp, "src")
            shutil.copytree(ROOT, dst, ignore=shutil.ignore_patterns(
                ".git", "*.db", "*.db-wal", "*.db-shm", "ip_salt", "__pycache__"))
            with open(os.path.join(dst, "server.py"), "w", encoding="utf-8",
                      newline="\n") as fh:
                fh.write(original.replace(anchor, replacement))
            result = run_all(dst)
            if result.failed:
                names = ", ".join(n for n, _, _ in result.failed[:3])
                print("  ✓ %s → 測試如預期失敗 %d 項(%s…)"
                      % (label, len(result.failed), names))
            else:
                print("  ✗ %s → 防護拆掉了測試竟然全綠,這把尺量錯東西了" % label)
                all_good = False
        finally:
            shutil.rmtree(tmp, ignore_errors=True)
    return 0 if all_good else 1


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--verify-gauge", action="store_true",
                    help="拆掉防護,確認這套測試會紅")
    ap.add_argument("-v", "--verbose", action="store_true")
    args = ap.parse_args()

    if args.verify_gauge:
        return verify_gauge()

    started = time.time()
    result = run_all(ROOT)
    for name, ok, detail in result.results:
        if args.verbose or not ok:
            print("%s %s%s" % ("PASS" if ok else "FAIL", name,
                               "  ← " + detail if detail else ""))
    print("\n%d 項檢查,%d 項失敗,%.1f 秒。"
          % (len(result.results), len(result.failed), time.time() - started))
    return 1 if result.failed else 0


if __name__ == "__main__":
    sys.exit(main())
