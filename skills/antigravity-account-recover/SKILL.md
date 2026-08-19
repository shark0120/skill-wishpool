---
name: antigravity-account-recover
description: 修復 Gemini Code Assist / antigravity 帳號的 403 VALIDATION_REQUIRED「Verify your account to continue」。當使用者說「帳號被擋」「Verify your account」「403 但重新登入沒用」「Gemini 帳號要驗證」「antigravity 403」「重新授權還是不行」「綁手機也沒用」時使用。也用於判斷代理回的 503 auth_unavailable 是引擎狀態還是上游真的拒絕。
---

# antigravity-account-recover

## 這個錯誤的陷阱

```
403 permission_error: "Verify your account to continue."
```

**重新 OAuth 授權不會修好它。** 實測過:重新授權成功、新 token 寫入、
`loadCodeAssist` 回 200、帳號供應狀態與健康帳號**完全相同**(同 tier、有 Cloud 專案)——
但 `generateContent` 照樣 403。

**綁定手機號碼也沒用。** Google 要的是 **Gemini Code Assist 專屬**的驗證流程,
不是一般 Google 帳號安全設定。

## 關鍵:Google 會給你一次性驗證連結,但代理會把它吃掉

代理層通常只轉發 `message` 欄位,把 `details[]` 丟掉 —— 而**解法就在 `details[]` 裡**。
必須繞過代理直接問 Google。

## 步驟

### 1. 直接打上游取完整錯誤

```python
import json, urllib.request, urllib.error
tok = json.load(open(r"...\auth\antigravity-<EMAIL>.json"))["access_token"]
body = {"model": "gemini-pro-agent", "project": "<cloudaicompanionProject>",
        "request": {"contents": [{"role": "user", "parts": [{"text": "hi"}]}]}}
q = urllib.request.Request(
    "https://cloudcode-pa.googleapis.com/v1internal:generateContent",
    data=json.dumps(body).encode(),
    headers={"Authorization": "Bearer " + tok, "Content-Type": "application/json"})
try:
    print(urllib.request.urlopen(q, timeout=60).read()[:200])
except urllib.error.HTTPError as e:
    print(e.code, e.read().decode())   # ← 完整 details[] 在這
```

`<cloudaicompanionProject>` 從這裡拿(這支通常會回 200,即使帳號被擋):
```
POST https://cloudcode-pa.googleapis.com/v1internal:loadCodeAssist
body: {"metadata": {"pluginType": "GEMINI"}}
```

### 2. 取出驗證連結

回應長這樣:
```json
{"error": {"code": 403, "status": "PERMISSION_DENIED",
  "details": [{"@type": "...ErrorInfo", "reason": "VALIDATION_REQUIRED",
    "metadata": {"validation_url": "https://accounts.google.com/signin/continue?...&plt=<TOKEN>..."}}]}}
```

`details[].metadata.validation_url` 就是解法。

### 3. 用「那個帳號」開啟連結走完流程

- **必須是出問題的那個 Google 帳號**。瀏覽器已登入別的帳號就用無痕視窗。
- 連結含一次性 `plt=` token,**會過期**;過期就重跑第 1 步再取一次。
- 成功會導到 `developers.google.com/.../auth_success_gemini`。

### 4. 驗證是否真的活了(不要只看檔案有沒有更新)

代理層有記憶體內的失敗狀態,會讓你看到假訊號:

1. **先重啟引擎**清掉 error 狀態
2. 確認乾淨基準:所有帳號 `failed: 0` / `status: active`
3. 把其他帳號暫時 `disabled: true`,**只留待測帳號**
4. 打一發真請求

**判讀**:
- `200` → 真的好了
- `403 Verify your account` → 還沒過驗證,回第 1 步
- `503 auth_unavailable` → **這是引擎拒絕路由,不是上游拒絕**;沒清乾淨,重來

第二發之後幾乎都會變成 503(第一發失敗就把帳號標成 error 了),**只有第一發算數**。

## 判斷是不是白費力氣

`loadCodeAssist` 回 200 且 tier / project 與健康帳號一致 → 帳號本身是好的,純粹卡驗證,值得救。
`loadCodeAssist` 就回 4xx → 問題更深(未開通 / 已停權),先解決那個。

## 救不回來時

在憑證檔設 `"disabled": true`(**可逆**,不要刪檔),讓引擎不再浪費請求去撞它,
並把容量規劃改成實際可用帳號數。

## 安全界

- **絕不印出、複製、記錄 access_token 或 refresh_token。** 只讀來用,不外流。
- 驗證連結含一次性 token —— 可以給帳號擁有者,**不要貼進公開場合或 commit**。
- 改憑證檔前先備份到 `backups/`。
- 不代替使用者完成 Google 驗證流程(那需要他們本人的身分確認)。
