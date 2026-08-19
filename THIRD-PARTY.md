# 第三方程式碼與出處

這個專案的前端動畫引擎是**建置時**打包進 `public/index.html` 的。
執行時不會連任何外部網站 —— 打包產物直接內嵌在頁面裡,離線也能開。

星數與授權都是用 `gh api` 當場查的(2026-08-18),不是憑印象寫的。

## 打包進頁面的(執行時依賴)

| 專案 | ★ | 授權 | 版本 | 用在哪 |
|---|---|---|---|---|
| [animejs](https://github.com/juliangarnier/anime) | 72,216 | MIT | ^4.5.0 | 動畫引擎:時間軸、緩動、`onScroll` 捲動觸發、`svg` 路徑變形、`stagger` |
| [lenis](https://github.com/darkroomengineering/lenis) | 15,455 | MIT | ^1.3.26 | 慣性平滑捲動 |

兩者的授權全文隨 npm 套件散佈,在 `node_modules/<套件>/LICENSE`。
MIT 要求保留著作權聲明與授權條款,因此本檔案即為散佈時的署名。

## 只用在建置時(不進頁面)

| 專案 | 授權 | 用途 |
|---|---|---|
| [esbuild](https://github.com/evanw/esbuild) | MIT | 打包與壓縮 `src/vendor.js` |
| [Pillow](https://github.com/python-pillow/Pillow) | MIT-CMU | 畫 `public/og.png` 分享卡(`scripts/make_og.py`)|

Pillow **不在 package.json 裡、也沒有 requirements.txt** —— 它只有在要重畫分享卡
那張圖的時候才需要(`pip install pillow`)。圖是產物、進了版控,所以跑伺服器、跑測試、
部署都不需要它;`scripts/make_og.py --check` 只讀 PNG 檔頭,同樣不需要。
字型用系統內建的(Windows 的 Georgia + 新細明體、Linux 的 DejaVu Serif + Noto Serif CJK),
沒有把任何字型檔散佈進這個 repo。

## 評估過但**沒有**採用

寫下來是為了讓後面的人不用重查一次:

| 專案 | ★ | 為什麼不用 |
|---|---|---|
| [shadcn-ui/ui](https://github.com/shadcn-ui/ui) | 121,509 | React + Tailwind,本專案沒有 React 也沒有 CSS 框架 |
| [tailwindcss](https://github.com/tailwindlabs/tailwindcss) | 97,234 | 需要另一套 build,與單檔自包含的方向衝突 |
| [animate.css](https://github.com/animate-css/animate.css) | 82,737 | **Hippocratic License 2.1** —— 非 OSI 認可、附使用限制,放進 MIT 專案會污染授權 |
| [motion](https://github.com/motiondivision/motion) | 33,266 | MIT,但光 `scroll` 就 75KB,能力與 anime.js `onScroll` 重疊 |
| [Hover.css](https://github.com/IanLunn/Hover) | 29,397 | **雙授權,商用需另行付費** |
| [AOS](https://github.com/michalsnik/aos) | 28,060 | MIT,但 anime.js 的 `onScroll` 已經涵蓋 |
| [uiverse-io/galaxy](https://github.com/uiverse-io/galaxy) | 12,082 | MIT。**沒有整包引入**,只參考了幾個純 CSS 形狀手法的做法,實作是重寫的 |

## 自己寫的部分

水滴形附議鈕、波浪切邊、不對稱卡片圓角、gooey 液態濾鏡、極光水池 canvas、
語意化配色系統與 8 色標籤盤,都是這個專案自己寫的原生 CSS/SVG/Canvas,
沒有複製任何第三方原始碼。
