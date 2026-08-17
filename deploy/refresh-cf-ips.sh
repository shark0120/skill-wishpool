#!/bin/sh
# 產生 / 更新 Cloudflare 真實 IP 設定。Cloudflare 的網段會增減,建議每季跑一次。
#
#   sudo sh deploy/refresh-cf-ips.sh /www/server/panel/vhost/nginx/extension/cloudflare-realip.conf
#
# 為什麼需要:站在 Cloudflare 後面時 $remote_addr 是 CF 邊緣節點,同一機房出來的
# 訪客會被當成同一個人 —— 速率限制誤殺、一人一票失效。只信任 CF 網段送來的
# CF-Connecting-IP,直連原站的人就偽造不了。
set -eu

OUT="${1:-/www/server/panel/vhost/nginx/extension/cloudflare-realip.conf}"
TMP="$(mktemp)"
trap 'rm -f "$TMP"' EXIT

printf '# 由 deploy/refresh-cf-ips.sh 產生,不要手改。\n' > "$TMP"
printf '# 來源:https://www.cloudflare.com/ips-v4 與 ips-v6\n' >> "$TMP"

n=0
for url in https://www.cloudflare.com/ips-v4 https://www.cloudflare.com/ips-v6; do
    body="$(curl -fsS -m 15 "$url")" || { echo "抓不到 $url,原設定不動。" >&2; exit 1; }
    for cidr in $body; do
        case "$cidr" in
            *[0-9a-fA-F:.]*/*) printf 'set_real_ip_from %s;\n' "$cidr" >> "$TMP"; n=$((n + 1)) ;;
            *) ;;
        esac
    done
done

# 抓到的網段數量明顯不對就中止 —— 寧可保留舊設定,也不要寫出一份空的
# (空的等於信任所有來源送來的 CF-Connecting-IP,比沒設更糟)。
if [ "$n" -lt 10 ]; then
    echo "只解析到 $n 個網段,看起來不對,原設定不動。" >&2
    exit 1
fi

printf 'real_ip_header CF-Connecting-IP;\nreal_ip_recursive off;\n' >> "$TMP"

mkdir -p "$(dirname "$OUT")"
cat "$TMP" > "$OUT"
chmod 644 "$OUT"
echo "寫出 $OUT($n 個 Cloudflare 網段)"
echo "接著跑:nginx -t && systemctl reload nginx(或面板的 reload)"
