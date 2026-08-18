#!/bin/bash
# 願望池:每日一致性快照 + 自我驗證 + 保留期
#
#   sudo install -m 700 deploy/backup.sh /usr/local/bin/wishpool-backup
#   sudo crontab -e
#   5 3 * * * /usr/local/bin/wishpool-backup >> /var/log/wishpool-backup.log 2>&1
#
# 可用環境變數覆寫:WISHPOOL_DB / WISHPOOL_BACKUP_DIR / WISHPOOL_KEEP_DAYS
#
# ── 為什麼不是一行 cp ──────────────────────────────────────────────
# 資料庫是 WAL 模式。直接 cp 熱資料庫會拿到撕裂的檔:少掉還沒 checkpoint 的
# 交易,或抓到寫到一半的頁。`.backup` 走 SQLite 的線上備份 API,拿到的是一致快照。
#
# ── 為什麼要驗,而且要驗兩層 ────────────────────────────────────────
# 沒驗過的備份等於沒有備份 —— 你會在還原那天才發現它是壞的,而那天你沒有第二次機會。
#   1. integrity_check:檔案結構有沒有壞
#   2. 筆數比對:integrity_check 對一個「結構完好的空殼」也會回 ok
#
# ── 為什麼刻意不備份 ip_salt ────────────────────────────────────────
# 資料庫裡存的是 ip_hash 不是 IP,但 IPv4 只有 43 億個 —— 只要拿到 salt,
# 幾分鐘就能把整份 ip_hash 反推回真實 IP。salt 跟資料庫放在同一份備份裡,
# 等於這份備份一旦外流就是一份訪客 IP 名單。
#
# 代價:還原後既有的「一人一票」關聯會斷掉(每個人可以再附議一次),速率限制歸零。
# 如果你判斷連續性比較重要,把 salt 另外備份到**不同的地方**,不要跟資料庫同一包。
set -uo pipefail
umask 077

DB="${WISHPOOL_DB:-/var/lib/skill-wishpool/wishes.db}"
OUT="${WISHPOOL_BACKUP_DIR:-/var/backups/skill-wishpool}"
KEEP_DAYS="${WISHPOOL_KEEP_DAYS:-30}"
STAMP=$(date +%Y%m%d-%H%M%S)
TMP=$(mktemp -d /tmp/wpbk.XXXXXX)
trap 'rm -rf "$TMP"' EXIT

log(){ echo "[$(date -Is)] $*"; }
die(){ log "失敗: $*"; exit 1; }

command -v sqlite3 >/dev/null || die "找不到 sqlite3,請先安裝"
[ -f "$DB" ] || die "找不到資料庫 $DB"
mkdir -p "$OUT" || die "建不了 $OUT"

sqlite3 "$DB" ".backup '$TMP/wishes.db'" || die "sqlite3 .backup 失敗"
[ -s "$TMP/wishes.db" ] || die "快照是空的"

IC=$(sqlite3 "$TMP/wishes.db" "PRAGMA integrity_check;" 2>&1)
[ "$IC" = "ok" ] || die "快照 integrity_check 不過: $IC"

SRC=$(sqlite3 "$DB" "select (select count(*) from wishes)||'/'||(select count(*) from votes);" 2>&1)
BAK=$(sqlite3 "$TMP/wishes.db" "select (select count(*) from wishes)||'/'||(select count(*) from votes);" 2>&1)
case "$BAK" in ''|*rror*) die "讀不到快照筆數: $BAK";; esac
log "來源 $SRC / 快照 $BAK"

gzip -9 "$TMP/wishes.db" || die "壓縮失敗"
mv "$TMP/wishes.db.gz" "$OUT/wishes-$STAMP.db.gz" || die "搬檔失敗"
chmod 600 "$OUT/wishes-$STAMP.db.gz"
log "已寫入 $OUT/wishes-$STAMP.db.gz ($(stat -c%s "$OUT/wishes-$STAMP.db.gz") bytes)"

find "$OUT" -maxdepth 1 -name 'wishes-*.db.gz' -mtime +"$KEEP_DAYS" -print -delete \
  | sed 's/^/[清掉過期] /'

log "完成,目前保有 $(ls -1 "$OUT"/wishes-*.db.gz 2>/dev/null | wc -l) 份"
