---
name: false-green-audit
description: 找出「測試通過但其實測錯東西」的假綠燈——測到錯的設定檔、錯的二進位、錯的環境、被靜默吞掉的輸出、永遠不會失敗的斷言。當使用者說「明明測過了怎麼還是壞」「本機好好的上線就掛」「nginx -t 通過但 reload 失敗」「測試都綠的」「怎麼會沒抓到」「CI 過了但實際不行」時使用。任何「驗證通過」之後、做不可逆動作之前應主動跑一次。
---

# false-green-audit

## 核心問題

綠燈有兩種:**「它真的沒問題」** 和 **「我沒測到問題」**。兩者長得一模一樣。

假綠燈比紅燈危險得多 —— 紅燈會讓你停下來,假綠燈讓你充滿信心地把壞東西推上線。

## 五種假綠燈(依實際踩到的頻率排序)

### 1. 測到錯的設定檔 / 錯的二進位

系統路徑上的工具與實際運行的服務**不是同一份**。

```bash
nginx -t
# nginx: configuration file /etc/nginx/nginx.conf test is successful   ← 綠
```
但實際跑的是:
```bash
ps -eo cmd | grep "[n]ginx: master"
# nginx: master process /www/server/nginx/sbin/nginx -c /www/server/nginx/conf/nginx.conf
```
**測的和跑的是兩個不同的設定檔。** 用對的一測就爆 `duplicate location`。

**通則**:先找出**實際運行的進程**用的是哪個二進位、哪個設定,再用那一組測。

```bash
ps -eo pid,cmd | grep "[m]aster\|[s]erver"        # 真正在跑的
readlink -f "$(command -v tool)"                   # PATH 上的
systemctl cat svc 2>/dev/null | grep ExecStart     # systemd 認為的
```

### 2. 輸出被靜默吞掉

```bash
python -m pytest -q     # 但 pyproject 的 addopts 已經有 -q → 變成 -qq → 完全不印統計行
```
你看到「沒有錯誤」,其實是**沒有輸出**。

```bash
cmd | head -5           # head 提前關閉,SIGPIPE 讓上游死掉,你以為它跑完了
grep pattern file       # 沒有 -q 卻只看 exit code;檔案不存在也是非 0
set -e                  # 在 pipeline 裡只看最後一個指令的退出碼(除非 set -o pipefail)
```

**檢查**:刻意讓它失敗一次。看不到紅燈的驗證不是驗證。

### 3. 正則沒有你以為的意思

```bash
grep -c $'\r' f     # BRE 不認 \r;很多 shell 下這在數含字母 r 的行
grep -E '[0-9]+' f  # 沒有 ^$ 錨點,"abc123" 也算過
```

**檢查**:拿一個**應該不匹配**的樣本餵進去,確認它真的不匹配。

### 4. 斷言永遠為真

```python
assert result is not None          # 幾乎不可能失敗
assert len(items) >= 0             # 恆真
assert "error" not in output.lower()   # output 為空時通過
mock.assert_called()               # 有呼叫就算過,不管參數對不對
```

**檢查(最有效的一招)**:**把 bug 放回去,確認測試會紅。**
綠燈證明不了測試有效;紅燈才能。

```
把缺陷重新植入 → 跑測試 → 必須失敗,而且錯誤訊息要指出真正的失敗模式
→ 移除缺陷 → 必須通過
```
兩個方向都要驗。只驗一邊等於沒驗。

### 5. 環境不對等

- 本機有 `curl` / `python3` / 特定 locale,目標機器沒有
- 測試用 root 跑,實際用非特權使用者跑
- 測試在同一台機器上,實際跨網路(逾時、緩衝、proxy 全都不同)
- 容器內的 UID 與映像烙印的 UID 不同 → 掛載的 volume 寫不進去
- Windows 開發、Linux 部署(行尾、路徑分隔、大小寫敏感)

## 檢查清單(不可逆動作前跑一次)

- [ ] 我測的二進位/設定,和實際會跑的是**同一份**嗎?(`ps` 確認,不要用 `which` 猜)
- [ ] 我看到的「通過」是真的有輸出,還是**沒有輸出**?
- [ ] 我讓它失敗過一次嗎?失敗時的訊息**指得出真正原因**嗎?
- [ ] 斷言有可能為假嗎?把缺陷放回去試過嗎?
- [ ] 環境(使用者、路徑、網路、平台、行尾)跟正式環境對得上嗎?
- [ ] 有沒有 `|| true`、`2>/dev/null`、`-q`、`|| :` 把失敗吃掉?
- [ ] exit code 我真的檢查了嗎,還是只看有沒有紅字?

## 反模式

- **「跑起來沒報錯」** 當成驗證通過 —— 沒報錯可能是根本沒執行到。
- **只驗成功路徑** —— 監看/測試的過濾條件必須也涵蓋失敗特徵,否則崩潰時是靜默的,
  而靜默看起來跟「還在跑」一模一樣。
- **信任宣稱** —— 「已修復」的 commit message 不是證據,重跑才是。
- **改完不重驗** —— 任何改動都可能讓先前的綠燈失效(尤其雜湊、快照、產生的檔案)。

## 安全界

- 本 skill 是**診斷用**:只讀、只重跑既有檢查,不改生產設定。
- 需要刻意植入缺陷來驗證測試時,**在暫存副本或分支上做**,並確保復原。
- 找到假綠燈不要自行降低門檻或改斷言讓它「看起來對」—— 回報並修真正的問題。
