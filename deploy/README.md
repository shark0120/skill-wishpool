# 部署

前提:主機上**可能已經跑著別的網站**。這份流程的順序是為了不弄掉它們,不要跳步。

## 0. 先確認你不會弄掉現有的站

```bash
nginx -T | grep -E "listen .*(80|443)" | sort -u   # 誰已經佔著 80/443
systemctl is-active nginx
```

**這個服務不佔 80/443。** 它只綁 `127.0.0.1:8787`,對外靠既有的 nginx 反代。
如果你打算讓它自己聽 443,那你會跟現有站台打架 —— 不要這樣做。

## 1. 放檔案

```bash
sudo useradd --system --home /var/lib/skill-wishpool --shell /usr/sbin/nologin wishpool
sudo mkdir -p /opt/skill-wishpool /var/lib/skill-wishpool
sudo git clone https://github.com/shark0120/skill-wishpool.git /opt/skill-wishpool
sudo chown -R root:root /opt/skill-wishpool          # 程式碼唯讀
sudo chown -R wishpool:wishpool /var/lib/skill-wishpool
sudo chmod 750 /var/lib/skill-wishpool
```

程式碼放 `/opt`(唯讀)、資料放 `/var/lib`(唯一可寫的地方)。
systemd unit 的 `ProtectSystem=strict` + `ReadWritePaths` 就是照這個假設寫的。

## 2. 管理端權杖

```bash
sudo tee /etc/skill-wishpool.env >/dev/null <<EOF
WISHPOOL_ADMIN_TOKEN=$(python3 -c 'import secrets;print(secrets.token_urlsafe(32))')
WISHPOOL_TRUST_PROXY=1
EOF
sudo chmod 600 /etc/skill-wishpool.env
```

- `WISHPOOL_ADMIN_TOKEN` 沒設的話管理端會整組回 503(fail-closed),不是變成誰都能改。
- `WISHPOOL_TRUST_PROXY=1` **只有在第 4 步的 nginx 設定正確覆寫 `X-Forwarded-For` 之後才可以開**。
  順序反了會有一段時間任何人都能自帶假 IP 繞過速率限制。

## 3. 起服務

```bash
sudo cp /opt/skill-wishpool/deploy/systemd/skill-wishpool.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now skill-wishpool
curl -s http://127.0.0.1:8787/api/health | head -c 300     # 這裡就要看到 JSON
```

`curl` 沒回東西就先看 `journalctl -u skill-wishpool -n 50`,不要往下做。

## 4. 反向代理

```bash
sudo cp /opt/skill-wishpool/deploy/nginx/skill-wishpool.conf /etc/nginx/conf.d/
sudo vim /etc/nginx/conf.d/skill-wishpool.conf     # 改 server_name 與憑證路徑
sudo nginx -t                                      # 必須通過才繼續
sudo systemctl reload nginx                         # reload,不是 restart
```

用 `reload` 不用 `restart`:reload 是平滑換設定,現有站台的連線不會斷。

> **`nginx -t` 通過不代表沒事。** 它只驗語法,不驗憑證檔存不存在、不驗上游通不通。
> 下一步的實測才算。

## 5. 實測(這一步不能省)

```bash
curl -sI https://wish.example.com/ | head -3                    # 新站活著
curl -s  https://wish.example.com/api/health | head -c 200       # API 活著
curl -sI https://你原本的站/ | head -3                            # 舊站沒被弄掉 ★
```

★ 這一條最重要。改完 nginx 一定要回頭確認**原本的站還在**。

再確認一次 `X-Forwarded-For` 沒有被偽造的空間:

```bash
# 自帶一個假 IP,伺服器不應該採信(它會取第一個位址,而 nginx 應該整個覆寫掉)
curl -s -H 'X-Forwarded-For: 1.2.3.4' https://wish.example.com/api/health -o /dev/null -w '%{http_code}\n'
```

驗法:連續打超過每小時上限的許願請求,如果換 `X-Forwarded-For` 就能繼續許願,
就是 nginx 那行寫成 `$proxy_add_x_forwarded_for` 了 —— 回去改成 `$remote_addr`。

## 6. 備份

要備份的只有兩個東西:

```bash
/var/lib/skill-wishpool/wishes.db     # 願望、票、輪次結果
/var/lib/skill-wishpool/ip_salt       # IP 雜湊的鹽
```

鹽掉了不會弄壞資料,但既有的「一人一票」關聯會全部斷掉(大家可以重複附議一次)。

SQLite 是 WAL 模式,**不要直接 `cp` 熱資料庫**:

```bash
sqlite3 /var/lib/skill-wishpool/wishes.db ".backup '/tmp/wishes-$(date +%F).db'"
```

## 更新

```bash
cd /opt/skill-wishpool && sudo git pull
sudo -u wishpool python3 scripts/selftest.py      # 先在這台機器上驗過再重啟
sudo systemctl restart skill-wishpool
curl -s http://127.0.0.1:8787/api/health | head -c 200
```

## aaPanel / 寶塔:網站已經在面板裡建好了

這是最常見的情況(主機上已經跑著一堆站)。**不要去改面板產生的 vhost 檔** ——
面板改設定時會覆寫它。用面板已經幫你 include 的 extension 目錄:

```bash
# 1. Cloudflare 真實 IP(站在 CF 後面就一定要做,否則所有訪客共用邊緣 IP)
sudo sh deploy/refresh-cf-ips.sh /www/server/panel/vhost/nginx/extension/cloudflare-realip.conf

# 2. 反向代理片段
sudo cp deploy/nginx/aapanel-extension-include.conf \
        /www/server/panel/vhost/nginx/extension/skill-tw.com/wishpool.conf

# 3. 測試語法,通過才 reload
sudo /www/server/nginx/sbin/nginx -t
sudo /etc/init.d/nginx reload      # 面板的 nginx 不是 systemd 服務
```

面板 vhost 裡本來就有這一行,所以放進去就生效:

```nginx
include /www/server/panel/vhost/nginx/extension/<你的網域>/*.conf;
```

三件容易踩的事:

- **`limit_req_zone` 不能放在這個檔裡。** 那個指令只能在 `http` 區塊,放進 server
  片段會讓整個 nginx 起不來 —— 連帶弄掉主機上所有其他站。
- **`.well-known` 要留給憑證續簽。** 面板 vhost 裡有 `location ~ \.well-known`
  (正則),優先於我們的 `location /`,所以照原樣就會運作。不要自己再加一條蓋掉它。
- **reload 不要 restart。** reload 是平滑換設定,其他站的連線不會斷。

## ⚠️ 放在 Cloudflare(或任何會改寫 HTML 的 CDN)後面

伺服器送出頁面時會即時算 inline `<script>`/`<style>` 的 sha256 並寫進 CSP。
這讓單檔頁面也能拿到不含 `'unsafe-inline'` 的 CSP —— 但它有一個代價:

**雜湊是對「我們送出的位元組」算的。CDN 只要改寫 HTML,雜湊就對不上,整頁 JS 被擋成白畫面。**

Cloudflare 上要檢查三個開關(Speed → Optimization / Analytics):

| 功能 | 影響 | 該怎麼設 |
|---|---|---|
| **Rocket Loader** | 會改寫 `<script>` → **雜湊必炸,整頁死** | **關掉** |
| **Auto Minify(HTML)** | 會改寫 inline 區塊 → 雜湊必炸 | **關掉** |
| **Web Analytics / Browser Insights** | 注入 `beacon.min.js` → 被 CSP 擋掉,每次載入留一則 console 錯誤,而且違反「零外部請求」 | **關掉**(想留就改用 `WISHPOOL_CSP=unsafe-inline`,但那等於放棄這道防線) |

實測(skill-tw.com,2026-08-17):Web Analytics 是開著的,beacon 被 CSP 擋下:

```
Loading the script 'https://static.cloudflareinsights.com/beacon.min.js/…' violates
the following Content Security Policy directive: "script-src 'sha256-…'"
```

擋掉是好事(追蹤沒生效),但那三個開關沒關就等於把「頁面會不會死」交給 CDN 的設定。
自己驗一次最快:

```bash
# 線上頁面的 inline script 雜湊,必須跟 CSP 標頭裡宣告的那個一樣
curl -s https://你的網域/ | python3 -c '
import base64, hashlib, re, sys
body = sys.stdin.buffer.read()
for tag, inner in re.findall(rb"<(script|style)\b[^>]*>(.*?)</\1\s*>", body, re.S | re.I):
    print(tag.decode(), "sha256-" + base64.b64encode(hashlib.sha256(inner).digest()).decode())
'
curl -sI https://你的網域/ | grep -i content-security-policy
```

兩邊的 sha256 對不上,就是 CDN 改寫了你的 HTML。

## 只想放一個唯讀展示站

不用起服務、不用改 nginx:

```bash
python3 scripts/export_static.py
# 把 public/ 的內容丟進任何一個既有站台的目錄就好
```

前端偵測不到後端會自動退成唯讀模式,許願按鈕改成導去 GitHub 開 issue。
