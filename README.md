# Skill 許願池

> 你想要什麼 AI skill?丟一個願望進池子,大家聯署。**每三天結算一次,票最高的那一個就做成 skill。**

任何人都能許願、都能附議 —— 不用註冊、不用登入、不放 cookie、不做追蹤。
一支 Python 檔 + 一頁 HTML,不用 Docker、不用資料庫伺服器。

**依賴講清楚:**

- **跑起來不需要任何依賴。** 後端只用 Python 3.9+ 標準函式庫;前端就是一個已經建好、
  進了版控的 `public/index.html`。clone 下來 `python3 server.py` 就會動,不用 `pip install`,
  也不用 `npm install`。
- **執行時零外部請求。** 前端的動畫引擎(anime.js、lenis)是**建置時**用 esbuild 打包並
  內嵌進那一頁 HTML 的,不是從 CDN 拉的。使用者的瀏覽器不會連任何外部網站,離線也能開。
- **只有要改動畫引擎才需要 npm。** 那時跑 `npm install && npm run build`。
  CI 會驗版控裡那份 HTML 真的是從 `src/vendor.js` 建出來的。
- 授權與出處見 [THIRD-PARTY.md](THIRD-PARTY.md)。

**線上的池子:<https://skill-tw.com>**

[![CI](https://github.com/shark0120/skill-wishpool/actions/workflows/ci.yml/badge.svg)](https://github.com/shark0120/skill-wishpool/actions/workflows/ci.yml)

---

## 三十秒跑起來

```bash
git clone https://github.com/shark0120/skill-wishpool.git
cd skill-wishpool
python3 server.py --seed
```

打開 <http://127.0.0.1:8787> 就有一個可以許願、可以附議、會倒數的池子。
沒有 `pip install`、也沒有 `npm install` 這一步 —— 頁面是建好的,後端只用標準函式庫。

要改前端動畫引擎才需要 Node:

```bash
npm install && npm run build     # esbuild 打包 → 內嵌進 public/index.html
```

---

## 聯署規則

| | |
|---|---|
| **一人一票** | 同一個來源對同一個願望只能附議一次(用加鹽雜湊過的 IP 認,不存原始 IP;IPv6 收斂到 /64,見下面的「防濫用」)。 |
| **每 3 天結算** | 可用 `--cycle-days` 改。倒數是從資料庫裡釘住的起算點推算的,重啟伺服器不會跳。 |
| **票最高的出線** | 同票時**先許願的贏**。門檻預設 1 票,可用 `--min-votes` 調高。 |
| **門檻只算別人的票** | 許願的人自動有一票,所以門檻拿總票數比等於沒有門檻(自己許的自己就湊滿了)。這裡數的是**不是許願者本人**投的票 —— `min_votes=1` 的意思是「至少要有一個別人也想要」。排名還是用總票數。 |
| **出線就離池** | 得標願望狀態轉成 `planned`(有人接了)並自動註記第幾輪、幾票,不會連莊。 |
| **票會累積** | 沒選上的願望票數不歸零,下一輪繼續比。 |
| **「已實現」只算成品** | 首頁那個數字只數 `granted`(東西真的做出來了)。出線的當下是 `planned`(有人接了),**不算** —— 不然結算完的那一秒首頁就會宣稱有一個成品,而其實還沒有。`/api/health` 的 `stats.planned` 另外給在做的數量。 |
| **不用排程** | 過期輪次由下一個進來的請求順手補結算,沒有 cron、沒有背景執行緒。停機超過 10 輪的那些會誠實記成「沒有結算」,不會假裝當時有人得標。 |
| **票以截止當時為準** | 結算雖然是過期後第一個請求順手做的,算的卻是**截止時間之前**投的票。沒有這一條,池子沒人來的那幾個小時裡投的票會回頭決定一個早就該結束的輪次。 |

做完的 skill 用管理端把願望標成 `granted` 並填上網址,首頁的「歷屆結果」就會出現「成品 →」連結。

---

## 分享:每一個願望都有自己的網址

這個池子只有一條長大的路:有人把**某一則**貼給別人。所以那件事被當成功能做,不是順便。

| | |
|---|---|
| `/w/{id}` | 一則願望的永久網址。伺服器把 `<title>` 與 `og:` 換成那一則 —— 貼進 LINE、Threads、X、Discord,對方看到的是那個願望,不是千篇一律的首頁。 |
| 分享鍵 | 每張願望卡上都有。手機叫系統分享面板,桌機直接複製連結。剛許完願的那一刻,只要那張卡在畫面上,游標就會自動停在它上面。 |
| 點進來 | 那一則被撈出來釘在最上面(它可能早就沉到第二頁),並且明講「有人把這個願望分享給你」。 |
| 找不到 / 已下架 | 回 404 給爬蟲,但人看到的還是整個池子,不是一頁錯誤訊息。 |
| 靜態託管 | 沒有 `/w/{id}` 這條路由,分享鍵自動退回同一頁的 `#w{id}` 錨點。 |
| `/sitemap.xml` | 動態產生:首頁 + 每一個公開願望,`lastmod` 跟著願望的更新時間。 |

網址**不寫死**:`og:url` / `canonical` / `og:image` / sitemap 都用這台伺服器自己的來源
(`Host` 標頭,可用 `WISHPOOL_SITE_URL` 釘死),所以 clone 去跑 `server.py` 不會指回 skill-tw.com。
**但唯讀靜態託管沒有伺服器可以改寫**:GitHub Pages 上看到的是版控裡那份預設值(指向
skill-tw.com 的 canonical 與 og:image),`public/robots.txt` 裡的 sitemap 網址也是寫死的 ——
要自架唯讀版,先把 `server.py` 的 `SITE_URL_DEFAULT` 改成你的網域、跑一次
`python3 scripts/sync_meta.py`,再改 `public/robots.txt` 與 `public/sitemap.xml`
裡寫死的那兩個網址(完整版的 sitemap 是伺服器動態產生的,不吃這個檔)。
分享卡圖上那行 `skill-tw.com` 也是畫進去的,要換得改 `scripts/make_og.py` 的 `FOOT` 重畫。

分享卡的圖是 `public/og.png`(1200×630),產生器在 `scripts/make_og.py` —— 它是產物,
進了版控,只有要重畫才需要 `pip install pillow`(伺服器不需要)。

文案的唯一來源是 `server.py` 的 `meta_block()`;`public/index.html` 裡那一段是給靜態託管
看的預設值,由 `scripts/sync_meta.py` 寫回去,`--check` 在測試裡逐位元組比對 —— 兩邊脫節
就變紅,不會出現「線上一套、GitHub Pages 另一套」。

---

## 兩種架法

### 1. 完整版(可以許願、可以投票)

```bash
python3 server.py --host 127.0.0.1 --port 8787 --db /var/lib/skill-wishpool/wishes.db
```

前面接自己的反向代理。systemd unit 與 nginx 設定在 [`deploy/`](deploy/),
**放在已經跑著別的網站的主機上請先讀 [`deploy/README.md`](deploy/README.md)**。

### 2. 唯讀版(GitHub Pages / 任何靜態空間)

```bash
python3 scripts/export_static.py        # 產生 public/wishes.json
```

把 `public/` 丟上去就好(**先換掉分享卡裡的網址** —— 見上面那一節:靜態託管沒有
伺服器可以改寫 `canonical` / `og:`,不換的話你的頁面會宣告自己是 skill-tw.com 的複本)。前端偵測不到後端時會**自動退成唯讀**:
只能看,許願按鈕改成導去 GitHub 開 issue。倒數不會亂編一個假的出來。

---

## API

所有回應都是 JSON。錯誤格式:`{"ok":false,"error":"人話說明","code":"機器碼","field":"欄位"}`。

| 方法 | 路徑 | 說明 |
|---|---|---|
| `GET` | `/api/health` | 版本、限制值、本輪狀態、是否唯讀 |
| `GET` | `/api/wishes` | `?sort=hot\|new\|top&q=&tag=&status=&limit=&offset=` |
| `GET` | `/api/wishes/{id}` | 單筆 |
| `POST` | `/api/wishes` | `{title, detail?, tags?, author?}`;標題重複會**自動合併並幫你附議** |
| `POST` | `/api/wishes/{id}/vote` | 附議,回 `{votes, already_voted}` |
| `GET` | `/api/round` | 本輪倒數、領先者、歷屆結果 |
| `GET` | `/api/challenge?kind=wish\|vote` | 拿一份工作量證明的挑戰;算完把 `pow` 一起送回來 |
| `POST` | `/api/admin/wishes/{id}` | `{status?, note?, skill_url?}`,需 `X-Admin-Token` |
| `DELETE` | `/api/admin/wishes/{id}?confirm=1` | 永久刪除(下架請改用 `status=hidden`) |
| `POST` | `/api/admin/round/close` | 提前結算這一輪 |
| `GET` | `/api/admin/export` | 完整匯出(含已下架) |

狀態:`open`(候選中)、`planned`(有人接了)、`granted`(已實現)、`declined`(暫不做)、`hidden`(下架,公開 API 看不到)。

```bash
# 把第 12 號願望標成已實現
curl -X POST http://127.0.0.1:8787/api/admin/wishes/12 \
  -H "X-Admin-Token: $WISHPOOL_ADMIN_TOKEN" \
  -H 'Content-Type: application/json' \
  -d '{"status":"granted","skill_url":"https://github.com/you/that-skill"}'
```

---

## 設定

| 環境變數 | 預設 | 作用 |
|---|---|---|
| `WISHPOOL_ADMIN_TOKEN` | 未設 | **沒設就整組關閉管理端(回 503)**,不是變成誰都能改 |
| `WISHPOOL_READONLY` | `0` | `1` = 唯讀,所有寫入回 403 |
| `WISHPOOL_TRUST_PROXY` | `0` | `1` = 相信 `X-Forwarded-For`。**只有**放在自己的反向代理後面才能開,否則速率限制與一人一票可被輕易繞過 |
| `WISHPOOL_ALLOW_ORIGIN` | 未設 | 設了才發 CORS 標頭 |
| `WISHPOOL_SALT_FILE` | `<db 同層>/ip_salt` | IP 雜湊的鹽。**不要進版控**;換掉就等於把舊的關聯全斷掉 |
| `WISHPOOL_RATE_WISH_MAX` / `_WINDOW` | `5` / `3600` | 每個來源每小時可許幾個願 |
| `WISHPOOL_RATE_VOTE_MAX` / `_WINDOW` | `60` / `3600` | 每個來源每小時可附議幾次 |
| `WISHPOOL_RATE_READ_MAX` | `240` | 每個來源**每分鐘**可讀幾次(API、`/w/{id}`、`/sitemap.xml` 共用一條;正常瀏覽一頁只用 3 次)。這條存在記憶體裡,重啟歸零 |
| `WISHPOOL_CYCLE_DAYS` | `3` | 幾天結算一次(也可用 `--cycle-days`) |
| `WISHPOOL_MIN_VOTES` | `1` | 出線門檻 |
| `WISHPOOL_POW` | `1` | `0` = 關掉送出前的工作量證明 |
| `WISHPOOL_POW_BITS_WISH` / `_VOTE` | `16` / `13` | 難度(0 bit 的個數)。每 +1 就是兩倍工作量 |
| `WISHPOOL_POW_TTL` | `180` | 挑戰有效秒數 |
| `WISHPOOL_SITE_URL` | 未設 | 對外網址(分享卡 `og:`、`canonical`、sitemap 用)。沒設就從每個請求的 `Host` 推,所以**自架通常不用設**;代理沒傳 `Host` 或要強制 https 才設 |
| `WISHPOOL_CSP` | `hash` | `hash` 用即時算的 inline 雜湊(最嚴);`unsafe-inline` 是**放在會改寫 HTML 的 CDN 後面時的退路**;`off` 完全不發。填錯的值會退回 `hash`,不會變成沒有 CSP |

---

## 防濫用與隱私:實際做了什麼

寫清楚是為了讓你自己判斷夠不夠用,不是為了聽起來安全。

**做了:**

- **送出前的工作量證明**:許願與附議都要先在瀏覽器算一段雜湊
  (`sha256(salt:nonce)` 開頭要有 N 個 0 bit,預設許願 16 bits ≈ 6.5 萬次、
  附議 13 bits ≈ 8 千次)。人類等幾十毫秒到半秒,腳本要洗版就得付出等比例 CPU。
  挑戰由伺服器用 HMAC 簽章、綁來源雜湊、3 分鐘過期、**同一份只能兌現一次**
  (防重放),而且難度是伺服器說了算 —— 自己把 `bits` 改小會被擋。
  不需要金鑰、不載入任何外部腳本、不放 cookie。`WISHPOOL_POW=0` 可關掉。
- **速率限制**:每個來源每小時 5 個願望 / 60 次附議,存在 SQLite 裡,重啟不會歸零。
  讀取另外有一條(每分鐘 240 次,記憶體裡),API 與會查資料庫的頁面(`/w/{id}`、`/sitemap.xml`)共用 ——
  站在 Cloudflare 後面又關掉 Browser Integrity Check 的話,那就是唯一擋狂打的東西。這是唯一真正擋得住洗版的機制。檢查與寫入在同一個 `BEGIN IMMEDIATE` 交易裡,所以平行請求繞不過去(自我測試會打 20 個並行請求,只能有 5 個成功)。
- **一人一票**:`(願望, 來源雜湊)` 有唯一鍵,重複附議在資料庫層就被吃掉,不只是前端 disable。
- **IPv6 收斂到 /64**:來源雜湊算的是 /64 而不是完整位址。ISP 與 VPS 配 IPv6 是一次給一整段 /64,
  用完整位址當來源的話,任何有 IPv6 的人手上就有 1.8×10^19 個「不同來源」—— 速率限制與一人一票
  對他等於不存在,而且不必偽造任何標頭。代價是同一段 /64 底下的人共用一票(跟 IPv4 的 NAT 同一類,
  但那是**有界**的取捨;用完整位址是無界的)。
- **不存原始 IP**:只存 `sha256(鹽 + IP)` 前 32 碼。連 access log 也只寫雜湊前 8 碼。自我測試會直接打開 DB 檔翻每一格,確認裡面找不到 IP 字串。
- **重複願望自動合併**:標題正規化(去標點空白、casefold)後撞到就併成附議,池子不會被同一件事佔滿。
- **輸入清理**:零寬字元、雙向覆寫字元、控制字元一律移除;長度、連結數量、標籤數量都有硬上限。
- **XSS**:使用者內容全程走 `textContent`,前端沒有任何 `innerHTML` / `insertAdjacentHTML` / `eval`(自我測試會掃原始碼,加回去就變紅)。
- **CSP 用雜湊而非 `unsafe-inline`**:伺服器在送出頁面時即時算 inline 區塊的 sha256,所以雜湊永遠不會跟內容脫節;注入進 DOM 的 `<script>` 對不上雜湊就不會執行。
- **管理端 fail-closed**:沒設權杖就整組 503;權杖比對用 `hmac.compare_digest`。
- **站在 CDN 後面的話,零外部請求會有一個缺口**:skill-tw.com 實測每個回應都帶 Cloudflare 的
  `NEL` / `Report-To`,瀏覽器連線出錯時會主動把報告送到 `a.nel.cloudflare.com`。頁面本身沒有外連,
  但那一段不在程式碼裡、也不在站方手上 —— 要真的零外部請求得去 CDN 關掉 NEL。
- **程式碼本身零外部請求**:字型用系統內建,沒有 CDN、沒有 Google Fonts、沒有分析工具,整頁離線也能開。
  **但你放在前面的 CDN 可能自己塞東西** —— 實測 Cloudflare 的 Web Analytics 會把
  `beacon.min.js` 注入 HTML;我們的 CSP 把它擋掉了(console 會留下一則 blocked 訊息),
  但要真正做到零外部請求,得去 CDN 那邊關掉那個功能。見 [`deploy/README.md`](deploy/README.md)。

**沒做,你要自己知道:**

- **沒有帳號系統**。同一個 NAT / 校園網路 / 公司網路底下的人會共用一個雜湊(IPv6 則是同一段 /64,通常就是同一戶),彼此擠不掉彼此的票,但也就只有一票。想要嚴格一人一票就得加登入,這個專案刻意不做。
- **前端的蜜罐欄位只是嚇阻**,不是防護。真正的防線是速率限制。
- **PoW 不等於「人機驗證」**。它證明的是「有人付了計算成本」,不是「這是人類」。
  買得起 CPU 的人還是過得去 —— 它讓大量自動化變貴,真正擋量的是速率限制。
- **沒有 CAPTCHA、沒有第三方防機器人服務**。那些都要載入外部腳本,會同時打破
  零外部請求、不追蹤、CSP 不開洞三件事。真的被鎖定攻擊,請在反向代理層擋。
- **管理端只有一個權杖**,沒有多人權限、沒有操作稽核日誌。
- **沒有 email 通知**。願望有進展要自己回來看。
- **`--seed` 的範例願望是虛構的**,`author` 都寫「範例」,不是真實使用者。

---

## 測試

```bash
python3 scripts/selftest.py                 # 203 項端到端檢查(真的起伺服器、真的打 HTTP)
python3 scripts/selftest.py --verify-gauge  # 反向對照:把防護拆掉,確認測試會紅
python3 scripts/check_contrast.py -v        # 直接從 index.html 讀色票,實算 WCAG 對比度
```

`--verify-gauge` 是重點:它會複製一份原始碼,分別把**標題長度上限、投票去重、目錄逃脫檢查、速率限制、速率限制的寫入鎖、工作量證明的雜湊檢查、工作量證明的防重放、讀取限流、輪次得標判定、分享卡的跳脫、IPv6 來源收斂、截止時間、已實現的算法、門檻只算別人的票**這十四個防護改壞,然後要求同一套測試**必須失敗**。
一套永遠會綠的測試比沒有測試更危險 —— 這一步就是在防那個。

**測試一定要在你要部署的那台機器上跑一次。** 這個專案就吃過一次:同一份程式碼在
Windows / Python 3.14 上 94 項全綠,在 Ubuntu / Python 3.10 上穩定紅 4 項 —— 而紅的
那個是真 bug(見下面第三點)。`deploy/README.md` 的更新流程因此把 selftest 放在
`systemctl restart` **之前**。

開發過程中這套機制真的抓到五件事:

> **假綠燈:** 目錄逃脫測試原本用 `urllib` 發 `/../x`,但 `urllib` 會先把路徑正規化成
> `/x`,所以那條測試從來沒送出過 `..` —— 把逃脫檢查整段拆掉,測試照樣全綠。現在改用
> 原始 socket,而且目標刻意選副檔名在白名單內的檔案,不然會被副檔名白名單擋掉、
> 量不到真正那道防線。
>
> **真漏洞:** 速率限制是「先數再寫」,原本沒有鎖 —— 20 個並行請求在上限 5 的池子裡
> **全部**拿到 201。現在檢查與寫入在同一個 `BEGIN IMMEDIATE` 交易裡,並加了一條
> 並行測試盯著它。
>
> **真 bug(而且我一度把它當成測試的錯):** handler 原本在 `with connect()` **裡面**
> 就送出 HTTP 回應,而 commit 是離開區塊才發生 —— 客戶端拿到 201 之後立刻發的下一個
> 請求,可能用另一條連線讀到還沒有這筆資料的舊快照。症狀就是「剛許的願不見了」。
> 我第一次看到它時以為只是輪次測試在閃,用輪詢「修」掉了,等到在 Linux 上跑才發現
> 是真的。現在所有 handler 都是「payload 在 with 裡面組好,回應在提交之後才送」,
> 並有一節 10 輪無延遲的寫完馬上讀盯著。
>
> **會閃的測試:** 輪次測試原本 sleep 固定秒數。會閃的測試跟假綠燈一樣糟 —— CI 隨機
> 變紅之後,大家就開始忽略紅燈。現在改成先確認票真的投進去了,再輪詢等結算。
>
> **會閃的「尺」:** 更難發現的一種 —— 測試本身不閃,**反向對照**在閃。並行洗版那一節
> 原本是開 20 個 thread 各自送請求,但 `t.start()` 自己就要時間,第一個常常整趟跑完了
> 第 20 個才起步,於是「拿掉寫入鎖」這個變異三次只有一次會紅(head 與新版都會閃,
> 實測過)。一把時準時不準的尺,量出來的綠燈是沒有意義的。現在 20 條連線先各自建好、
> 卡在 barrier 再一起送,而且**同樣的爆量打 6 輪**(每輪換一個來源位址讓配額重來)——
> 每一輪都必須剛好 5 個成功。拆掉鎖之後 6 次重跑全部如預期變紅。

---

## 介面

- **手機優先。** 實測過 375×812 與 768×1024、亮色與暗色各一次:沒有橫向捲動、
  最小字級 12.5px、文字對比最低 5.17:1(WCAG AA 要 4.5)、獨立點擊目標都 ≥ 44px。
- **每張卡有分享鍵**(44px 高,顏色刻意比附議鈕弱 —— 附議才是主行動)。手機叫系統
  分享面板、桌機複製連結;沒有 `navigator.clipboard`(http 或舊瀏覽器)時退回老方法,
  再不行就直接把網址顯示出來讓人自己抄。
- **沒有 emoji。** 圖示是同文件內嵌的 SVG symbol —— emoji 在每個平台長得不一樣、
  在暗色模式常常糊掉,而且大小不受控。
- **水池是 canvas 畫的**,不是圖檔:水面波紋一直在動,有人許願或附議時會落一滴水
  濺起漣漪。顏色從 CSS 變數讀,所以跟著亮暗模式走;`prefers-reduced-motion` 時
  只畫一格靜態畫面;分頁切到背景就停止動畫,但**不清畫布**(不然回來會看到空白)。
- **視覺語言**參考 [HanSun Architects](https://www.hansunarchitects.com/) 的網站:
  暖紙白底、近黑內文、髮絲級分隔線、圓角只有 2px、襯線大標配寬字距、大量留白。
  金只出現在描邊與漸層 —— 金色文字在淺底上過不了 AA,所以 `--gold-*` 一律不拿來寫字。
  字體全部用系統內建襯線堆疊(原站用的 Cormorant Garamond 是 Google Fonts,外連會破壞零外部請求)。
- **超高響應式。** 320 / 768 / 1280 都實測過:手機單欄、桌機「釘住的側欄 + 主欄 +
  願望卡兩欄」、超寬螢幕三欄;root 字級用 `clamp()` 流動,下限鎖 16px。
- **動態。** anime.js 做捲動進場與數字滾動、lenis 做慣性捲動、canvas 做三色極光水池,
  背景兩團極光緩慢漂移。形狀刻意不規則:水池是 SVG 波浪切邊、附議鈕是有機水滴、
  願望卡左右交錯不對稱圓角、聯署框是會轉的漸層描邊。
  無限循環的 CSS 動畫上限 4 個(有量尺盯著),而且只動 `transform` 與 `opacity`。
- 執行時零外部請求(CDN 的注入見上一節)。

## 想改成別的主題?

這份程式碼裡沒有任何跟「skill」綁死的邏輯 —— 它就是一個**聯署 + 定期結算**的池子。
把 `public/index.html` 的文案換掉就能變成功能許願、選書、選題、社團活動投票
(分享卡的文案在 `server.py` 的 `meta_block()`,改完跑 `python3 scripts/sync_meta.py`;
分享卡的圖在 `scripts/make_og.py`)。
後端只有兩個地方要看:`CYCLE_DAYS_DEFAULT`(幾天結算)與 `pick_winner()`(怎麼算贏)。

---

## 授權

MIT。拿去改、拿去架、拿去商用都可以,不用問我。

---

<a id="english"></a>

## English

**Skill Wishpool** — a petition-style wishlist for AI skills. Anyone can post a wish and
co-sign others; **every 3 days the top-voted wish gets built into an actual skill.**

No signup, no cookies, no tracking. One Python file (stdlib only, 3.9+) plus one
self-contained HTML page — no Docker, no database server.

**Dependencies, stated precisely:** running it needs nothing installed — the backend is
Python stdlib and `public/index.html` ships built and committed, so `python3 server.py`
just works. The front-end animation engines (anime.js, lenis — both MIT) are bundled
**at build time** with esbuild and inlined into that one HTML file, so the browser still
makes zero external requests and the page works offline. You only need `npm install &&
npm run build` if you want to change the animation engines. CI verifies the committed
HTML really is the output of `src/vendor.js`. See [THIRD-PARTY.md](THIRD-PARTY.md).

```bash
python3 server.py --seed     # http://127.0.0.1:8787
```

- **Shareable wishes**: every wish has its own URL, `/w/{id}`, and the server rewrites
  `<title>` and the Open Graph tags to that wish, so pasting it into LINE / Threads / X /
  Discord shows *that wish* rather than the same generic homepage. Every card has a share
  button (native share sheet on mobile, clipboard on desktop). `/sitemap.xml` is generated
  from the live pool. URLs are not hard-coded **when you run `server.py`** — they follow
  the request's `Host`, or `WISHPOOL_SITE_URL` if you pin it. Static hosting has no server
  to rewrite them, so the committed defaults (canonical, `og:image`, `robots.txt`,
  `sitemap.xml`) still point at skill-tw.com — change `SITE_URL_DEFAULT`, run
  `scripts/sync_meta.py`, and edit those two files before you publish a read-only copy.
- **Read-only static mode**: run `python3 scripts/export_static.py` and host `public/`
  anywhere (GitHub Pages). The page detects the missing backend and degrades to read-only;
  if the snapshot is the bundled sample data it says so instead of passing fictional vote
  counts off as real.
- **Anti-abuse**: per-source rate limits in SQLite, one vote per source per wish enforced by
  a DB unique key, duplicate-title merging, input sanitisation, hash-based CSP, fail-closed
  admin endpoints. Raw IPs are never stored — only `sha256(salt + ip)`.
- **Tests**: `scripts/selftest.py` boots the real server over real HTTP (203 checks).
  `--verify-gauge` sabotages fourteen guards and requires the suite to go red, so the suite
  can't quietly become a rubber stamp. It has already caught a false green (a traversal
  test that never actually sent `..`, because `urllib` normalises the path), two real bugs
  (the rate limiter was check-then-act with no lock, so 20 parallel requests all got
  through a limit of 5; and responses were sent before the transaction committed, so a
  freshly created wish could be missing from the very next read), a flaky test — and a
  flaky *gauge*: the parallel-flood check started 20 threads one by one, so the first
  request often finished before the last one started and the "remove the write lock"
  mutation only went red about one run in three. The connections are now opened up front
  and released together by a barrier, and the same flood runs six times.
  Run the suite **on the machine you deploy to** — the same code was 94/94 green on
  Windows/Python 3.14 while failing 4 checks on Ubuntu/Python 3.10.
- **One person, one vote — including over IPv6**: the source hash is computed from the /64
  prefix, not the full address. ISPs hand out a whole /64 per customer, so hashing the full
  address would give anyone with IPv6 1.8×10^19 distinct "sources" and no header forgery
  required.

See the tables above for the full API and configuration; MIT licensed.
