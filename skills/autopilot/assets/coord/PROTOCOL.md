# 可攜協作協議(.coord/PROTOCOL.md)

## 為什麼有這層
多個 AI session / 帳號共用同一個 checkout 時,兩個同時寫同一檔會互相截斷。認領 = 鎖住不重疊的檔案範圍(owns[]),先到先得,即可在同一 checkout 內安全並行。

## 鐵律
1. 先 `claim` 成功、再動手;只在 owns[] 範圍內改檔。
2. `git add <明確路徑>`,絕不 `-A`/`.`(防連帶提交/截斷)。
3. 每個任務要 `done`(自動跑 gate,全綠才收 + 放鎖);不留半成品占鎖,做不完就 `release`。
4. 只做 ownerType=ai。decision(需人拍板)、authorize(需人授權/花費/親自)一律跳過丟回使用者。
5. 授權紅線永不自動:push/動 main/PR/部署/外部花費/刪資料/改權限/寫 .env 祕密值。

## 指令速查
- 現況:`node .coord/claim.mjs status`
- 找下一個:`node .coord/claim.mjs next --agent <代號>`
- 認領:`claim <id> --agent <代號>`  |  自檢:`check <id>`  |  收:`done <id> --agent <代號>`
- 佇列健康(收尾用):`health --min 3`(可認領 ai 任務低於門檻 → 該補任務)

## 停止條件
- 佇列空且補不出新 ai 任務(剩 decision/authorize)→ 寫卡點清單交回使用者。
- 同一任務連兩輪 gate 卡紅無法自解 → release + 交接,換別的。
