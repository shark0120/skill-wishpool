#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""把願望匯出成 public/wishes.json,讓沒有後端的地方(GitHub Pages)也能唯讀展示。

    python3 scripts/export_static.py                  # 有 DB 就從 DB,沒有就用 data/seed.json
    python3 scripts/export_static.py --db /path/x.db
    python3 scripts/export_static.py --from-seed       # 強制用種子資料

單向資料流:DB(或 seed.json)→ 這支腳本 → public/wishes.json。
**不要手改 public/wishes.json**,下次匯出就沒了。
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

import server  # noqa: E402  (要先把 ROOT 放進 sys.path)

OUT = os.path.join(ROOT, "public", "wishes.json")


def from_db(db_path):
    server.CFG["db"] = db_path
    server.CFG["readonly"] = True  # 匯出不該改動任何東西
    with server.connect() as conn:
        wishes, total = server.list_wishes(conn, sort="new", limit=200)
        return {
            "source": "db",
            "wishes": wishes,
            "total": total,
            "stats": server.stats(conn),
            "round": server.round_payload(conn),
        }


def from_seed(seed_path):
    with open(seed_path, "r", encoding="utf-8") as fh:
        items = json.load(fh)
    wishes = []
    for i, item in enumerate(items, start=1):
        wishes.append({
            "id": i,
            "title": item.get("title", ""),
            "detail": item.get("detail", ""),
            "tags": server.parse_tags(item.get("tags")),
            "author": item.get("author", ""),
            "status": item.get("status", "open"),
            "votes": int(item.get("votes", 0)),
            "skill_url": item.get("skill_url", ""),
            "note": item.get("note", ""),
            "created_at": "2026-01-01T00:00:00Z",
            "updated_at": "2026-01-01T00:00:00Z",
        })
    return {
        "source": "seed",
        "wishes": wishes,
        "total": len(wishes),
        "stats": {
            "wishes": len(wishes),
            "votes": sum(w["votes"] for w in wishes),
            "granted": sum(1 for w in wishes if w["status"] in ("granted", "planned")),
        },
        # 種子資料沒有真的輪次,所以倒數留空 —— 不要編一個假的結算時間出來。
        "round": {
            "cycle_days": server.CYCLE_DAYS_DEFAULT,
            "min_votes": server.MIN_VOTES_DEFAULT,
            "index": None, "started_at": None, "ends_at": None,
            "seconds_left": None, "leader": None, "history": [],
        },
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", default=os.path.join(ROOT, "data", "wishes.db"))
    ap.add_argument("--seed-file", default=os.path.join(ROOT, "data", "seed.json"))
    ap.add_argument("--from-seed", action="store_true")
    ap.add_argument("--out", default=OUT)
    args = ap.parse_args()

    if args.from_seed or not os.path.isfile(args.db):
        payload = from_seed(args.seed_file)
    else:
        payload = from_db(args.db)
    payload["generated_at"] = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    payload["note"] = ("這是唯讀快照,由 scripts/export_static.py 產生,不要手改。"
                       "來源:%s" % payload["source"])

    # newline="\n":專案強制 LF,不然每次匯出整檔都會出現假差異。
    with open(args.out, "w", encoding="utf-8", newline="\n") as fh:
        json.dump(payload, fh, ensure_ascii=False, indent=1)
        fh.write("\n")
    print("寫出 %s(%d 筆,來源 %s)" % (args.out, payload["total"], payload["source"]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
