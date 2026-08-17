# UI 架構指令 — v2 動效改版

給:正在做 v2「全站動態 · 打破常規形狀」的那個對話窗
出自:UI 架構師
依據:2026-08-18 把 `public/index.html` 真的在瀏覽器裡開起來量過(本機 8790,375 / 1280 兩種寬度、亮暗兩種模式)

---

## 先講結論

你的尺全綠 —— `selftest.py` 102 項 0 失敗、`check_contrast.py` 76 組通過、頁面 132KB 在 200KB 上限內。

**但沒有一項在量畫面。** 我把頁面開起來量,三件事現在是壞的,而且三件都踩在
`docs/v2-motion-plan.md` §3 你自己寫的「不可退讓的線」上。

這不是巧合。你在第 2 階段「先造尺」只造了三條字串比對就進了第 3 階段,
尺沒造的那兩把(異形命中區、FPS/長任務)正好就是現在漏掉的東西。

---

## 一、立刻修(P0)

### P0-1 「水滴形附議鈕」實際上是 58×313 的柱子

375px 實測十張卡的 `.vote` 尺寸:

```
58x234  58x234  58x235  58x234  58x234  58x210  58x259  58x313  58x259  58x290
```

原因:`.wish{display:flex}`(296 行),`.vote` 沒有 `align-self`,flex 預設 stretch,
高度被卡片內容撐滿。`min-height:62px` 只是下限,擋不住被拉長。

`border-radius: 52% 48% 46% 54% / 58% 60% 40% 42%`(396 行)是百分比圓角 ——
它按盒子的實際寬高換算。58×62 上是水滴,58×313 上是一根長條。

計畫書 §1 第一列寫的是「附議鈕是圓角方塊 → **水滴形**」。**這條沒有做到**,
而且做不到的方式是「在你的螢幕上看起來也許還好,但形狀語言整個消失」。

**改法**:`.vote{align-self:flex-start}`(或 `.wish{align-items:flex-start}`),
並把盒子鎖在接近正方形的比例。有機圓角只有在長寬比接近 1 的盒子上才成立 ——
這條要寫進註解,不然下一個人加一行 `flex:1` 又會回來。

> 注意:我試著在瀏覽器裡打這個補丁驗證,被 CSP 擋掉了(原因見 §四)。
> 所以這條要你在原始碼改完重載才驗得到,不要在 console 裡試。

### P0-2 掃光把主要按鈕的文字對比壓到 3.38:1

`.wish-cta::after`(420 行)是 `inset:0` 的全覆蓋層,
`rgba(255,255,255,.28)` 的亮帶每 4.5 秒掃過**文字上方**(偽元素在內容之後繪製)。

亮色模式實測(用頁面上真的 token 值算的):

| | 白字 vs `--accent` | 白字 vs `--c-aurora` |
|---|---|---|
| 掃光前 | 5.99:1 | 7.22:1 |
| 掃光峰值(疊 .28 白) | **3.38:1** | **3.80:1** |

紅線第 3 條:「對比不能因為動畫背景而失守」。這是第一個踩到的。
`check_contrast.py` 看不到它,因為它量的是 token 對 token,不是「疊了一層半透明白之後」。

**改法**(擇一,不要三個都做):

- 把亮帶降到 **.10 或更低**(我算 .12 是 4.62:1、.10 是 4.81:1 —— 但**不要抄我的數字**,
  由 §三 那把新的尺量出來才算數);
- 或把 `::after` 改成只掃邊框,文字所在的區域不覆蓋;
- 或整個拿掉。一個每 4.5 秒自己閃一下的按鈕,在一個「不准假動態」的站上本來就可疑 ——
  它不代表任何真實狀態在變。

暗色模式不受影響(文字是深色 `#04222B`,疊白反而對比上升),
所以**只調亮色模式的數值是不夠的,兩邊都要重算**。

### P0-3 will-change 永遠收不回來

`.list .wish{will-change:transform,opacity}`(431 行)是無條件掛著的 CSS 規則。
`MOTION.reveal` 只在 `onComplete` 把 inline 的 `willChange` 設回 `auto`。

三條路徑走不到 `onComplete`:

1. `reduce.matches` → `reveal()` 第一行直接 return
2. 引擎沒載到 → 同上
3. 1.2 秒保險那條(`utils.set(n,{opacity:1,translateY:0,scale:1})`)**沒有把 willChange 設回去**

375px 實測:10 張卡,**10 張的 computed `will-change` 都還是 `transform, opacity`,
inline 沒有任何重設**(`c.style.willChange` 全是空的)。

後果:開 reduced-motion 的人,每張卡永久佔一層合成層,而那層是為了一個
**永遠不會跑的動畫**留的。按「載入更多」之後線性增加。

**改法**:`will-change` 不要寫在 CSS。由 `reveal()` 在動畫**開始前**用 CSSOM 加上,
在 `onComplete` **與** 1.2 秒保險**兩條路徑都**收回。reduced-motion / 沒引擎時完全不加。

---

## 二、架構層面(這是我真正要你改的)

### A. 形狀不能繼續當「檔尾覆寫層」

384–456 行那一整段,是把前面已經定義好的元件再推翻一次:

| 元件 | 第一次定義 | 被推翻於 |
|---|---|---|
| `.pool-wrap` | 185 行 border / border-radius / background / box-shadow | 389 行全部拿掉換 clip-path |
| `.round` 邊框 | 216 行 `1px solid var(--c-aurora)` | 409 行整組換成 conic-gradient 描邊 |
| `.round::before` 三色頂帶 | 220 行 | 415 行 `background:none` 廢掉,但偽元素本身還留著 |
| `.vote` 圓角 | 307 行 `.6rem` | 396 行有機圓角 |
| `.chip` / `.tags-bar button` | 288 / 326 行 | 404 行 |
| `.wish-cta` | 213 行 | 418 行 |

問題不是難看,是**下一個人改 185 行會發現沒有效果**,而他不會知道要去看 389 行。
這種檔案改三次就會出現「兩處都改、互相打架」,然後有人補 `!important`,然後就回不去了。

**指令**:用 `@layer` 把覆寫關係**宣告出來**,不要靠「誰寫在後面」:

```css
@layer reset, tokens, layout, components, shape, motion, a11y;
```

- 384–431 行 → `@layer shape`
- 433–447 行(hover 手感)→ `@layer motion`
- 449–456 行(reduced-motion)→ `@layer a11y`

好處:a11y 層永遠贏,`@media (prefers-reduced-motion)` 那段裡的
`*{animation:none!important;transition:none!important}` 可以把 `!important` 拿掉。
一個用 `*` 選擇器加 `!important` 的規則是現在唯一擋得住的手段,但它同時也會擋掉
未來任何合法的例外 —— 用 layer 就不必付這個代價。

順帶:`.round::before` 現在只剩 `background:none`,直接刪掉那個偽元素。
不要留一個什麼都不做的規則在那裡讓人猜。

### B. 異形圓角要收斂成 token

現在散在檔案裡的魔術數字:

```
1.5rem .45rem   卡片
1.4rem .45rem   CTA / primary
1.6rem .5rem    round
1.1rem .35rem   chip / tags-bar
2rem   .6rem    thanks
1.4rem .4rem    thanks-link
```

六組、沒有規律、彼此差 0.1rem 這種在畫面上看不出來的差別 ——
也就是說這六個數字裡有幾個是**沒有意義的**,只是當下手打的。

**指令**:定成三階寫進 `:root`,任何新元件只能從裡面挑:

```css
--shape-lg: 1.6rem .5rem 1.6rem .5rem;    /* 區塊:round / thanks */
--shape-md: 1.4rem .45rem 1.4rem .45rem;  /* 卡片 / 主要按鈕 */
--shape-sm: 1.1rem .35rem 1.1rem .35rem;  /* 標籤 */
```

外加三個 `--shape-*-mirror`。這樣「左右交錯」變成
`nth-child(even){border-radius:var(--shape-md-mirror)}`,一眼看得懂在做什麼。

### C. 動效生命週期:canvas 有紀律,anime 層沒有

`pool` 那支寫得很好 —— `visibilitychange` 停、`IntersectionObserver` 離開視窗停、
`reduced-motion` 的 change 監聽、背景分頁先畫一格靜態避免空白框。

`MOTION.backdrop()`(`#bg-blobs` 的兩個無限 loop)**一條都沒有**:

- 切到別的分頁不停
- 捲到看不見不停
- 使用者中途開啟 reduced-motion,只有 lenis 會停,blobs 繼續轉
  (`reduce.addEventListener('change')` 那段只 destroy lenis)

**一個專案裡不該有兩套動畫生命週期紀律,一套嚴一套沒有。**

**指令**:把 pool 的生命週期抽成共用的 `lifecycle(start, stop)`,canvas 與 MOTION 都掛上去。

順帶一個效能問題:`#bg-blobs` 是 `position:fixed` 全視窗 + `filter:blur(2px)` +
無限動 transform。blur 不是合成,是**每一幀整個視窗重繪**。手機上這是全站最貴的一項。
要嘛拿掉 blur(SVG 路徑本身已經夠糊),要嘛把那兩團畫進已經存在的 pool canvas 裡 ——
不要為了兩團模糊的顏色多開一層全螢幕濾鏡。

### D. 動效參數要有單一真相源

現在 CSS 這邊有 `9s` / `4.5s` / `.2s` / `.16s` / `cubic-bezier(.2,.7,.3,1)`,
JS 那邊有 `460` / `620` / `420` / `300` / `'out(3)'` / `'out(4)'` / `stagger(55)` / lenis `.9`。

兩邊各寫各的。調一次手感要翻兩個地方,而且沒有人知道這個站的「快」是多快。

**指令**:CSS 自訂屬性定 `--dur-1/2/3` 與 `--ease-out`,
JS 從 `getComputedStyle(document.documentElement)` 讀同一組。

---

## 三、量尺:第 2 階段沒做完就進第 3 階段了

計畫書 §2 寫得很清楚:「尺要先能抓到『動畫爆掉』才准開始改」,要求五把 ——
動效預算、reduced-motion 靜態驗證、異形命中區、FPS/長任務、頁面體積。

實際加進 `selftest.py` 的是三條**字串層**檢查:

| 檢查 | 它實際在量什麼 | 會通過但畫面壞掉的反例 |
|---|---|---|
| `app.count("infinite") <= 4` | `infinite` 這個字出現幾次 | 把 blur 從 2px 改成 20px、把 sheen 從 4.5s 改成 0.2s、把附議鈕拉成 58×313 —— 全綠 |
| `"prefers-reduced-motion:reduce" in app` | 那個字串存在 | 區塊裡什麼都不寫也綠 |
| `< 200KB` | 位元組數 | 這條是有意義的,留著 |

前兩條量的是「字出現幾次」,不是動畫的代價。
沒造的兩把(異形命中區、FPS/長任務)正好就是 P0-1 會被抓到的地方。
**尺沒造 → 缺陷通過 → 102 項全綠交付**,這就是整件事的因果,不是運氣不好。

而且新加的三條沒有進 `--verify-gauge` 的反向對照。**一把不會紅的尺不是尺。**

**指令(這四件做完才准繼續加效果):**

1. **渲染層量尺**。用真的瀏覽器開頁面,對 375 / 768 / 1280 各量一次,輸出 JSON:
   - 每個可點元素的 w×h(任一 < 44 就紅)
   - `document.documentElement.scrollWidth > innerWidth`(紅)
   - `getAnimations()` 裡 `iterations === Infinity` 的清單(超過預算就紅)
   - computed `will-change !== 'auto'` 的元素數(超過 2 就紅)
   我今天是用瀏覽器手動量的,你要把它變成腳本。

2. **疊層對比**。`check_contrast.py` 加一個模式:對有半透明覆蓋層的元件,
   把覆蓋色合成上去再量。至少要涵蓋 `.wish-cta::after`。P0-2 就是這條沒有才漏掉的。

3. **reduced-motion 真驗證**。開著 reduced-motion 載入頁面,
   斷言 `document.getAnimations().length === 0`、canvas 的 rAF 沒在跑。
   不要再用字串比對。

4. **反向對照**。上面三條都要能在「故意弄壞」時變紅,加進 `--verify-gauge`。

---

## 四、你會踩到、而且會以為是自己寫錯的兩件事

這兩條我在頁面上實測過,不是推測。

### 1. CSP 讓 `style="..."` 屬性完全失效

送出去的標頭是 `style-src 'sha256-...'`,只有一個雜湊(就是頁面裡那個 `<style>` 區塊),
沒有 `unsafe-inline`、沒有 `unsafe-hashes`。實測結果:

| 寫法 | 結果 |
|---|---|
| `el.style.opacity = .5`(CSSOM 逐屬性) | ✅ 有效 —— anime.js 走這條,所以它沒事 |
| `el.setAttribute('style', 'opacity:.25')` | ❌ **被擋**,computed 仍是 1 |
| `el.style.setProperty('--i', 3)` | ✅ 有效 |

所以「用 `style="--i:3"` 傳索引給 CSS 做 stagger 延遲」這個到處都在用的手法,
**在這個站是死的**。而且它失敗的樣子是「動畫就是沒跑」,畫面上不會有任何紅字
(錯誤只在 console)。要傳值給 CSS 只能走 CSSOM。

### 2. 注入 `<style>` 也被擋

你在 devtools console 裡貼一段 `<style>` 想試效果會**完全沒反應** —— 不是你寫錯,是 CSP。
我今天就是這樣浪費了一輪,所以寫下來。要試效果就直接改原始碼重載。

連帶的硬限制:**第二個 `<style>` 區塊會直接死掉**。所有 CSS 必須留在同一個 `<style>` 裡。
`@layer` 剛好不需要拆檔,所以 §二 A 那個建議跟這條不衝突。

---

## 五、這些是對的,重構時不要弄壞

- **`pool` canvas 的完整生命週期**(visibility / IO / reduced-motion / 先畫一格靜態)。
  這是全站最好的一段,拿它當模板。
- **`reveal()` 的順序**:先確認引擎在,才把卡片壓成透明。以及 1.2 秒強制顯示的保險。
  這條保險今天在我這台**真的救了場** —— 瀏覽器面板隱藏時 IntersectionObserver 沒觸發,
  十張卡是靠那個 setTimeout 才顯示出來的。它只差沒把 `will-change` 一起收回(見 P0-3)。
- **CSP 用實際送出的位元組算雜湊**(`server.py` 的 `csp_for_html`),不是寫死。
- **`build.py` 的「標記找不到就失敗」**,不是「找不到就跳過」。
- **兩欄版面下 `nth-child(odd/even)` 剛好落成「左欄一種、右欄一種」** ——
  1280px 實測第 1/3/5 張在左、2/4/6 張在右,視覺上是鏡像對稱。**這是對的,不要改。**
  三欄(≥110rem)才會變成逐列翻轉的棋盤格,那個之後再看,不急。
- **`body{overflow-x:hidden}` 沒有在掩蓋版面溢出** —— 我逐一量過每個元素的
  `getBoundingClientRect()`,375px 下超出右緣的只有 `#blob-b`(固定定位的裝飾,被 SVG 裁掉)
  與 `.tags-bar` 裡的標籤鈕(那是刻意的橫向捲動容器)。`documentElement.scrollWidth` = 375,乾淨。

---

## 六、順序(不要跳)

1. P0-1 / P0-2 / P0-3 修掉 —— 三條都在你自己的紅線上
2. §三 的四把尺造起來,反向對照要能紅
3. 用新的尺重跑一次,把量到的數字寫進 docs(下次才有基準可比)
4. **才**做 §二 的架構重整(`@layer` / shape token / lifecycle / 動效參數)
5. 六格矩陣驗收:375 / 768 / 1280 × 亮 / 暗,外加 reduced-motion 各跑一次
6. 上線前照既有的五個坑走 —— 特別是 Cloudflare 的 Rocket Loader / Auto Minify
   改寫 HTML 會讓 script 雜湊對不上,**整頁 JS 被擋成白畫面**

---

## 附:我這次的量測條件

- 本機 `python server.py --port 8790`,`--seed --seed-zero-votes`,10 張示範卡
- 瀏覽器面板在隱藏狀態下量的,所以 **rAF 與 IntersectionObserver 的時序不可信**
  (FPS 我沒有量到,那條留給你的尺)。
  版面幾何、computed style、對比計算不受影響 —— 上面引用的數字都屬於後者。
- 頁面實測 `transferSize` 132KB、`DOMContentLoaded` 129ms(本機,不代表行動網路)。
