#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""把 esbuild 打包好的第三方動畫引擎內嵌進 public/index.html。

    npm run build          # esbuild 打包 → 這支內嵌(Linux / macOS)
    npm run build:win      # Windows 版,只差 python 執行檔名稱
    python3 scripts/build.py --check   # 只檢查有沒有脫節,不寫檔

為什麼要內嵌而不是 <script src>:
  1. 執行時零外部請求 —— 使用者的瀏覽器不會連任何 CDN,離線也能開。
  2. CSP 用的是 inline 雜湊,外部檔案要嘛開洞要嘛加一堆 hash。
  3. 單檔仍然「下載下來就能用」。

**public/index.html 的 vendor 區塊是產生的,不要手改** —— 兩條標記中間的東西
每次 build 都會被覆寫。標記以外的地方(CSS、頁面結構、應用程式碼)仍然是手寫的來源。
"""

from __future__ import annotations

import argparse
import hashlib
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PAGE = os.path.join(ROOT, "public", "index.html")
BUNDLE = os.path.join(ROOT, "build", "vendor.min.js")

START = "<!-- vendor:start 由 scripts/build.py 產生,不要手改 -->"
END = "<!-- vendor:end -->"


def build_block(bundle: str) -> str:
    digest = hashlib.sha256(bundle.encode("utf-8")).hexdigest()[:12]
    return (
        START + "\n"
        "<script>/* anime.js + lenis,由 esbuild 打包 · 見 THIRD-PARTY.md · "
        "sha256:%s */\n%s\n</script>\n" % (digest, bundle.strip()) + END
    )


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true",
                    help="只比對有沒有脫節,不寫檔(CI 用)")
    args = ap.parse_args()

    try:
        with open(BUNDLE, "r", encoding="utf-8") as fh:
            bundle = fh.read()
    except OSError:
        print("FAIL 找不到 %s —— 先跑 esbuild(npm run build 會自己做)" % BUNDLE)
        return 1
    if len(bundle) < 1000:
        print("FAIL 打包結果只有 %d 個位元組,看起來不對" % len(bundle))
        return 1

    with open(PAGE, "r", encoding="utf-8") as fh:
        page = fh.read()

    # 標記找不到就直接失敗,不要「找不到就跳過」—— 那會變成一支永遠會綠的建置。
    if page.count(START) != 1 or page.count(END) != 1:
        print("FAIL public/index.html 裡的 vendor 標記不是剛好各一個。"
              "應該長這樣:\n  %s\n  ...\n  %s" % (START, END))
        return 1
    head, rest = page.split(START, 1)
    _, tail = rest.split(END, 1)
    fresh = head + build_block(bundle) + tail

    if args.check:
        if fresh != page:
            print("FAIL public/index.html 的 vendor 區塊跟 build/vendor.min.js 脫節了。")
            print("     跑 `npm run build` 之後再 commit。")
            return 1
        print("vendor 區塊同步(%.1f KB)。" % (len(bundle) / 1024))
        return 0

    if fresh == page:
        print("vendor 區塊沒有變動(%.1f KB)。" % (len(bundle) / 1024))
        return 0

    # newline="\n":專案強制 LF,不然每次 build 整檔都會出現假差異。
    with open(PAGE, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(fresh)
    print("已內嵌 vendor 區塊:%.1f KB → %s(整頁 %.1f KB)"
          % (len(bundle) / 1024, os.path.relpath(PAGE, ROOT), len(fresh) / 1024))
    return 0


if __name__ == "__main__":
    sys.exit(main())
