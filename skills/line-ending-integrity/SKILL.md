---
name: line-ending-integrity
description: 處理 CRLF/LF 造成的隱形災難——shell 腳本在 Linux 上 bad interpreter、發佈的 SHA256 永遠對不上、diff 顯示整檔變更但內容相同、CI 在 Windows runner 上莫名失敗。當使用者說「腳本在伺服器上跑不起來」「bad interpreter」「^M」「雜湊對不上」「diff 全紅但我沒改」「Windows 上正常 Linux 上壞掉」「git 說檔案變了但看起來一樣」時使用。跨平台專案發佈前必查。
---

# line-ending-integrity

## 為什麼這個會咬人

行尾字元是**看不見的**。編輯器不顯示、`diff` 輸出看起來正常、`cat` 看起來一樣。
但它會造成三種完全不同的災難,而且症狀都不指向真正的原因。

## 三種災難

### 1. `bad interpreter: /bin/sh^M`

CRLF 的 shell 腳本在 Linux 上,`#!/bin/sh\r` 的 `\r` 被當成直譯器路徑的一部分。
錯誤訊息裡的 `^M` 幾乎沒人看得懂。

```bash
file script.sh        # "with CRLF line terminators" ← 就是它
head -1 script.sh | xxd | head -1
```

### 2. 發佈的雜湊永遠對不上(最危險)

網站叫使用者「下載 → 對雜湊 → 讀過 → 再執行」。如果發佈的摘要算的是 CRLF 版、
而使用者拿到的是 LF 版(或反過來),**雜湊永遠不符**。

後果不是「使用者發現問題」,而是**使用者學會跳過驗證** —— 你親手訓練他們忽略
唯一能保護他們的那道防線。

> 真實案例:三個安裝腳本磁碟上 CRLF、git 裡 LF,`.sha256` 釘的是 CRLF 位元組。
> 傳 CRLF → Linux 上直接掛;傳 LF → 摘要永遠錯。**兩種傳法都是錯的。**

### 3. 「我沒改啊」的整檔 diff

`git diff` 顯示每一行都變了,但內容一模一樣。審查者看到 500 行變更就跳過細看 ——
真正的改動藏在裡面沒人發現。

## 診斷(照順序)

```bash
# 1. 磁碟上到底是什麼
python -c "b=open('f','rb').read(); print('CRLF',b.count(b'\r\n'),'LF-only',b.count(b'\n')-b.count(b'\r\n'))"

# 2. git 存的是什麼(可能與磁碟不同!)
git show :path/to/f | python -c "import sys;b=sys.stdin.buffer.read();print('CRLF',b.count(b'\r\n'))"

# 3. 三方比對:磁碟 / git blob / 發佈的摘要
disk=$(sha256sum f | cut -d' ' -f1)
blob=$(git show :f | sha256sum | cut -d' ' -f1)
pub=$(grep -oE '[a-f0-9]{64}' f.sha256)
[ "$disk" = "$blob" ] && [ "$disk" = "$pub" ] && echo MATCH || echo DRIFT

# 4. 現行設定
git config core.autocrlf
cat .gitattributes 2>/dev/null
```

**陷阱**:`grep -c $'\r' f` 不可靠 —— BRE 不認 `\r`,很多 shell 下它會去數含字母 `r` 的行。
一定要用 python 或 `file`。

## 修法

### 釘住 `.gitattributes`(唯一可靠的做法)

`core.autocrlf` 是**每台機器**的設定,你控制不了貢獻者的機器。`.gitattributes` 進版控,
對所有人生效,而且會覆蓋 `autocrlf`。

```gitattributes
# 位元組是關鍵的檔案:腳本要能在 Linux 執行,摘要要對得上
*.sh        text eol=lf
*.ps1       text eol=lf
*.sha256    text eol=lf
*.bash      text eol=lf
Dockerfile* text eol=lf
*.py        text eol=lf

# Windows 專用的批次檔反而需要 CRLF
*.bat       text eol=crlf
*.cmd       text eol=crlf

# 二進位絕不轉換
*.png binary
*.zip binary
```

### 正規化既有檔案

```bash
python - <<'EOF'
import pathlib
for f in ("a.sh","b.ps1"):
    p = pathlib.Path(f); b = p.read_bytes(); n = b.replace(b"\r\n", b"\n")
    if n != b: p.write_bytes(n); print(f, "CRLF -> LF")
EOF
```

**正規化之後一定要重算所有雜湊**,並重跑三方比對。

### 讓它無法再退化

CI 加一個 job:

```yaml
- name: line endings and digests
  run: |
    for f in site/*.sh site/*.ps1; do
      python -c "import sys;b=open('$f','rb').read();sys.exit(b'\r\n' in b)" \
        || { echo "CRLF in $f"; exit 1; }
    done
    cd site && sha256sum -c *.sha256
```

雜湊檢查本身就是最好的行尾守衛 —— 行尾一變,雜湊立刻不符。

## 順序很重要

1. 先 `.gitattributes`
2. 再正規化檔案
3. **最後**才算雜湊
4. 三方驗證(磁碟 = git blob = 發佈值)
5. 執行測試(`sh -n`、實際跑一次)

順序顛倒就會算到錯的位元組,而且你不會知道。

## 安全界

- 正規化是**破壞性**的批次改檔:先確認在版控裡、或先備份。
- 不要對二進位檔做行尾轉換(會毀檔)。`.gitattributes` 標 `binary`。
- 不要為了讓雜湊對上而改雜湊 —— 要改的是檔案。先確定哪一種行尾是正確的,再算。
- `*.bat` / `*.cmd` 需要 CRLF,別一律轉 LF。
