# UI 架構指令 — v2 動效改版

給:正在做 v2「全站動態 · 打破常規形狀」的那個對話窗
出自:UI 架構師
版本:2026-08-18 04:30(**第二版,第一版的行號與部分數字已經作廢,見文末「修訂」**)

---

## 讀之前:兩件會影響你怎麼用這份文件的事

**一、這份文件不引用行號,只引用內容錨點。**
我第一版寫的時候檔案是 1620 行,寫完是 1683 行 —— 你在我稽核的期間一直在改。
行號在這個專案現在是**會騙人的參照**。下面每一條都給選擇器或函式名,你自己 grep。

**二、我重量過,所以有些話跟第一版不一樣。**
附議鈕被拉長那條你已經修掉了(現在 58×66,正確)。
掃光壓對比那條因為你把色票整組換暗,現在勉強站在線上(4.52:1,離 4.5 只剩 0.02)。
但**換上去的六角形帶來了更嚴重的問題**,見 P0-1。

---

## 現況

- `selftest.py` 102 項 0 失敗、`check_contrast.py` 76 組通過、頁面 136KB —— **全綠**。
- 我把站開起來,用 1px 網格做真正的命中測試、算最大內接正方形、逐一量色票色相。
- 另外跑了一輪六個面向的對抗式代碼稽核:提出 36 條,**36 條全部通過反駁驗證**。
- 結論不變,而且更硬:**你的尺全綠是因為它沒有一項在量畫面。**

---

## P0 —— 這三條在你自己的紅線上,修完才准加新東西

### P0-1 六角形把附議鈕的命中區削到 42×42

現在的 `.vote` 是 `clip-path:polygon(50% 0,100% 26%,100% 74%,50% 100%,0 74%,0 26%)`,盒子 58×66。

我在瀏覽器裡用 `elementFromPoint` 對整個按鈕做 1px 網格掃描,再用動態規劃算最大全命中矩形:

| 量到的 | 值 |
|---|---|
| 盒子 | 58 × 66 |
| **最大內接正方形(全部可點)** | **42 × 42** |
| 最大內接矩形 | 54 × 35 |
| 可點面積 | 2832 / 3828 格 = **74%** |
| 四個角 | 全部**點不到**(落到底下的 `li.wish`) |

紅線第 2 條寫的是「異形不能吃掉命中區:視覺可以是水滴,可點區域仍要 ≥44×44px」。
**42 < 44。** 而且這是在 `min-height:66px` 已經放大過之後的結果 —— 六角形上下各切掉 26%,
數學上要讓內接正方形達到 44,盒子高度得到 **73px 以上**。

`clip-path` 同時也把 `outline` 切掉了,所以你把焦點框改成了 `outline:none` + inset 陰影 ——
那是被形狀逼出來的妥協,而妥協又生出了 P0-2。**根因是形狀套在 button 本身,不是套在裝飾層。**

**改法(要的是這個,不是把 min-height 加大)**:形狀與命中區分開。

```css
.vote{position:relative;isolation:isolate;clip-path:none;background:transparent}
.vote::before{content:'';position:absolute;inset:0;z-index:-1;
              clip-path:polygon(50% 0,100% 26%,100% 74%,50% 100%,0 74%,0 26%);
              background:var(--bg)}
```

button 本身回到未裁切的矩形 → 命中區 58×66 全可點、`outline` 不再被切、
全域的 `:focus-visible` 直接沿用,P0-2 一併消失。
視覺完全不變 —— 使用者看到的還是那顆寶石。

### P0-2 已附議的按鈕,焦點框跟底色同一個顏色

- `.vote:focus-visible{outline:none;box-shadow:inset 0 0 0 2px var(--focus)}`
- `.vote[aria-pressed=true]{background:var(--accent)}`
- 實測 `--focus` 與 `--accent` **是同一個值**(`#6E2639`)

已經附議過的人用鍵盤 Tab 到那顆按鈕,焦點框畫在同色的底上 → **完全看不見**。
一個站不需要很多鍵盤使用者才會出事,一個就夠了,而且他不會回報,他只會走掉。

**改法**:P0-1 修好之後 `outline` 就不再被切,直接刪掉 `outline:none` 那行,沿用全域的
`:focus-visible{outline:2px solid var(--focus);outline-offset:2px}` —— 外框畫在形狀**外面**,
底色是什麼都不影響。若堅持要 inset,就得另立 `--focus-ring`,不能跟語意色共用 token。

順便補一段 Windows 高對比模式的備援(現在全檔一條 `forced-colors` 都沒有):

```css
@media (forced-colors:active){ .vote:focus-visible{outline:3px solid Highlight;outline-offset:2px} }
```

### P0-3 will-change 永久掛在每一張卡上

`.list .wish{will-change:transform,opacity}` 是無條件的 CSS 規則,
唯一收回它的地方是 `MOTION.reveal` 的 `onComplete`。

三條路徑走不到 `onComplete`:reduced-motion(函式第一行 return)、引擎沒載到(同上)、
1.2 秒保險那條(只寫 opacity / translateY / scale,**沒收 will-change**)。

375px 實測:**10 張卡,10 個 computed `will-change` 都還是 `transform, opacity`,inline 全空。**

而且 375px 下 `#list` 的文件座標 top = 848.8px,視窗只有 812 —— **第一屏一張卡都進不了
IntersectionObserver**,永遠是 1.2 秒保險在收尾。也就是說:
**「捲動進場」這個第 4 階段的主打動效,在手機上從來沒有播過。**
1280×800 也只有第一列會動,第二列之後被 fallback 無差別 `unobserve` 吃掉。

**改法**:
1. 刪掉 CSS 那條 `will-change`,改由 `reveal()` 在動畫**開始前**用 CSSOM 加。
2. `onComplete` **和** 1200ms fallback **兩條路徑**都要設回 `auto`。
3. fallback 不要無差別 `unobserve`:只對「還在 DOM、仍透明、而且**當下在視窗內**」的補顯示,
   不在視窗內的留著繼續觀察,捲到才進場。
4. `!on()` 的 early return 之前,先把所有節點的 will-change 設回 auto。

---

## P1 —— 效能與可用性,P0 之後接著做

### 1. 背景層現在是三層全視窗 fixed,最底下那層每幀重新光柵化

`body::before`(漸層,z-index:-3)+ `#bg-blobs`(SVG,-2,**`filter:blur(3px)`**)
+ `body::after`(顆粒貼圖,-1)。三層疊著,最底下那層由 anime 無限 loop 動 SVG `<path>` 的 transform。

- SVG 子元素的 transform **不會**被提升成合成層 → 內容一變,整層要重新光柵化,再重套模糊。
- 實測位移不是小幅度:`viewBox="0 0 100 100"` + `preserveAspectRatio="none"`,
  1 user unit = 視窗寬的 1%,量到的 bounding box 位移是 **上百 CSS px**、尺寸長大四百多 px。
  也就是每一幀的失效區域就是**整個視窗**。
- 沒有任何停止條件:捲到看不見不停、`visibilitychange` 不停、
  使用者中途開 reduced-motion 只有 lenis 會停(`reduce` 的 change 監聽只 destroy lenis)。
- 你在 `v2-motion-plan.md` §4 自己就預測過「`filter` 在 iOS Safari 會觸發整層重繪」。
- 你也在同一份計畫裡為了**一模一樣的理由**拿掉了附議鈕的每幀重繪動畫。這個 loop 違反同一條規則。
- blur 從 2px 漂到 3px,而三條檢查全部無感 —— 這是 P2 那把尺沒造的直接後果。

**改法**:兩團色改成兩個 `<div>` + `radial-gradient`(漸層本身就有柔邊),
`filter:blur` 拿掉,對 div 動 transform 並加 `will-change:transform`(**只有這兩個元素**),
或乾脆改成 CSS/WAAPI 動畫不走 anime 每幀寫 inline style。
再用 `@media (pointer:coarse)` 在手機/平板整層關掉。
`backdrop()` 補上 `visibilitychange`、IntersectionObserver、`reduce` change 三個停止條件。

> **這裡有一條架構原則**:`pool` canvas 那支寫得很好 —— visibility 停、IO 停、
> reduced-motion 停、背景分頁先畫一格靜態。`MOTION` 這邊一條都沒有。
> **一個專案不該有兩套動畫生命週期紀律,一套嚴一套沒有。**
> 把 pool 的生命週期抽成共用的 `lifecycle(start, stop)`,兩邊都掛上去。

### 2. 桌機/平板橫向:sticky 側欄比視窗高,「丟進池子」被釘在畫面外

`.rail` 是 `position:sticky` 且包住整個 `.compose` 表單。展開表單後 rail 高於視窗,
sticky 釘住的是頂端 → 送出鈕落在視窗下方,而且**不會跟著捲** ——
使用者得把整個願望列表滑完才看得到那顆按鈕。

**改法**:給 sticky 加高度條件(`@media (min-width:60rem) and (min-height:52rem)`),
或 `.rail:has(.compose:not([hidden])){position:static}`。
不要用 `max-height` + 內部捲動,那會生出第二條捲軸。

### 3. Lenis 在手機/平板完全不生效,卻在那裡掛 non-passive 觸控監聽

`new Lenis({syncTouch:false})` → 觸控裝置的捲動完全走原生,平滑一點都吃不到。
但它仍然在 `window` 上掛了 non-passive 的 touch 監聽,每一次觸控捲動都要多跑一次 JS。
**主要裝置(平板)付了成本、拿到零好處。**

**改法**:`smoothScroll()` 開頭加
`if (!matchMedia('(hover:hover) and (pointer:fine)').matches) return;`
觸控裝置一個監聽都不掛、rAF 迴圈也不起來;桌機滾輪平滑不受影響。

順帶:那個手寫的 `const tick = t => { lenis.raf(t); requestAnimationFrame(tick); }` 沒有停止機制。
使用者在頁面開著時打開「減少動態效果」→ `lenis.destroy()` 之後 tick 還在跑 → **未捕捉的 TypeError**,
而且之後 lenis 回不來。改成存 rafId、tick 內先 `if(!lenis) return`,或直接用 Lenis 內建的 `autoRaf`。

### 4. anime 留下的 inline transform 永久蓋掉桌機 hover 手感

`reveal` / `press` / `pop` 收尾時 inline 還留著 `transform: translateY(0) scale(1)`,
特異性永遠贏過 `.wish:hover{transform:translateY(-3px)}` 這類 CSS 規則。
**附議鈕按過一次,之後就再也不會放大了。**

**改法**:每個動畫收尾都把 transform 還給 CSS —— `node.style.transform = ''`
(或 `lib.anime.utils.cleanInlineStyles(nodes)`),`reveal` 的兩條收尾路徑、`press`、`pop` 都要。

### 5. 螢幕閱讀器會被念爆

- `<ul id="list">` 整包是 `aria-live="polite"` → **搜尋每打一個字就把整份列表重念一遍**。
- `#stats` 也是 live 區域,而 `countTo` 是逐格改 `textContent` → 一次更新約 **111 次朗讀**。
- 關閉許願表單不還焦點,鍵盤使用者當場失去位置。

**改法**:`aria-live` 從 `#list` / `#stats` 拿掉,改成一個 `role="status"` 的 `.sr` 狀態列,
渲染完只寫一句摘要(「找到 12 個願望,依熱門排序」);列表本身用 `aria-busy` 包。
`countTo` 期間讓數字節點對輔具隱形,結束才寫一次。
`closeCompose` 結尾 `$('cta').focus()`,送出成功後把焦點送到新卡片。

---

## P2 —— 量尺:第 2 階段沒過就進了第 3–5 階段

計畫書 §2 白紙黑字:「**尺要先能抓到『動畫爆掉』才准開始改**」,要求五把尺。
實際造出來一把半,而且沒有一把在量畫面:

| 檢查 | 它真正在量什麼 | 會通過但畫面壞掉的實例(都是現在檔案裡真的發生的) |
|---|---|---|
| `app.count("infinite") <= 4` | `infinite` 這個字在手寫 CSS 出現幾次 | 兩個 `loop:true` 的 anime 動畫**完全數不到**;blur 從 2px 漂到 3px 無感;附議鈕命中區掉到 42 無感 |
| `"prefers-reduced-motion:reduce" in app` | 那個字串存在 | **把整個 `@media` 區塊刪掉,102 項仍然全綠** —— 因為 JS 裡的 `matchMedia('(prefers-reduced-motion: reduce)')` 就滿足了這個字串 |
| `< 200KB` | 位元組數 | 這條有意義,留著 |

**「異形命中區」與「FPS/長任務」這兩把根本沒造,而 P0-1 正好就是它們該抓到的東西。**
尺沒造 → 缺陷通過 → 102 項全綠交付。這是因果,不是運氣。

而且這三條**沒有進 `--verify-gauge` 的反向對照**,結構上也進不去
(`verify_gauge` 現在寫死只會突變 `server.py`)。**一把不會紅的尺不是尺。**

**指令 —— 這五件做完才准繼續加效果:**

1. **反向對照先擴到 HTML。** `verify_gauge` 改吃 `(檔名, 錨點, 替換)` 三元組,
   加一張 `HTML_MUTATIONS`,至少四條:刪掉整個 `@media (prefers-reduced-motion)` 區塊;
   把區塊內的 `animation:none!important` 換成 `animation-duration:6s!important`;
   給 `.vote` 加一條吃掉命中區的 clip-path;把 blur 加到 12px。
   **沒有這一步,底下四把尺都不算數。**
2. **reduced-motion 改成解析區塊內容**:用 regex 從 `<style>` 切出該 `@media` 區塊,
   切不到直接 FAIL(不要「找不到就跳過」);區塊內必須含 `animation:none!important`
   與 `transition:none!important`;`<style>` 裡所有出現 `infinite` 的選擇器都要被該區塊覆蓋。
3. **命中區尺**(Playwright/CDP):對 `button, a[href], summary, [role=button]` 逐一取 rect,
   把 `border-radius` / `clip-path` 算進去,求**最大內接軸對齊正方形** ≥44px。
   375 / 768 / 1194 三個寬度各跑一次。我今天是手動算的,你要把它變成腳本。
4. **動效預算改成量螢幕上真的在跑的東西**:
   `document.getAnimations().filter(a => a.playState==='running' && a.effect.getComputedTiming().iterations===Infinity)`
   加上 JS 側的 `loop:true` 計數(現在完全沒被算到)。字串計數降級成輔助檢查,
   順便把掃描範圍收窄到 `<style>` 之內,別再掃 JS 與註解。
5. **FPS / 長任務**:掛 `PerformanceObserver({type:'longtask'})`,載入後閒置 8 秒 + 捲到底一次,
   要求 longtask 總時長 <200ms、最長單筆 <100ms,平均幀距 <20ms。門檻先量現值再留 20% 餘裕。

另外 **`check_contrast.py` 要加疊層模式**:對有半透明覆蓋層的元件把覆蓋色合成上去再量。
`.wish-cta::after` 的掃光現在把白字對 `--c-aurora` 壓到 **4.52:1** —— 過了,但只多 0.02。
**任何人把色票調亮一點點就會無聲跌破 4.5,而現在沒有任何一把尺看得到這件事。**

---

## P3 —— 架構(尺造好之後再動,不然改壞了不知道)

### 1. CSS 已經疊到第三層覆寫,而且第二層整層失效

現在是「元件定義 → 打破常規形狀層 → 鎏金層」三層,後面推翻前面。實際後果:

- **「打破常規形狀」那整層的圓角規則已經被第三層全部抹平**,
  但解釋為什麼要這樣做的整段註解還留在原地 —— 讀的人會照著一份已經不生效的說明去改。
- `.vote[aria-pressed=true]` 的舊 blob 圓角特異性贏過新層的 `border-radius:0`
  → **附議之後按鈕形狀會變**。這就是漏網的第一個受害者。
- `reduced-motion` 區塊裡有一行 `.vote` 是舊圓角的複製品
  → 開「減少動態」的人看到跟別人**不一樣的按鈕形狀**。

**指令**:用 `@layer` 把覆寫關係宣告出來,不要靠「誰寫在後面」:

```css
@layer reset, tokens, layout, components, shape, motion, a11y;
```

a11y 層永遠贏 → `@media (prefers-reduced-motion)` 裡的 `*{animation:none!important}`
可以把 `!important` 拿掉(那個 `*` + `!important` 是現在唯一擋得住的手段,但它同時也擋掉未來所有合法例外)。
`reduced-motion` 區塊裡**只准放「把會動的東西關掉」的宣告**,不准重述任何形狀或顏色 ——
每重述一次就多一份會漂移的副本。
CSP 只允許單一 `<style>` 雜湊,所以不能拆檔 —— `@layer` 剛好不需要拆檔。

### 2. 三條桌機 media query 從來沒生效過

「超高響應式」整塊寫在元件定義**之前**,被後面的 mobile 基準值以同權重蓋掉。
實測 `#pool{height:clamp(110px,11vw,160px)}` 是死碼,桌機吃到的是 mobile 的 `clamp(76px,16vw,116px)`。

這種錯誤肉眼掃不出來。**指令**:把響應式整塊搬到元件定義之後(或用 `@layer`),
搬完重量三個值;並在 selftest 加一條:解析 `<style>`,同一組「選擇器+屬性」若在某個
media query 之後又以相同或更高特異性出現 → FAIL。

### 3. 語意色系統已經塌了,但圖例還寫著舊的

CSS 開頭那段圖例寫「`--accent` 水藍 / `--c-aurora` 極光紫 / `--c-flare` 焰橘」。
實測現在的值:

| token | 值 | 實際色相 |
|---|---|---|
| `--accent` | `#6E2639` | 344°(絳紅,不是水藍) |
| `--c-aurora` | `#4A3F35` | 29°(**棕色,不是極光紫**) |
| `--c-flare` | `#7B5D18` | 42°(金) |
| `--warn` | `#8C3A1E` | 15° |
| `--good` | `#2F5D3A` | 134° |

六個語意色有**四個擠在 15°–42° 的暖色帶裡**。「每個顏色代表一件事」這條規則在
色相這麼近的情況下已經不成立了 —— 使用者分不出「本輪聯署」與「領先中」。
`check_contrast.py` 76 組全過,因為它只量前景對背景,**不量語意色彼此分不分得開**。

**指令**:先決定 `--c-aurora` 還代不代表「本輪聯署」。
如果視覺方向確實改成單色調鎏金,就**承認語意色系統已經改制**,把圖例改寫成事實 ——
不要留一份跟程式碼不符的規格。然後在 `check_contrast.py` 加一組 `SEMANTIC_PAIRS` 互驗:
語意色兩兩之間要求色相差 ≥30° 或 ΔE ≥25。

### 4. 異形圓角要收斂成 token

現在散著 `1.5rem/.45rem`、`1.4rem/.45rem`、`1.6rem/.5rem`、`1.1rem/.35rem`、
`2rem/.6rem`、`1.4rem/.4rem` 六組,彼此差 0.1rem 這種畫面上看不出來的差別 ——
也就是這六個數字裡有幾個是沒有意義的,只是當下手打的。收成 `--shape-lg/md/sm` 三階 +
三個 mirror,新元件只能從裡面挑。

### 5. 動效參數要有單一真相源

CSS 有 `9s`/`4.5s`/`.2s`/`.16s`/`cubic-bezier(.2,.7,.3,1)`,
JS 有 `460`/`620`/`420`/`300`/`out(3)`/`out(4)`/`stagger(55)`/lenis `.9`。
定 `--dur-1/2/3` 與 `--ease-out`,JS 從 `getComputedStyle(document.documentElement)` 讀同一組。

### 6. `.round` 的 conic-gradient 描邊每幀重繪整個 border-box

動的是自訂屬性 `--ang`,而且桌機上它被 sticky 釘住 → **永遠在視窗內,永遠在重繪**。
改成旋轉一個靜態漸層層(`.round::after` + `transform:rotate`),不要動漸層角度。
另外 `.round` 的 background 綁在 `var(--ang)` 上,瀏覽器不支援 `@property` 時
整條 background 會失效變透明,而且不會退回前一條規則 —— 在規則裡自己補一行 `--ang:0deg;` 就好。

---

## P4 —— 文件、授權、部署

1. **MIT 授權條款沒有滿足。** 散佈出去的東西裡沒有 anime.js / lenis 的授權全文,
   lenis 連著作權人名字都沒有。加 `licenses/animejs-LICENSE.txt` 與 `licenses/lenis-LICENSE.txt`,
   直接複製 `node_modules/*/LICENSE` 全文(含 `Copyright (c) 2025 Julian Garnier`
   與 `Copyright (c) 2024 darkroom.engineering`)。**這條不是風格問題,是法律義務。**
2. **兩個 inline script 都沒有 `data-cfasync="false"`。** Cloudflare 的 Rocket Loader 一被打開,
   inline script 被搬動 → 雜湊對不上 → **整站白畫面**,而唯一的防線是 CDN 儀表板上一個開關。
   加上這個屬性只改標籤屬性、不動標籤內容,`csp_for_html` 算的是 `<script>` 與 `</script>`
   **之間**的位元組,**雜湊完全不變**,加了不需要重算任何東西。vendor 那顆要改 `scripts/build.py`。
3. **整頁 136KB,每次瀏覽完整重下載**(`no-cache`、沒有 ETag、源站不壓縮)。
   `csp_for_html` 已經算過 `sha256(body)`,直接拿前 16 碼當 ETag,比對 `If-None-Match` 回 304 ——
   重複瀏覽從 136KB 降到幾百 bytes。這是一行的事。
4. **Windows 上照 README 打 `npm run build` 一定不會內嵌**(`python3` 不存在),
   而 `build:win` 沒寫進任何一份文件。把 build 改成走一支會依序試 `python3`→`python`→`py -3` 的小 script。
5. **README 的「97 項」與 CONTRIBUTING 的「五個防護」跟實際跑出來的 102 / 六個對不上。**
   這個位置**已經脫節過一次**(`18e9def` 把 90 改成 97)。讓 `selftest.py` 支援 `--count`,CI 拿它去 grep 文件。
6. **`THIRD-PARTY.md` 寫的用途是舊的**:anime.js 的「用在哪」與 AOS 的排除理由,
   講的都是這次已經拿掉的功能。

---

## 你會踩到、而且會以為是自己寫錯的三件事

這三條我都實際撞過,寫下來免得你重撞。

### 1. CSP 讓 `style="..."` 屬性完全失效

`style-src` 只有一個雜湊(頁面裡那個 `<style>` 區塊),沒有 `unsafe-inline`、沒有 `unsafe-hashes`。實測:

| 寫法 | 結果 |
|---|---|
| `el.style.opacity = .5`(CSSOM) | ✅ 有效 —— anime.js 走這條,所以它沒事 |
| `el.setAttribute('style','opacity:.25')` | ❌ **被擋**,computed 仍是 1 |
| `el.style.setProperty('--i', 3)` | ✅ 有效 |

「用 `style="--i:3"` 傳索引給 CSS 做 stagger 延遲」這個到處都在用的手法**在這個站是死的**,
而且失敗的樣子是「動畫就是沒跑」,畫面上不會有紅字。要傳值給 CSS 只能走 CSSOM。

### 2. 注入 `<style>` 也被擋

在 devtools console 裡貼一段 `<style>` 試效果會**完全沒反應** —— 不是你寫錯,是 CSP。
我第一次量的時候就這樣浪費了一輪。要試效果直接改原始碼重載。
連帶:**第二個 `<style>` 區塊會直接死掉**,所有 CSS 必須留在同一個 `<style>` 裡。

### 3. 頁面沒在合成時,IntersectionObserver 與 rAF 都不派送

我用的瀏覽器面板隱藏時,IO 完全不觸發、rAF 被節流,卡片是靠 1.2 秒保險才顯示的。
如果你拿這種狀態下的 computed 值當證據,會把「幾何上進不去視窗」誤判成「IO 壞了」,
或反過來把真的壞掉當成「只是分頁沒顯示」。
**量動效相關的東西之前,先確認頁面真的在畫。** 版面幾何、computed style、對比計算不受影響。

---

## 這些是對的,重構時不要弄壞

- **`pool` canvas 的完整生命週期**(visibility / IO / reduced-motion / 背景分頁先畫一格靜態)。
  這是全站最好的一段,拿它當所有動效的模板。
- **`reveal()` 的順序**:先確認引擎在,才把卡片壓成透明。以及 1.2 秒強制顯示的保險 ——
  它今天真的救了場。它只差沒把 will-change 一起收回、以及不該無差別 unobserve。
- **CSP 用實際送出的位元組算雜湊**(`csp_for_html`),不是寫死。
- **`build.py` 的「標記找不到就失敗」**,不是「找不到就跳過」。
- **兩欄版面下 `nth-child(odd/even)` 剛好落成「左欄一種、右欄一種」**
  (1280px 實測 1/3/5 在左、2/4/6 在右,視覺上是鏡像對稱)。**這是對的,不要改。**
- **`body{overflow-x:hidden}` 沒有在掩蓋版面溢出**:375px 下逐一量過每個元素的
  `getBoundingClientRect()`,超出右緣的只有固定定位的裝飾層與刻意橫捲的標籤列,
  `documentElement.scrollWidth` = 375,乾淨。
  (但 `.meta` 缺 `overflow-wrap` —— 40 字的英數暱稱會撐爆卡片,而 `overflow-x:hidden`
  會讓它**靜靜被切掉**。這條要補。)

---

## 順序(不要跳)

1. **P0 三條**。都在你自己的紅線上。
2. **P2 的第 1 項**(反向對照擴到 HTML)。沒有它,後面每一把尺都可能是假的。
3. **P2 剩下四把尺 + 疊層對比**。造完用它們重跑一次,把量到的數字寫進 docs 當基準。
4. **P1 五條**。
5. **P3 架構重整**。這時候尺已經在了,改壞會紅。
6. **P4 文件與部署**。授權全文那條在推 GitHub 之前一定要做完。
7. 驗收:375 / 768 / 1280 × 亮 / 暗,外加 reduced-motion,共七次實機。
8. 上線前照既有的五個坑走,特別是 Cloudflare 改寫 HTML 會讓雜湊對不上整頁白。

**在 P0 與 P2 做完之前,不要再加任何新效果。** 現在每加一個,都是在一把量不到它的尺底下加的。

---

## 修訂(第一版 → 第二版)

| 第一版寫的 | 現在的事實 |
|---|---|
| 附議鈕被 flex stretch 拉成 58×313 | **已修**,現在 58×66。但換上的六角 clip-path 帶來 P0-1 |
| 掃光把 CTA 文字對比壓到 3.38:1 | 色票整組換暗之後是 **4.52:1**,過了,但只多 0.02,且沒有尺看著 |
| 所有行號引用 | **全部作廢**,本版改用內容錨點 |

## 附:量測條件

- 本機 `python server.py --port 8790 --seed --seed-zero-votes`,10 張示範卡,DB 用暫存副本(沒動原檔)。
- 命中區是用 `elementFromPoint` 做 1px 網格掃描 + 動態規劃求最大全命中正方形,不是用公式估的。
- 對比是用頁面上真的 token 值做 sRGB 相對亮度計算,含 alpha 合成。
- FPS 我**沒有**量到(面板沒在合成),那條留給你的尺。
- 另有一輪六面向對抗式代碼稽核,36 條發現全部通過反駁驗證;
  上面收錄的是其中會影響使用者或架構的部分,完整清單在稽核輸出裡。
