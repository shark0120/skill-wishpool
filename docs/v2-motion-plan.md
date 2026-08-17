# v2「全站動態 · 打破常規形狀」工作流程

目標(使用者原話):**找 GitHub 上高分 UI 相關組件放入、網站全部動態、打破常規 UI 形狀。**

---

## 0. 先講一個硬衝突,這個不決定就不能動工

這個專案現在對外承諾的是**零依賴、零外部請求**:

- `README.md` 寫「不用 npm、不用 Docker」「程式碼本身零外部請求」
- `CONTRIBUTING.md` 寫「零依賴……是為了讓任何人 clone 下來就能跑、離線也能跑」
- **CI 有一關叫「零依賴檢查」**:偵測到 `package.json` 或 `requirements.txt` 直接失敗
- 自我測試有一條掃 `index.html` 有沒有外連(`//cdn.`、`fonts.`、`unpkg`、`jsdelivr`)
- CSP 用 inline 雜湊,任何外部 `<script>` 都會被瀏覽器擋掉

「把 GitHub 組件放進來」的正常做法(npm / CDN)**會同時撞到上面五條**。所以要嘛換做法,要嘛改承諾。

### GitHub 實際查到的候選(星數與授權都是 `gh api` 當場查的,不是印象)

| 專案 | ★ | 授權 | 能不能用 |
|---|---|---|---|
| shadcn-ui/ui | 121,509 | MIT | ✗ React + Tailwind,本專案沒有 React 也沒有 build |
| tailwindlabs/tailwindcss | 97,234 | MIT | ✗ 需要 build step |
| **animate-css/animate.css** | 82,737 | **Hippocratic 2.1** | ✗ **非 OSI 授權、附使用限制**,放進 MIT 專案會污染授權 |
| juliangarnier/anime | 72,216 | MIT | △ 純 JS 可內嵌,但要 vendor 進來(約 17KB) |
| motiondivision/motion | 33,266 | MIT | △ 同上,主要為 React 設計 |
| **IanLunn/Hover** | 29,397 | **雙授權,商用要付費** | ✗ |
| michalsnik/aos | 28,060 | MIT | △ 可內嵌,但現代瀏覽器有原生 scroll-driven animation 可取代 |
| darkroomengineering/lenis | 15,455 | MIT | △ 平滑捲動;會接管捲動行為,無障礙要小心 |
| **uiverse-io/galaxy** | 12,082 | **MIT** | ✓ **純 HTML/CSS 組件庫,無框架、可逐個挑、附署名即可** |
| magicuidesign/magicui | 21,985 | MIT | ✗ React,但**效果可以照著重寫**(想法不受著作權保護,程式碼才受) |

### 兩條路

**A 案(建議):維持零依賴,把效果「移植」進來。**
挑 MIT 授權的來源(uiverse galaxy、magicui 的效果概念、anime.js 的緩動曲線),用原生 CSS/SVG/Web Animations API 重寫成 inline 程式碼,在 `THIRD-PARTY.md` 逐條署名與標授權。
→ 承諾不變、CI 不用改、離線仍可跑、單檔仍可下載即用。代價:我要自己實作,效果由我保證。

**B 案:接受依賴,加 build step。**
`package.json` + vendor 打包成單一 inline bundle。
→ 要**刪掉 CI 的零依賴檢查**、改寫 README/CONTRIBUTING 的承諾、頁面體積從 ~55KB 漲到 150KB+。
→ 好處:直接用現成的成熟動畫引擎。

---

## 1. 這次要做什麼(具體清單)

### 打破常規 UI 形狀

| 現在 | 改成 | 手法 |
|---|---|---|
| 附議鈕是圓角方塊 | **水滴形** | `clip-path` 水滴路徑;命中區另外用 padding 撐回 44px |
| 水池是矩形框 | **波浪切邊** | SVG `mask-image` 波形,上下緣起伏 |
| 願望卡都一樣的圓角 | **不對稱圓角**,交錯左右 | `border-radius: 28px 6px 28px 6px`,偶數卡鏡像 |
| 聯署框是普通方框 | **會轉的漸層描邊** | `conic-gradient` + `@property` 角度動畫 |
| 標籤是膠囊 | **squircle** | 多值 `border-radius` / `mask` |
| 卡片與附議鈕分離 | **液態黏連(gooey)** | SVG filter `feGaussianBlur`+`feColorMatrix` |

### 全站動態

- 捲動進場:原生 `animation-timeline: view()`,不支援時退回 IntersectionObserver
- 數字滾動:統計與倒數用 count-up,不是直接跳
- 水池:加流體擾動與滑鼠/觸控互動漣漪
- 卡片:hover/press 傾斜與光暈(桌機),觸控裝置只留 press 回饋
- 標籤列:選中時液態變形
- 列表換頁/篩選:View Transitions API(有支援才啟用)
- 背景:極光漸層緩慢流動

---

## 2. 工作流程(每一階段都有閘門,沒過不進下一階段)

| # | 階段 | 產出 | 閘門 |
|---|---|---|---|
| 0 | 決策 | A 案或 B 案 | **使用者決定,這步沒答案不動工** |
| 1 | 蒐集與授權 | `THIRD-PARTY.md`:每個借用的效果標來源、星數、授權、我改了什麼 | 沒有 OSI 授權的一律不進來 |
| 2 | **先造尺** | 擴充量尺:動效預算、reduced-motion 靜態驗證、異形命中區、FPS/長任務、頁面體積上限 | 尺要先能抓到「動畫爆掉」才准開始改 |
| 3 | 形狀 | 水滴鈕、波浪切邊、不對稱卡、gooey、旋轉描邊 | 375px 無橫向捲動、命中區 ≥44×44、對比不變 |
| 4 | 動態 | 捲動進場、數字滾動、互動漣漪、View Transitions | 動效總數 ≤ 主要三類、單次 ≤0.4s、無無限閃爍 |
| 5 | 驗收 | 375/768 × 亮/暗 × reduced-motion 六種組合實測 | 對比 0 不合格、console 0 錯誤、FPS 不低於 50 |
| 6 | 發佈 | 線上機器跑 selftest → commit → push → 部署 → 線上實測 | 其他 30 幾個站狀態不變 |

---

## 3. 不可退讓的線(不管走哪一案)

1. **`prefers-reduced-motion` 必須整套停下來變靜態**,不是變慢。
2. **異形不能吃掉命中區**:視覺可以是水滴,可點區域仍要 ≥44×44px。
3. **對比不能因為動畫背景而失守**:文字不疊在會動的漸層上,或該處單獨量測。
4. **不准假動態**:沒有真實資料在變的地方不做假進度、假跳動。
5. **手機優先**:所有效果先在 375px 驗;桌機專屬效果(傾斜、磁吸)用 `hover: hover` 隔離。
6. **量尺先於改動**:第 2 階段沒做完不進第 3 階段。

---

## 4. 我預期會踩到的坑(先寫下來,踩到才不會當成新發現)

- `clip-path` 會把 `box-shadow` 和 `outline` 一起切掉 → 焦點框會消失,要改用內描邊或 `filter: drop-shadow`。
- gooey filter 在整層套用會讓**文字也被模糊** → 只能套在純裝飾層,文字必須在 filter 之外。
- `backdrop-filter` 與 `filter` 在 iOS Safari 上會觸發整層重繪 → 平板可能掉幀,要量。
- `animation-timeline` 支援度不完整 → 一定要有 IntersectionObserver 退路,而且退路要真的測過(不能只寫在註解裡)。
- 動畫改 `width/height/top/left` 會 layout thrash → 只准動 `transform` 與 `opacity`。
- 頁面體積:目前 ~55KB。B 案會破 150KB,單檔下載即用的賣點會變弱。

---

## 5. 決定與結果(2026-08-18)

**選了 B 案**:接受依賴、加 build step。實際落地成這樣 ——

- 依賴只在**建置時**:`esbuild` 把 anime.js + lenis 打包成一份 IIFE,
  `scripts/build.py` 把它內嵌進 `public/index.html`。
  **執行時仍然零外部請求**,離線可開,CSP 不用開洞,自架者也不需要 npm。
- CI 的「零依賴檢查」改成兩件更有意義的事:
  1. `build` job 重新打包並比對版控裡的 HTML(`build.py --check`),證明沒有人手改 vendor 區塊;
  2. 掃整頁不准出現任何 CDN 網址;
  3. 每個執行時依賴都必須列進 `THIRD-PARTY.md`,否則失敗。
- README / CONTRIBUTING 的承諾改寫成精確版本:「跑起來零依賴、執行時零外部請求;
  只有要改動畫引擎才需要 npm」。
- 沒有採用 `motion`(光 scroll 就 75KB,與 anime.js `onScroll` 重疊)。
  最後連 anime 的 `onScroll`、`svg`、`createTimer` 也拿掉,捲動觸發改用原生
  IntersectionObserver:bundle 從 75.8KB → **60.6KB**,整頁 118KB。

### 實際做出來的

形狀:水池波浪切邊(SVG clipPath)、附議鈕有機水滴形、願望卡左右交錯的不對稱圓角、
聯署框會轉的三色漸層描邊(`@property --ang`)、斜角標籤與按鈕、致謝卡的漸層描邊。

動態:lenis 慣性捲動、背景兩團極光緩慢漂移變形、卡片捲動進場(IntersectionObserver
+ anime stagger)、統計數字滾動、附議水滴回彈、CTA 掃光、canvas 三色極光水池。

響應式:320 / 768 / 1280 實測 —— 手機單欄、桌機「釘住側欄 402px + 主欄 796px +
卡片兩欄」、≥110rem 三欄;root 字級 `clamp(16px, .94rem + .22vw, 17.5px)` 流動,
下限鎖 16px(再小 iOS 聚焦輸入框會自己放大整頁)。

### 過程中自己違規一次

第一版把附議鈕做成持續變形的 `border-radius` 動畫 —— 列表上 12 張卡就是 12 個
每幀重繪的無限動畫,違反自己在第 3 節寫的「只動 transform 與 opacity」。
拿掉了,形狀留著,動感移到按下去那一下。並補了一條量尺:手寫 CSS 裡的
`infinite` 不准超過 4 個。
