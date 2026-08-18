# 把一個站放上 Cloudflare 之後,我們踩到與解掉的東西

這份筆記記的是 [skill-tw.com](https://skill-tw.com)(原始碼:
[skill-wishpool](https://github.com/shark0120/skill-wishpool))在 Cloudflare 後面
實際遇到的問題與取捨。每一條都是實測出來的,不是看文件抄的。

站的性質先講清楚,因為所有取捨都跟它有關:

- 一頁 HTML + 一支 Python 後端,**執行時零外部請求**(動畫引擎在建置時打包內嵌)
- 不放 cookie、不追蹤、沒有帳號系統
- 內容是公開的,**而且我們希望 AI 助手抓得到**

---

## 一、為什麼沒有用 Turnstile / reCAPTCHA / hCaptcha

需要「擋機器人洗版」的時候,第一個念頭都是掛一個 CAPTCHA。但那三個都要載入
外部腳本,對這個站等於同時打破三件事:

1. **零外部請求** —— 使用者的瀏覽器會去連第三方
2. **不追蹤** —— 那些服務本來就在做指紋
3. **CSP 不開洞** —— 我們的 CSP 是 `script-src 'sha256-…'`,要加白名單才裝得上

所以改成**自帶的工作量證明(proof of work)**:送出前瀏覽器要找到一個 nonce,
讓 `sha256(salt:nonce)` 開頭有 N 個 0 bit。實測桌機許願 0.6 秒、投票 0.16 秒。

設計上幾個地方要注意:

- 挑戰用 **HMAC 簽章**,伺服器不存狀態;**綁來源雜湊**,別人的挑戰挪用不了
- **同一份只能兌現一次**(防重放),**有效期 180 秒**(可先領後用,窗口越長越好囤)
- **難度由伺服器認定** —— 客戶端把 `bits` 改小會被擋
- **領挑戰本身也要限流**,不然可以先囤一堆算好的證明再爆發

**誠實的邊界:這不是「人機驗證」。** 它證明的是「有人付了計算成本」,不是
「對方是人類」。買得得起 CPU 的人照樣過得去。真正擋量的是速率限制,PoW 是
讓大量自動化變貴的第二層。這句話我們寫在專案的 README 裡,不含糊帶過。

---

## 二、`error code 1010`:Cloudflare 把 AI 擋在門外

**症狀**:用 `curl` 讀站一切正常,但用 Python 的 `urllib` 直接抓,回 403,
body 只有一行 `error code: 1010`。

**診斷**:拿六種 User-Agent 各打一次。`curl`、瀏覽器、ClaudeBot、GPTBot、
Googlebot **全部 200**;只有 Python 陽春請求 403。所以不是 UA 黑名單,
是**請求標頭組合看起來不像瀏覽器**。

**真因**:Cloudflare 的 **Browser Integrity Check(BIC)**。1010 就是它的錯誤碼。
位置在 **Security → Settings → Browser Integrity Check**(舊介面在 Firewall → Settings)。

**取捨**:這個站要讓 AI 抓得到,所以把 BIC 關掉。但 BIC 是一層防護,關掉之後
應用層就是唯一的防線,所以同時做了三件補償:

| 補償 | 內容 |
|---|---|
| 讀取限流 | 每來源每分鐘 240 次 API 讀取(正常瀏覽一頁只用 3 次),429 帶 `Retry-After` |
| 挑戰限流 | 每來源每分鐘 40 次,堵住「先囤算好的證明」 |
| 縮短時間窗 | PoW 挑戰有效期 300 → 180 秒 |

寫入那一側本來就有 PoW + 每來源每小時 5 願望/60 投票 + 資料庫層的一人一票,
這三層都不依賴 Cloudflare,所以關掉 BIC 沒有動到防洗版的底線。

**判斷準則**:BIC 擋的是「長得不像瀏覽器的請求」,對真正的攻擊者幫助有限
(改個標頭就過),卻剛好把正派的自動化擋在外面。如果你的站希望被機器讀,
這一項通常該關;如果是後台,就該留著。

---

## 三、Cloudflare 會改寫你的 HTML —— 這會讓雜湊型 CSP 整頁死掉

我們的頁面是單檔內嵌 CSS/JS,為了不使用 `'unsafe-inline'`,伺服器在送出頁面時
**即時計算 inline 區塊的 sha256** 寫進 CSP。這樣雜湊永遠不會跟內容脫節。

但這個做法有一個代價:**雜湊是對「我們送出的位元組」算的**。CDN 只要改寫
HTML,雜湊就對不上,整頁 JS 被擋 —— 白畫面,而且不會有任何錯誤提示。

Cloudflare 上有三個開關會改寫 HTML:

| 功能 | 後果 | 建議 |
|---|---|---|
| **Rocket Loader** | 改寫 `<script>` → 雜湊必炸,整頁死 | 關 |
| **Auto Minify (HTML)** | 改寫 inline 區塊 → 雜湊必炸 | 關 |
| **Web Analytics** | 注入 `beacon.min.js` → 被 CSP 擋掉,每次載入留一則 console 錯誤 | 關(否則違反零外部請求) |

我們實測 Web Analytics 是開著的,注入的 beacon **被 CSP 擋下來了**:

```
Loading the script 'https://static.cloudflareinsights.com/beacon.min.js/…' violates
the following Content Security Policy directive: "script-src 'sha256-…'"
```

擋掉是好事,但這代表「頁面會不會死」被交給了 CDN 的設定。自己驗一次最快:

```bash
# 線上頁面 inline script 的雜湊,必須跟 CSP 標頭裡宣告的那個一樣
curl -s https://你的網域/ | python3 -c '
import base64, hashlib, re, sys
body = sys.stdin.buffer.read()
for tag, inner in re.findall(rb"<(script|style)\b[^>]*>(.*?)</\1\s*>", body, re.S | re.I):
    print(tag.decode(), "sha256-" + base64.b64encode(hashlib.sha256(inner).digest()).decode())
'
curl -sI https://你的網域/ | grep -i content-security-policy
```

對不上就是 CDN 改寫了你的 HTML。我們也留了一個逃生開關
(`WISHPOOL_CSP=unsafe-inline`),在不能關 CDN 改寫的環境下寧可 CSP 弱一點,
也不要讓頁面整個死掉。

---

## 四、在 Cloudflare 後面,你拿到的 IP 不是訪客的 IP

這件事不做,「一人一票」會**直接失效而且不會報錯**。

站在 CF 後面時,`$remote_addr` 是 Cloudflare 邊緣節點的位址 —— 同一個機房出來的
所有訪客會被算成同一個人。速率限制會誤殺,投票去重會把不同人擋掉。

正確做法是只信任來自 CF 網段的 `CF-Connecting-IP`:

```nginx
# 由腳本從 https://www.cloudflare.com/ips-v4 與 ips-v6 產生,CF 會增減網段
set_real_ip_from 173.245.48.0/20;
# … 其餘網段 …
real_ip_header CF-Connecting-IP;
real_ip_recursive off;
```

**為什麼要限定網段**:直接無條件相信 `CF-Connecting-IP`,任何人只要繞過 CF
直連原站、自己帶那個標頭,就能偽造成任意 IP。限定網段之後,直連的人偽造不了。

還有一個更容易寫錯的地方 —— 往後端傳的時候:

```nginx
proxy_set_header X-Forwarded-For $remote_addr;          # 對
# proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;   # 錯
```

第二種會把**用戶端自己送來的** `X-Forwarded-For` 接在最前面。如果後端取的是
第一個位址(常見寫法),那等於讓任何人自帶假 IP。

**怎麼驗**:同一個請求分別帶 `X-Forwarded-For: 1.2.3.4` 與 `CF-Connecting-IP: 9.9.9.9`,
看應用層記到的來源雜湊會不會變。我們實測三種請求都得到**同一個雜湊**,才算過關。
另外看 access log 記到的是不是真實訪客 IP,而不是 CF 的位址。

---

## 五、面板(aaPanel/寶塔)+ CDN 的組合坑:正則 location 會繞過你的反向代理

這一條是最近才抓到的,而且**是真的洩漏**。

面板產生的 vhost 裡有兩條正則規則:

```nginx
location ~ .*\.(gif|jpg|jpeg|png|bmp|swf)$  { expires 30d; }
location ~ .*\.(js|css)?$                   { expires 12h; }
```

它們會**直接從磁碟的網站根目錄撈檔案**,優先於我們自己寫的 `location /` 反向代理。
而我們的程式碼就 checkout 在網站根目錄 —— 結果是 repo 裡任何 `.js`/`.css`/圖檔
**都能被公開讀走**。實測 `/src/vendor.js` 回 200。

**修法**:nginx 的正則 location 是**先定義先贏**。面板 vhost 有一行
`include .../extension/<網域>/*.conf;`,而且位置在那兩條之前 —— 所以在自己的
include 裡重新定義同樣的樣式,就能把它們蓋掉,一律轉給應用程式:

```nginx
location ~* \.(js|css|gif|jpg|jpeg|png|bmp|swf|webp|ico|map|json|py|md|toml|lock)$ {
    proxy_pass http://127.0.0.1:8787;
    proxy_set_header Host            $host;
    proxy_set_header X-Forwarded-For $remote_addr;
}
```

修完再驗一次:`/src/vendor.js`、`/package.json`、`/server.py` 全部 404,
`/`、`/robots.txt` 仍然 200。

**通用教訓**:把程式碼 checkout 在網站根目錄很方便,但只要有任何一條規則
繞過你的應用程式直接讀磁碟,整個 repo 就是公開的。動 nginx 之前先問一句
「有沒有別的 location 會比我先匹配到」。

---

## 六、Cloudflare 憑證分三種,拿錯會很危險

| 種類 | 長相 | 權限 | 建議 |
|---|---|---|---|
| **Global API Key** | 37 位十六進位 | **整個帳號、所有網域、DNS、帳單全開,不能限縮** | 幾乎永遠不要用 |
| **API Token** | `Authorization: Bearer …` | 可以限到「單一網域的單一權限」 | 要自動化就用這個 |
| **R2 API Token / S3 金鑰** | `cfat_…` + Access Key/Secret | 物件儲存的讀寫刪 | 只跟 R2 有關,改不了網域設定 |

要讓別人(或 AI)代你改一項設定,正確做法是開一個 **Zone → Zone Settings → Edit**、
Zone Resources 只選那一個網域的 **API Token**。萬一外流,能被動的也只有那一個網域的設定。

**另外**:任何憑證只要貼進聊天視窗、issue、截圖,就當作已經外洩,直接去後台
重置。這比事後檢討便宜太多。

---

## 七、順帶一提:我們怎麼確定這些修復是真的

這個專案有一個習慣:**每加一道防護,就加一條會紅的測試**,而且會反過來驗證
「這把尺量得準不準」。

```bash
python3 scripts/selftest.py                 # 131 項端到端(真的起伺服器、真的打 HTTP)
python3 scripts/selftest.py --verify-gauge  # 把 9 個防護分別改壞,要求測試必須變紅
```

`--verify-gauge` 抓到過一個假綠燈:目錄逃脫的測試原本用 `urllib` 發 `/../x`,
但 `urllib` 會先把路徑正規化成 `/x` —— 那條測試**從來沒送出過 `..`**。
把逃脫檢查整段拆掉,測試照樣全綠。

一套永遠會綠的測試,比沒有測試更危險。

---

*視覺設計的方向、配色節奏與版面手感,來自 [顏世倫](https://www.facebook.com/yan.shi.lun.933337/)。*
