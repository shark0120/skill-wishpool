#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""把 server.py 的分享卡預設值寫回 public/index.html。

    python3 scripts/sync_meta.py           # 寫回去
    python3 scripts/sync_meta.py --check   # 只比對(CI 與 selftest 用)

為什麼需要這一支:分享卡的文案有兩個讀者 ——
  * 完整版:server.py 每次請求現算(換成這台的網址、換成 /w/{id} 那個願望)。
  * 靜態託管:沒有伺服器,爬蟲看到的就是 public/index.html 裡寫死的那一段。
兩邊各改各的遲早會脫節,所以**唯一來源是 server.py 的 meta_block()**,
這一支負責把預設值蓋回 HTML,--check 負責在 CI 抓出脫節。

跟 scripts/build.py 是同一個路子:標記中間的東西是產物,不要手改。
"""

from __future__ import annotations

import argparse
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PAGE = os.path.join(ROOT, "public", "index.html")
sys.path.insert(0, ROOT)

import server  # noqa: E402  (要先把 ROOT 放進 sys.path)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true", help="只比對有沒有脫節,不寫檔")
    args = ap.parse_args()

    with open(PAGE, "rb") as fh:
        page = fh.read()

    found = server._META_BLOCK.search(page)
    if not found:
        print("FAIL public/index.html 裡找不到 <!-- meta:start … meta:end --> 標記")
        return 1

    want = server.meta_block()
    if found.group(0) == want:
        print("OK 分享卡預設值跟 server.py 一致(%d 位元組)" % len(want))
        return 0

    if args.check:
        print("FAIL public/index.html 的分享卡跟 server.py 的 meta_block() 不一樣。")
        print("     跑 python3 scripts/sync_meta.py 重新產生。")
        return 1

    with open(PAGE, "wb") as fh:
        fh.write(page[:found.start()] + want + page[found.end():])
    print("OK 已更新 public/index.html 的分享卡(%d 位元組)" % len(want))
    return 0


if __name__ == "__main__":
    sys.exit(main())
