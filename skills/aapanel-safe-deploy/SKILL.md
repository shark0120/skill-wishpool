---
name: aapanel-safe-deploy
description: 在跑著多個線上網站的 aaPanel/寶塔主機上安全部署新服務,不弄掉現有站。當使用者說「部署到伺服器」「上傳網站」「加一個新站」「docker compose 上線」「反向代理」「會不會影響其他網站」「寶塔」「aaPanel」「nginx 反代」時使用。特別針對「新服務想佔 80/443,但 nginx 已經在跑」這個必炸的情境。
---

# aapanel-safe-deploy

## 這個 skill 存在的理由

多數 docker-compose 部署包預設讓自己的 edge(Caddy/Traefik/nginx 容器)綁 **80/443**。
在共享主機上照著跑,結果是:**埠被佔 → 容器起不來,或更糟,現有 nginx 被擠掉 → 全部網站同時下線。**

實例:一台 aaPanel 主機跑著 **28 個網站**,直接 `docker compose up` 會全滅。

## 鐵律

1. **先數埠,再談部署。** 沒確認 80/443 誰在用之前,不要執行任何 compose。
2. **新服務綁 loopback,不綁 0.0.0.0。** 對外一律由既有 nginx 反代。
3. **`nginx -t` 通過才 reload。** 失敗就停手,不要硬上。
4. **設定用 include 加法,不改主檔。** 面板更新不會打架,回滾就是刪一個檔。
5. **導流一律 302,不用 301。** 301 被永久快取,反悔救不回來。

## 步驟

### 1. 唯讀勘查(不改任何東西)

```bash
# 誰佔了 80/443
ss -ltnp | grep -E ':(80|443)\s'
# 這台主機有幾個站
ls /www/server/panel/vhost/nginx/*.conf | wc -l
# 目標站存在嗎、憑證有嗎
ls -la /www/wwwroot/<domain>/ 2>/dev/null
ls /www/server/panel/vhost/cert/<domain>/ 2>/dev/null
# 空閒埠
for p in 8081 8082 8090 9000; do ss -ltn | grep -q ":$p " && echo "$p BUSY" || echo "$p free"; done
# DNS 是否指到這台
getent hosts <domain>; hostname -I | awk '{print $1}'
# 系統狀態
df -h /; free -m; docker --version; docker compose version
test -f /var/run/reboot-required && echo "REBOOT PENDING"
```

**判斷**:80/443 已被佔 → **必須走反代模式**,不要用 standalone compose。

### 2. 備份

```bash
cp /www/server/panel/vhost/nginx/<domain>.conf /root/<domain>.conf.bak-$(date +%F-%H%M%S)
cd /www/wwwroot/<domain> && tar czf /root/<domain>-webroot-$(date +%F-%H%M%S).tar.gz .
```

### 3. 靜態內容先上(零風險)

面板已經建好 vhost + 憑證的話,靜態檔案直接放進 webroot 就會被服務。
**先做這一步驗證管線通不通**,再談動態服務。

保留這些不要刪:`.well-known/`(TLS 續簽)、`.user.ini`、`.htaccess`。

```bash
# 驗證交付(尤其確認面板沒擋掉你要的副檔名,例如 .sh)
curl -sI https://<domain>/<file> | head -3
```

### 4. 服務綁 loopback

compose 裡:
```yaml
ports:
  - "127.0.0.1:8081:8081"   # ← 絕不是 "8081:8081"(那是 0.0.0.0)
```
edge 容器整個拿掉,不要 caddy/traefik。

### 5. nginx 反代用 include 加法

aaPanel 的 vhost 主檔會 include:
```
/www/server/panel/vhost/nginx/extension/<domain>/*.conf
```
把片段放這裡,**面板重寫主檔時不會清掉**。

**LLM 串流必須加這些,否則長回應會被無聲切斷:**
```nginx
location /api/ {
    proxy_pass http://127.0.0.1:8081/;
    proxy_http_version 1.1;
    proxy_set_header Connection "";
    proxy_buffering off;                 # 不緩衝,否則 SSE 卡住
    proxy_request_buffering off;
    proxy_read_timeout 600s;             # 預設 60s 會砍掉長生成
    proxy_send_timeout 600s;
    gzip off;                            # 壓縮會破壞 event-stream
    add_header X-Accel-Buffering no;
    proxy_set_header X-Real-IP $remote_addr;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
}
location ^~ /v0/management/ { return 404; }   # 管理面永不對外
```

Cloudflare 後面要拿真實 IP:`real_ip_header CF-Connecting-IP;` + `set_real_ip_from <CF 網段>`。

### 6. 測試再 reload

```bash
nginx -t          # 失敗 → 停手,修好再來
nginx -s reload   # 通過 → reload 不會中斷其他站
```

### 7. 冒煙測試(含串流)

```bash
curl -sI https://<domain>/ | head -3
curl -s -o /dev/null -w "%{http_code}\n" https://<domain>/api/health
curl -sN https://<domain>/api/<streaming-endpoint> | head -5   # 串流真的會流嗎
curl -s -o /dev/null -w "%{http_code}\n" https://<domain>/v0/management/  # 期望 404
# 確認其他站沒事
for d in <other-domains>; do curl -s -o /dev/null -w "$d %{http_code}\n" https://$d/; done
```

**最後那一行是重點** —— 每次改完都要確認鄰居還活著。

## 回滾(10 秒)

```bash
rm /www/server/panel/vhost/nginx/extension/<domain>/<your>.conf
nginx -t && nginx -s reload
```

## 不要自己決定的事

- **重開機**:待生效的 kernel 更新會讓所有站中斷,時間點由擁有者選。
- **改 UFW / 面板埠**:可能把自己鎖在外面。
- **關閉或導流既有服務**:若該服務有會員、餘額、API 金鑰,牽涉別人的錢和程式,必須先公告。
- **裝系統套件**(fail2ban 等):正式機上可能與面板既有防護衝突,先問。

## 安全界

- 密碼不進任何檔案;用 SSH 金鑰。金鑰安裝前先確認 `authorized_keys` 沒被清空。
- 不 `rm -rf` 任何 webroot;要清先 tar 備份。
- 不動 `/www/server/panel/` 底下面板自己的檔案(除了 extension include 目錄)。
