#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""量尺:直接從 public/index.html 讀出色票,實算 WCAG 對比度。

為什麼要有這支:色票是手寫的十六進位,改一個字元就可能讓輔助文字掉到讀不到,
而這種問題肉眼看不出來(尤其在室外光線下才會現形)。所以每次改顏色都要重算。

它讀的是**真正會送到瀏覽器的那份 CSS**,不是另一份設定檔——這樣就不會出現
「檢查通過但頁面用的是別的顏色」這種假綠燈。

    python3 scripts/check_contrast.py          # 不合格就 exit 1
    python3 scripts/check_contrast.py -v       # 印出每一組的比值
"""

from __future__ import annotations

import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HTML = os.path.join(ROOT, "public", "index.html")

# (前景, 背景, 最低比值, 說明)
# 4.5 = WCAG AA 正文;3.0 = AA 非文字(邊框、焦點框這類要能辨識的 UI 元件)
PAIRS = [
    ("ink", "bg", 4.5, "正文"),
    ("ink", "bg2", 4.5, "正文在次要底色上"),
    ("ink", "card", 4.5, "正文在卡片上"),
    ("soft", "bg", 4.5, "說明文字"),
    ("soft", "card", 4.5, "說明文字在卡片上"),
    ("soft", "bg2", 4.5, "說明文字在次要底色上"),
    ("faint", "bg", 4.5, "輔助文字"),
    ("faint", "card", 4.5, "輔助文字在卡片上"),
    ("faint", "bg2", 4.5, "輔助文字在次要底色上"),
    ("accent", "bg", 4.5, "連結"),
    ("accent", "card", 4.5, "連結在卡片上"),
    ("accent", "bg2", 4.5, "連結在次要底色上"),
    ("accent-ink", "accent", 4.5, "主要按鈕的字"),
    ("good", "card", 4.5, "已實現徽章"),
    ("good", "bg2", 4.5, "已實現徽章在次要底色上"),
    ("warn", "card", 4.5, "錯誤訊息"),
    ("warn", "bg", 4.5, "錯誤訊息在背景上"),
    ("bg", "warn", 4.5, "錯誤提示條的字"),
    ("bg", "ink", 4.5, "一般提示條的字"),
    ("line-strong", "card", 3.0, "輸入框邊框"),
    ("line-strong", "bg", 3.0, "輸入框邊框在背景上"),
    ("focus", "bg", 3.0, "焦點外框"),
    ("focus", "card", 3.0, "焦點外框在卡片上"),
]

TOKEN_RE = re.compile(r"--([a-z0-9-]+)\s*:\s*(#[0-9A-Fa-f]{3,8})")


def srgb_to_lin(channel: float) -> float:
    return channel / 12.92 if channel <= 0.04045 else ((channel + 0.055) / 1.055) ** 2.4


def luminance(hex_color: str) -> float:
    h = hex_color.lstrip("#")
    if len(h) == 3:
        h = "".join(c * 2 for c in h)
    if len(h) not in (6, 8):
        raise ValueError("看不懂的顏色:" + hex_color)
    r, g, b = (int(h[i:i + 2], 16) / 255 for i in (0, 2, 4))
    return (0.2126 * srgb_to_lin(r) + 0.7152 * srgb_to_lin(g) + 0.0722 * srgb_to_lin(b))


def contrast(fg: str, bg: str) -> float:
    a, b = luminance(fg), luminance(bg)
    hi, lo = max(a, b), min(a, b)
    return (hi + 0.05) / (lo + 0.05)


def extract_blocks(css: str):
    """抓出兩套色票:`:root[data-theme=light]` 與 `:root[data-theme=dark]`。

    這兩個手動覆寫區塊是使用者實際按切換鈕後生效的值,也是唯一兩份完整色票
    (bare :root 與 prefers-color-scheme 區塊只是它們的鏡像)。抓不到就直接失敗,
    不要「找不到就跳過」——那會變成永遠不會失敗的檢查。
    """
    out = {}
    for name in ("light", "dark"):
        m = re.search(r":root\[data-theme=" + name + r"\]\s*\{(.*?)\}", css, re.S)
        if not m:
            raise SystemExit("FAIL 在 CSS 裡找不到 :root[data-theme=%s] 區塊" % name)
        tokens = dict(TOKEN_RE.findall(m.group(1)))
        if not tokens:
            raise SystemExit("FAIL :root[data-theme=%s] 區塊裡沒有任何色票" % name)
        out[name] = tokens
    return out


def mirror_check(css: str, themes: dict) -> list:
    """順手比對 bare :root(= 亮色)與 dark media query 有沒有跟手動覆寫脫節。

    脫節的症狀很陰險:系統暗色模式下的顏色跟按鈕切到暗色不一樣,而檢查只看了一邊。
    """
    problems = []
    bare = re.search(r":root\s*\{(.*?)\}", css, re.S)
    if bare:
        for key, value in TOKEN_RE.findall(bare.group(1)):
            want = themes["light"].get(key)
            if want and want.lower() != value.lower():
                problems.append("bare :root 的 --%s=%s 與 light 覆寫 %s 不一致"
                                % (key, value, want))
    dark_media = re.search(r"@media\s*\(prefers-color-scheme:\s*dark\)\s*\{(.*?)\n\}",
                           css, re.S)
    if dark_media:
        for key, value in TOKEN_RE.findall(dark_media.group(1)):
            want = themes["dark"].get(key)
            if want and want.lower() != value.lower():
                problems.append("prefers-color-scheme:dark 的 --%s=%s 與 dark 覆寫 %s 不一致"
                                % (key, value, want))
    return problems


def main() -> int:
    verbose = "-v" in sys.argv or "--verbose" in sys.argv
    try:
        with open(HTML, "r", encoding="utf-8") as fh:
            html = fh.read()
    except OSError as exc:
        print("FAIL 讀不到 %s:%s" % (HTML, exc))
        return 1
    css = re.search(r"<style>(.*?)</style>", html, re.S)
    if not css:
        print("FAIL index.html 裡沒有 <style> 區塊")
        return 1
    css = css.group(1)

    themes = extract_blocks(css)
    failures = []
    checked = 0
    for theme, tokens in themes.items():
        for fg, bg, floor, label in PAIRS:
            if fg not in tokens or bg not in tokens:
                failures.append("%s:色票 --%s 或 --%s 不存在" % (theme, fg, bg))
                continue
            ratio = contrast(tokens[fg], tokens[bg])
            checked += 1
            ok = ratio >= floor
            if verbose or not ok:
                print("%-5s %-11s on %-11s %5.2f:1  (需 %.1f)  %s  %s" % (
                    theme, fg, bg, ratio, floor, "OK  " if ok else "FAIL", label))
            if not ok:
                failures.append("%s:--%s on --%s = %.2f:1,低於 %.1f(%s)"
                                % (theme, fg, bg, ratio, floor, label))

    for problem in mirror_check(css, themes):
        failures.append("色票鏡像不一致:" + problem)

    if failures:
        print("\n對比度檢查失敗 %d 項:" % len(failures))
        for f in failures:
            print("  ✗ " + f)
        return 1
    print("對比度檢查通過:%d 組色票組合、亮暗兩套、色票鏡像一致。" % checked)
    return 0


if __name__ == "__main__":
    sys.exit(main())
