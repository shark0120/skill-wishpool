#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""畫出分享卡圖 public/og.png(1200×630)。

    python3 scripts/make_og.py            # 重畫
    python3 scripts/make_og.py --check    # 只檢查檔案在不在、尺寸對不對(CI 用)

**這是產物,產一次就進版控** —— 跟 public/index.html 的 vendor 區塊一樣。
只有要改分享卡長相時才需要跑,而跑它需要 Pillow(`pip install pillow`)。
伺服器不需要 Pillow,`--check` 也不需要:它只讀 PNG 檔頭。

為什麼是 PNG 不是 SVG:Facebook、LINE、X、Threads 的爬蟲都不吃 SVG 當 og:image。
這是這個專案唯一一張點陣圖,所以寧可讓它是產物,也不要為了它加執行時依賴。

配色與字型跟著 public/index.html 的亮色模式走(金只用在描邊與漸層,不寫字 ——
金色文字在淺底上過不了 WCAG AA)。字型用系統內建襯線:Latin 走 Georgia、
中文走新細明體,跟頁面上的 `font-family` 堆疊同一個路線。
"""

from __future__ import annotations

import argparse
import math
import os
import struct
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "public", "og.png")
W, H = 1200, 630

# 亮色模式的色票(跟 index.html 的 :root 同一組)
BG = (247, 245, 242)
INK = (23, 23, 23)
SOFT = (79, 79, 79)
FAINT = (101, 95, 87)
ACCENT = (110, 38, 57)
GOLD = (201, 162, 39)

# 字型候選:同一句話裡 ASCII 走第一組、中文走第二組,逐段量寬度接起來。
LATIN_FONTS = [
    "C:/Windows/Fonts/georgia.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSerif.ttf",
    "/System/Library/Fonts/Supplemental/Georgia.ttf",
]
CJK_FONTS = [
    ("C:/Windows/Fonts/mingliu.ttc", 0),          # 新細明體
    ("C:/Windows/Fonts/msjh.ttc", 0),             # 微軟正黑體(退路)
    ("/usr/share/fonts/opentype/noto/NotoSerifCJK-Regular.ttc", 0),
    ("/System/Library/Fonts/Supplemental/Songti.ttc", 0),
]

TITLE = "Skill 許願池"
LEAD = "你想要什麼 AI skill?丟進池子,大家聯署。"
RULE = "每三天結算一次,票最高的那一個就做成 skill。"
FOOT = "skill-tw.com ・ 不用註冊 ・ 不放 cookie"


def first_existing(paths):
    for p in paths:
        path = p[0] if isinstance(p, tuple) else p
        if os.path.isfile(path):
            return p
    return None


def load_fonts(size):
    from PIL import ImageFont
    latin_path = first_existing(LATIN_FONTS)
    cjk = first_existing(CJK_FONTS)
    if not cjk:
        raise SystemExit("FAIL 找不到任何中文字型,改一下 CJK_FONTS 裡的路徑")
    cjk_font = ImageFont.truetype(cjk[0], size, index=cjk[1])
    latin_font = ImageFont.truetype(latin_path, size) if latin_path else cjk_font
    return latin_font, cjk_font


def runs(text):
    """把字串切成「連續 ASCII」與「連續非 ASCII」兩種段落,才能各配各的字型。"""
    out, buf, ascii_mode = [], "", None
    for ch in text:
        mode = ord(ch) < 128
        if ascii_mode is None or mode == ascii_mode:
            buf += ch
        else:
            out.append((buf, ascii_mode))
            buf = ch
        ascii_mode = mode
    if buf:
        out.append((buf, ascii_mode))
    return out


def draw_mixed(draw, xy, text, size, fill, tracking=0):
    """逐段換字型畫一行字,回傳畫完的總寬度。tracking 是字距(px)。"""
    latin, cjk = load_fonts(size)
    x, y = xy
    start = x
    for chunk, is_ascii in runs(text):
        font = latin if is_ascii else cjk
        for ch in chunk:
            draw.text((x, y), ch, font=font, fill=fill)
            x += draw.textlength(ch, font=font) + tracking
    return x - start


def wash(base, center, radius, rgba):
    """一團柔和的光暈:小圖上畫實心圓再放大,邊緣自然糊掉(不用裝濾鏡)。"""
    from PIL import Image, ImageDraw, ImageFilter
    small = Image.new("RGBA", (W // 6, H // 6), (0, 0, 0, 0))
    d = ImageDraw.Draw(small)
    cx, cy, r = center[0] // 6, center[1] // 6, radius // 6
    d.ellipse([cx - r, cy - r, cx + r, cy + r], fill=rgba)
    small = small.filter(ImageFilter.GaussianBlur(r / 2.2))
    base.alpha_composite(small.resize((W, H), Image.LANCZOS))


def render():
    from PIL import Image, ImageDraw

    img = Image.new("RGBA", (W, H), BG + (255,))
    # 兩團極光,跟頁面背景那兩團同一個角色:金在左上、酒紅在右下。
    wash(img, (140, 74), 600, GOLD + (36,))
    wash(img, (1090, 580), 540, ACCENT + (24,))

    draw = ImageDraw.Draw(img)

    # 髮絲級金框:外框 1px,內框再退 10px 一條更淡的,做出「兩道細線」的層次。
    draw.rectangle([40, 40, W - 41, H - 41], outline=GOLD + (150,), width=1)
    draw.rectangle([50, 50, W - 51, H - 51], outline=GOLD + (70,), width=1)

    # 水波標記(跟 favicon 同一組線條)
    x0, y0 = 96, 104
    for row in range(3):
        y = y0 + row * 17
        pts = []
        for i in range(0, 73):
            t = i / 72
            pts.append((x0 + t * 72, y + math.sin(t * math.pi * 2) * 7))
        draw.line(pts, fill=ACCENT + (235,), width=3, joint="curve")

    # 標題:寬字距的襯線大標
    draw_mixed(draw, (96, 196), TITLE, 96, INK + (255,), tracking=5)

    # 標題底下一條短金線
    draw.line([(100, 330), (232, 330)], fill=GOLD + (210,), width=2)

    draw_mixed(draw, (96, 372), LEAD, 40, SOFT + (255,), tracking=1)
    draw_mixed(draw, (96, 436), RULE, 40, SOFT + (255,), tracking=1)

    # 底線資訊
    draw.line([(96, 520), (W - 96, 520)], fill=GOLD + (90,), width=1)
    draw_mixed(draw, (96, 546), FOOT, 30, FAINT + (255,), tracking=1)

    # 右下角的漣漪:三圈同心弧,呼應「一滴水落進池子」。圓心壓在畫面外,只露上緣,
    # 並且裁在內框裡面 —— 讓它看起來是被框切掉的,不是畫超出去。
    ripple = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    rd = ImageDraw.Draw(ripple)
    cx, cy = W - 128, H + 12
    for i, r in enumerate((104, 158, 212)):
        alpha = 120 - i * 32
        rd.arc([cx - r, cy - r, cx + r, cy + r],
               start=192, end=348, fill=GOLD + (alpha,), width=2)
    mask = Image.new("L", (W, H), 0)
    ImageDraw.Draw(mask).rectangle([52, 52, W - 53, H - 53], fill=255)
    img.alpha_composite(Image.composite(ripple, Image.new("RGBA", (W, H), (0, 0, 0, 0)), mask))

    img.convert("RGB").save(OUT, "PNG", optimize=True)
    return OUT


def png_size(path):
    """只讀 PNG 檔頭拿寬高 —— 這樣 --check 不需要 Pillow。"""
    with open(path, "rb") as fh:
        head = fh.read(24)
    if len(head) < 24 or head[:8] != b"\x89PNG\r\n\x1a\n":
        raise ValueError("不是 PNG")
    return struct.unpack(">II", head[16:24])


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true",
                    help="只檢查產物在不在、尺寸對不對(不需要 Pillow)")
    args = ap.parse_args()

    if args.check:
        if not os.path.isfile(OUT):
            print("FAIL 找不到 public/og.png —— 跑 python3 scripts/make_og.py 產生")
            return 1
        try:
            w, h = png_size(OUT)
        except (OSError, ValueError) as exc:
            print("FAIL public/og.png 讀不出來:%s" % exc)
            return 1
        if (w, h) != (W, H):
            print("FAIL public/og.png 是 %d×%d,應該是 %d×%d" % (w, h, W, H))
            return 1
        print("OK public/og.png %d×%d,%.0f KB" % (w, h, os.path.getsize(OUT) / 1024))
        return 0

    try:
        import PIL  # noqa: F401
    except ImportError:
        print("FAIL 要重畫分享卡需要 Pillow:pip install pillow")
        print("     (只是要跑伺服器的話不用 —— og.png 已經在版控裡了)")
        return 1
    path = render()
    w, h = png_size(path)
    print("OK 畫好了 %s(%d×%d,%.0f KB)" % (path, w, h, os.path.getsize(path) / 1024))
    return 0


if __name__ == "__main__":
    sys.exit(main())
