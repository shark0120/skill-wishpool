# Skill 許願池

> 你想要什麼 AI skill?丟一個願望進池子,大家聯署。**每三天結算一次,票最高的那一個就做成 skill。**

任何人都能許願、都能附議 —— 不用註冊、不用登入、不放 cookie、不做追蹤。
一支 Python 檔 + 一頁 HTML,零外部依賴(不用 npm、不用 Docker、不用資料庫伺服器)。

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
沒有 `pip install` 這一步 —— 只用 Python 3.9+ 標準函式庫。

---

## 聯署規則

| | |
|---|---|
| **一人一票** | 同一個來源對同一個願望只能附議一次(用加鹽雜湊過的 IP 認,不存原始 IP)。 |
| **每 3 天結算** | 可用 `--cycle-days` 改。倒數是從資料庫裡釘住的起算點推算的,重啟伺服器不會跳。 |
| **票最高的出線** | 同票時**先許願的贏**。門檻預設 1 票,可用 `--min-votes` 調高。 |
| **出線就離池** | 得標願望狀態轉成 `planned`(有人接了)並自動註記第幾輪、幾票,不會連莊。 |
| **票會累積** | 沒選上的願望票數不歸零,下一輪繼續比。 |
| **不用排程** | 過期輪次由下一個進來的請求順手補結算,沒有 cron、沒有背景執行緒。伺服器關機期間的輪次會誠實記成「沒有結算」,不會假裝當時有人得標。 |

做完的 skill 用管理端把願望標成 `granted` 並填上網址,首頁的「歷屆結果」就會出現「成品 →」連結。

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

把 `public/` 丟上去就好。前端偵測不到後端時會**自動退成唯讀**:
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
| `WISHPOOL_CYCLE_DAYS` | `3` | 幾天結算一次(也可用 `--cycle-days`) |
| `WISHPOOL_MIN_VOTES` | `1` | 出線門檻 |

---

## 防濫用與隱私:實際做了什麼

寫清楚是為了讓你自己判斷夠不夠用,不是為了聽起來安全。

**做了:**

- **速率限制**:每個來源每小時 5 個願望 / 60 次附議,存在 SQLite 裡,重啟不會歸零。這是唯一真正擋得住洗版的機制。檢查與寫入在同一個 `BEGIN IMMEDIATE` 交易裡,所以平行請求繞不過去(自我測試會打 20 個並行請求,只能有 5 個成功)。
- **一人一票**:`(願望, 來源雜湊)` 有唯一鍵,重複附議在資料庫層就被吃掉,不只是前端 disable。
- **不存原始 IP**:只存 `sha256(鹽 + IP)` 前 32 碼。連 access log 也只寫雜湊前 8 碼。自我測試會直接打開 DB 檔翻每一格,確認裡面找不到 IP 字串。
- **重複願望自動合併**:標題正規化(去標點空白、casefold)後撞到就併成附議,池子不會被同一件事佔滿。
- **輸入清理**:零寬字元、雙向覆寫字元、控制字元一律移除;長度、連結數量、標籤數量都有硬上限。
- **XSS**:使用者內容全程走 `textContent`,前端沒有任何 `innerHTML` / `insertAdjacentHTML` / `eval`(自我測試會掃原始碼,加回去就變紅)。
- **CSP 用雜湊而非 `unsafe-inline`**:伺服器在送出頁面時即時算 inline 區塊的 sha256,所以雜湊永遠不會跟內容脫節;注入進 DOM 的 `<script>` 對不上雜湊就不會執行。
- **管理端 fail-closed**:沒設權杖就整組 503;權杖比對用 `hmac.compare_digest`。
- **零外部請求**:字型用系統內建,沒有 CDN、沒有 Google Fonts、沒有分析工具。整頁離線也能開。

**沒做,你要自己知道:**

- **沒有帳號系統**。同一個 NAT / 校園網路 / 公司網路底下的人會共用一個雜湊,彼此擠不掉彼此的票,但也就只有一票。想要嚴格一人一票就得加登入,這個專案刻意不做。
- **前端的蜜罐欄位只是嚇阻**,不是防護。真正的防線是速率限制。
- **沒有 CAPTCHA、沒有防機器人服務**。真的被鎖定攻擊,請在反向代理層擋。
- **管理端只有一個權杖**,沒有多人權限、沒有操作稽核日誌。
- **沒有 email 通知**。願望有進展要自己回來看。
- **`--seed` 的範例願望是虛構的**,`author` 都寫「範例」,不是真實使用者。

---

## 測試

```bash
python3 scripts/selftest.py                 # 89 項端到端檢查(真的起伺服器、真的打 HTTP)
python3 scripts/selftest.py --verify-gauge  # 反向對照:把防護拆掉,確認測試會紅
python3 scripts/check_contrast.py -v        # 直接從 index.html 讀色票,實算 WCAG 對比度
```

`--verify-gauge` 是重點:它會複製一份原始碼,分別把**標題長度上限、投票去重、目錄逃脫檢查、速率限制、輪次得標判定**改壞,然後要求同一套測試**必須失敗**。
一套永遠會綠的測試比沒有測試更危險 —— 這一步就是在防那個。

> 開發時它真的抓到過一個假綠燈:目錄逃脫測試原本用 `urllib` 發 `/../x`,但 `urllib`
> 會先把路徑正規化成 `/x`,所以那條測試從來沒送出過 `..`。現在改用原始 socket,
> 而且目標刻意選副檔名在白名單內的檔案,不然會被副檔名檢查擋掉、量不到真正那道防線。

---

## 介面

- **手機優先。** 實測過 375×812 與 768×1024、亮色與暗色各一次:沒有橫向捲動、
  最小字級 12.5px、文字對比最低 4.82:1(WCAG AA 要 4.5)、獨立點擊目標都 ≥ 44px。
- **沒有 emoji。** 圖示是同文件內嵌的 SVG symbol —— emoji 在每個平台長得不一樣、
  在暗色模式常常糊掉,而且大小不受控。
- **水池是 canvas 畫的**,不是圖檔:水面波紋一直在動,有人許願或附議時會落一滴水
  濺起漣漪。顏色從 CSS 變數讀,所以跟著亮暗模式走;`prefers-reduced-motion` 時
  只畫一格靜態畫面;分頁切到背景就停止動畫,但**不清畫布**(不然回來會看到空白)。
- 整頁 284 個 DOM 節點、零外部請求,離線也能開。

## 想改成別的主題?

這份程式碼裡沒有任何跟「skill」綁死的邏輯 —— 它就是一個**聯署 + 定期結算**的池子。
把 `public/index.html` 的文案換掉就能變成功能許願、選書、選題、社團活動投票。
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
self-contained HTML page — no npm, no Docker, no database server.

```bash
python3 server.py --seed     # http://127.0.0.1:8787
```

- **Read-only static mode**: run `python3 scripts/export_static.py` and host `public/`
  anywhere (GitHub Pages). The page detects the missing backend and degrades to read-only.
- **Anti-abuse**: per-source rate limits in SQLite, one vote per source per wish enforced by
  a DB unique key, duplicate-title merging, input sanitisation, hash-based CSP, fail-closed
  admin endpoints. Raw IPs are never stored — only `sha256(salt + ip)`.
- **Tests**: `scripts/selftest.py` boots the real server over real HTTP (84 checks).
  `--verify-gauge` sabotages five guards and requires the suite to go red, so the suite
  can't quietly become a rubber stamp.

See the tables above for the full API and configuration; MIT licensed.
