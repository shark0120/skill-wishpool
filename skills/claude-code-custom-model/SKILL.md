---
name: claude-code-custom-model
description: 讓 Claude Code / Codex 正確接上自訂模型或第三方代理(ANTHROPIC_BASE_URL),包含解鎖真實 1M 上下文、避免提早壓縮、以及對話中 system 訊息造成的串流 400。當使用者說「Claude Code 接自訂模型」「ANTHROPIC_BASE_URL」「接代理」「自己的 API 接 Claude Code」「上下文只有 200K」「一直 auto-compact」「Codex 接自訂模型」「串流 400」時使用。
---

# claude-code-custom-model

## 隔離優先(先做這個)

**絕不覆蓋使用者原本的登入。** 用獨立設定目錄:

```bat
set CLAUDE_CONFIG_DIR=%USERPROFILE%\.myproxy-claude
set CODEX_HOME=%USERPROFILE%\.myproxy-codex
```

這樣訂閱版和代理版可以同時開兩個視窗,互不干擾。**改使用者現有的設定檔是最容易被討厭的事。**

## 接線

```bat
set ANTHROPIC_BASE_URL=http://127.0.0.1:8320
set ANTHROPIC_AUTH_TOKEN=<proxy key>
set ANTHROPIC_MODEL=<your-model-name>
set ANTHROPIC_SMALL_FAST_MODEL=<cheap-model>
set API_TIMEOUT_MS=600000
set CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC=1
```

## 1M 上下文:預設會被當成 200K

**Claude Code 對不認得的模型名假設 200K**,於是在遠早於實際上限的地方就 auto-compact。
官方環境變數(文件 env-vars,v2.1.193+ 對不認得的模型名直接生效):

```bat
set CLAUDE_CODE_MAX_CONTEXT_TOKENS=1000000
set CLAUDE_CODE_MAX_OUTPUT_TOKENS=64000
```

相關可調項:
| 變數 | 作用 |
|---|---|
| `CLAUDE_CODE_AUTO_COMPACT_WINDOW` | 壓縮計算用的容量(不會超過真實上限) |
| `CLAUDE_AUTOCOMPACT_PCT_OVERRIDE` | 幾 % 觸發壓縮(只能調低) |
| `DISABLE_AUTO_COMPACT=1` | 關自動壓縮(`/compact` 仍可手動) |
| `CLAUDE_CODE_DISABLE_1M_CONTEXT=1` | 反向:強制當 200K |

`[1m]` 後綴(`sonnet[1m]`)只對官方模型名有文件保證;**自訂名稱請用上面的環境變數**,
別依賴後綴。Claude Code 會在送出前把後綴剝掉。

**Codex 端**(`$CODEX_HOME/config.toml`):
```toml
model_context_window = 1000000
model_max_output_tokens = 65536
```

## 串流 400:對話中的 system 訊息

**症狀**:非串流正常,串流回 `400 Request contains an invalid argument`,而且**每次都失敗**。

**原因**:Claude Code ≥2.1.x(`mid-conversation-system` beta)會在對話中間插入
`role: "system"` 的訊息。很多翻譯層原樣轉發 `messages[].role`,而 Gemini 等上游的
串流端點不接受 `system` 這個角色 —— 非串流端點卻容忍,所以很難發現。

**診斷法**(值得學起來,對任何「只有真實客戶端會失敗」的情境都適用):
1. 從代理的錯誤 log 撈出**完整原始請求 body**
2. 原樣重放 → 重現 400
3. 拿掉 `stream: true` → 200(**這一步就鎖定是串流路徑**)
4. 逐欄位加回最小請求,直到 400 出現
5. 逐 message / 逐 block 二分,找到最小重現

**修法**:在翻譯層把 `messages[].role == "system"` 映射成 `"user"`。
(CLIProxyAPI 上游 v7.2.93 就是這樣修的;更早版本需要前置 shim。)

前置 shim 的注意事項:
- 必須**拒絕 chunked**(回 411)或先解碼,絕不能轉發 `Content-Length: 0` 卻留下未讀 body
  —— 那是請求走私,殘留位元組會被當成下一個請求解析
- `Content-Length` 解析要 try/except + 上限,否則畸形值會讓 handler 崩潰
- 串流回應要**逐塊轉發**,不能整包緩衝(否則 SSE 變成一次吐完)

## 檢查清單

```bash
# 1. 模型有註冊嗎
curl -s $BASE/v1/models -H "Authorization: Bearer $KEY" | python -c "import json,sys;[print(m['id']) for m in json.load(sys.stdin)['data']]"

# 2. 非串流通嗎
curl -s -o /dev/null -w "%{http_code}\n" -X POST $BASE/v1/messages -H "Authorization: Bearer $KEY" \
  -H "Content-Type: application/json" \
  -d '{"model":"'"$MODEL"'","max_tokens":16,"messages":[{"role":"user","content":"say OK"}]}'

# 3. 串流通嗎(最常壞的一步)
curl -s -o /dev/null -w "%{http_code}\n" -X POST $BASE/v1/messages -H "Authorization: Bearer $KEY" \
  -H "Content-Type: application/json" \
  -d '{"model":"'"$MODEL"'","max_tokens":16,"stream":true,"messages":[{"role":"user","content":"say OK"}]}'

# 4. 對話中 system 訊息(Claude Code 真的會送)
#    在 messages 裡加 {"role":"system","content":[{"type":"text","text":"..."}]} 再測一次串流

# 5. 端到端
claude -p "reply with exactly: OK" --output-format json
```

**第 5 步不能省。** 前四步全過但 Claude Code 仍失敗是常態 —— 它送的 body 比手工測試複雜得多
(工具定義、`thinking`、`output_config`、`context_management`)。

## 觀察快取

Claude Code 會顯示回應裡的 `cache_read_input_tokens`(`/usage`、statusline)。
代理如果沒把上游的快取數字映射回這個欄位,使用者就看不到省了多少。要查自己的快取到底有沒有命中,就從上游回應的 usage 欄位逐欄對,不要相信中間層轉述的數字。

## 安全界

- 不修改使用者既有的 `~/.claude` / `~/.codex`,一律用獨立目錄 + 啟動器。
- API key 不寫進 shell rc、不印到 stdout(會留在終端捲軸與 agent 的 transcript);
  寫檔案並設 0600。
- 錯誤 log 常含完整 prompt —— 分享前先脫敏。
