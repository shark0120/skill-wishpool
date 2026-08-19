---
name: autopilot
description: >-
  一鍵自主把專案推到底。被叫起來就:自動偵測本專案 → 從協作看板認領範圍不撞的任務 →
  實作 → 自檢(gate + 實機實測)→ 對抗式驗證 → 提交 → 收尾把下一批任務排好 → 自動接續下一輪,
  全程不需使用者逐步下指令。掛著跑、多帳號/多子代理並行安全、200K context 自帶壓縮、跨專案自適應。
  當使用者打「/start」「/autopilot」,或說出明確的自主連跑語句如「自己跑到底」「自主迭代」
  「燒好燒滿」「我去睡了你繼續」「不用問我,直接做完」「take it from here」時使用。
  單獨出現的日常接續語(「開始」「繼續做」「接著做」「你決定」「keep going」「ship it」)不觸發本 skill。
---

# autopilot — 自主推進引擎(最快完成專案;不省 token)

> **一句話鐵律**:**先偵測 → 再認領 → 只改鎖住的 → 親眼驗過才算完成;不確定「該不該」就預設不做,不確定「怎麼做」就先查再決定;都推不動才在交接列清單,平時不逐步問使用者。**
>
> 這支 skill 是**通用**的:所有專案專屬值(指令、路徑、看板、產品名詞…)都在開跑時**偵測**出來,流程本身不寫死任何一個專案。丟到別的 repo 也能跑。

被上述**明確語句/指令**觸發後**立刻進 §1→§2,不要先反問「你要我做什麼」**。自主連續執行多輪與本機提交的範圍,仍受 §2 鐵律與授權紅線約束——觸發語不放寬任何紅線。把時間花在做事。

---

## 詳細模組(按需載入,別一開場全讀進 context)

這份 SKILL.md 是**脊椎**。遇到對應階段才去讀該模組——這樣連 200K 的模型載入也不爆:

| 模組 | 何時讀 | 檔 |
|---|---|---|
| **自適應偵測 + bootstrap** | §1 開跑解析 CTX 時;或這個 repo 沒有看板要自建時 | `reference/adapt.md` |
| **200K context 壓縮協議** | 要連續跑多輪 / context 往上爬 / 吞了大檔時 | `reference/compression.md` |
| **平行艦隊 + 排隊 + 分工不撞** | 要同時開多個子代理 / 多帳號並行時 | `reference/orchestration.md` |
| **MAX 融合跑到底迴圈(對抗式驗證 + 完整性批判 + 自動接續)** | 使用者要「燒好燒滿 / 跑到底 / 過夜跑」時 | `reference/max-loop.md` |

---

## 1. 開跑第 0 件事:自適應解析 CTX(先做完再動手)

**目的**:同一支 skill 換 repo 也能跑 = 流程恆定、專案專屬值全部開跑時解析。解析出「執行上下文 CTX」,之後所有步驟只引用 CTX 變數,**絕不把任何專案專屬字串寫死進流程或宣稱**。

```bash
node <此 skill>/templates/resolve-context.mjs   # 印出 CTX(偵測不到的標 UNKNOWN,絕不編造)
# 已安裝到 repo 的話:node scripts/autopilot/resolve-context.mjs
```

解析這些變數(優先序:專案根 `.autopilot.json` → 自動偵測 → 保守安全預設並標 `UNKNOWN`):

| 變數 | 用途 | 偵測(由上到下) | 缺省 |
|---|---|---|---|
| `$CLAIM` | 認領/自檢 CLI | `.autopilot.json.claimCli`;否則 `coordination/claim.mjs` | UNKNOWN→§1.2 降級 |
| `$BOARD` | 機器任務來源 | `coordination/tasks.json`(schema 前綴 `*-coord-tasks/`) | UNKNOWN→§1.2 |
| `$SHARED_FILES` | 高衝突共享檔 | `$BOARD.sharedFiles[]` | `[]` |
| `$GATE_ALIASES` | gate 短名→指令 | `$BOARD.gateAliases` | `{}` |
| `$GATE_HINTS` | 候選驗證 | 掃 `package.json` scripts 取 `verify*/build*/typecheck*/test*/smoke*/lint*` | 靠任務自帶 gate[] |
| `$PLAN_DOC` | 路線圖(補任務) | `docs/plan/00*` / `ROADMAP*` / `PLAN*` | UNKNOWN |
| `$STATE_DOC` | 唯一動態快照 | `CURRENT_STATE.md` / `STATE.md` | UNKNOWN |
| `$HANDOFF_DOC` | 交接 append | `CODEX_HANDOFF.md` / `HANDOFF*` / `ITERATION_LOG*` | 回覆末尾寫交接 |
| `$COMMIT_TRAILER` | commit 署名 | 近 5 個 commit 的既有 `Co-Authored-By` | 無 |
| `$AGENT` | 本 session 認領代號 | **每次開跑自己生成唯一 `<model>-<4碼>`** | 必生成 |
| `$VIEWPORT` | 前端實測尺寸 | 行動優先預設 `375x812` | `375x812` |

> **反硬編鐵律**:產品名、女主名、章節數、主機名、指令名、路徑… 一律不准憑印象填;要用就從 CTX / 內容檔 / config 取,取不到用中性佔位。詳見 `reference/adapt.md`。

**§1.2 無看板降級**:`$CLAIM`/`$BOARD` = UNKNOWN(這 repo 不是看板型)→ **不要假裝有**。若觸發句已給目標就做那個;否則跟使用者要一個明確目標。之後照 §2 的自問檢查點跑單一目標(對齊風格→實作→build/test 綠→明確路徑 commit→交接)。缺 coordination 又想長期自駕 → 讀 `reference/adapt.md` 的 bootstrap 自建一份。

---

## 2. 主迴圈:一台狀態機,一步一自問(笨模型防跑偏)

**LOCATE → PICK → CLAIM → IMPLEMENT → CHECK → COMMIT → CLOSE → LOOP**。每步後面的「自問」任一答**否**,就走該步指定動作,**不准帶著疑問往下衝**。

### 鐵律(每輪成立;越界即停)
1. **先認領、再動手**;只在 `$CLAIM claim` 鎖住的 `owns[]` 內寫檔。
2. **`git add` 一律明確路徑,絕不 `-A`/`.`**(防連帶提交/截斷)。
3. **只做 `ownerType: ai` 的任務**;`decision`/`authorize` **跳過:不問、不自己做**,換下一個。
4. **授權紅線(永不自行做、也永不排程去做)**:push / merge / PR / 動 `main` / 部署 / 任何**外部花費**(付費出圖、真實模型 API)/ 公開上線 / 刪資料 / 改權限 / 寫 `.env` 祕密值。→ 累積成清單留給使用者。
5. **提交到目前分支 = 已授權**(自適應:有遠端的共享 `main` → 先切工作分支再提交;solo/無遠端專案 `main` 就是工作線 → 可直接本機提交)。**push / PR / 任何對外一律不行,留給使用者。** `resolve-context.mjs --check` 會判定 GO/NO-GO。
6. **每個任務都要「自檢綠 + 提交」才算完成**;紅燈修到綠或 `release` 交還,**不留半成品占鎖**。
7. **沒讀過的不引用,沒跑過的不宣稱,沒對照過的不算完成**(反幻覺)。
8. **收尾一定補齊佇列**(CLOSE),否則下次開跑沒事做。

### LOCATE
```bash
node <此 skill>/templates/resolve-context.mjs --check   # 分支自適應判定 GO/NO-GO
git status --short && git branch --show-current        # 現況
$CLAIM status                                          # 誰在做什麼、鎖了哪些檔
$CLAIM list --available                                # 現在能領的(ai + deps 完成 + 不撞)
```
自問:① `--check` 是 GO 嗎?(NO-GO=在共享 main → 先 `git switch -c work` 切工作分支;solo/無遠端 main 會判 GO)② CTX 解析齊了?③ 板讀到了?—— 否則先補。

### PICK
```bash
$CLAIM next --agent $AGENT
```
自問:① `ownerType=ai`?② `deps` 都 done?③ `owns[]` 沒被鎖?—— 任一否 → **跳過換下一個**。`list --available` 全空 → 跳 CLOSE 補任務。

### CLAIM
```bash
$CLAIM claim <id> --agent $AGENT --note "怎麼切這一刀"
```
退出碼:`0` 成功 · `2` 範圍撞(回 PICK 換不撞的)· `3` 鎖忙(稍後重試同一個)。

### IMPLEMENT(只在鎖住範圍內;反幻覺 + 反離題)
- 讀任務 `goal`/`accept` + 人類規格(WP 檔若有);**每個要用的檔/函式/型別/欄位/script,先 Grep/Read 看到本人再用**。禁「我記得有」。
- 改動點附近先讀 20–50 行,照既有風格;一次一個可驗證單元。
- 自問:① 引用的每樣都親眼看過?② **只**改了 `owns[]`(+已登記 `sharedTouch[]`)?③ 有沒有「順手」改無關的(重構/格式/加小功能)?—— ③ 有 → **立刻 revert 多餘改動**。

### CHECK(自檢,親眼看輸出)
```bash
$CLAIM check <id>     # 自動跑 gate[](唯讀)+ 列 accept[] 給你逐條核
```
- 前端另加**實機實測**(直接用瀏覽器工具開 `$VIEWPORT`;專案若自帶 verify 類 skill 則優先用它):到該畫面、console **零錯誤**、既有/landing **零回歸**、互動**實際生效**(DOM 佐證;截圖逾時用 DOM)。
- 自問:① gate 綠是我**剛跑親眼看到**的(不是「應該會過」)?② accept 每條核了?③ 前端做了實測且零回歸?—— 否則修;修不動走 §3 停損。
- **要「燒好燒滿/跑到底」時**:gate 綠**不等於對** → 依全域 **max** skill 的對抗式驗證做法,開 N 個 fresh-context 懷疑者(重現/反例/回歸/範圍/宣稱各一視角)把改動打爆,全過才算;接續/停止的膠水規則見 `reference/max-loop.md`。

### COMMIT(明確路徑)
```bash
git add <明確路徑...>            # 絕不 -A / .
git diff --cached --name-only    # 確認 index ⊆ 我的 owns[]
git commit -m "<訊息>"           # 結尾接 $COMMIT_TRAILER(若有)
```
自問:cached 清單有沒有混進 `.env*` / 建置產物 / 別人的檔?—— 有 → `git reset` → 只 add 自己的。

### CLOSE(收工 + **強制**補佇列 = 自迭代命脈)
```bash
$CLAIM done <id> --agent $AGENT --note "證據:gate 12/12、瀏覽器 console 乾淨"
$CLAIM health --min 3            # 可立即認領的 ai 任務數
```
- `health` 紅(<門檻)→ **必須補新任務再結束**:從 `$PLAN_DOC` 挑下一個未拆大項,拆 **2–4 個原子任務** append 進 `$BOARD.tasks[]`,每筆必含 `id`(唯一 kebab)/`phase`/`title`/`ownerType:"ai"`/`priority`/`blocking`/`effort`/`deps[]`/`owns[]`(獨佔鎖範圍,寬到涵蓋你要改的、窄到不擋別人;動 `$SHARED_FILES` 另列 `sharedTouch[]`)/`goal`/`gate[]`(**能自動跑的**指令,可用 `$GATE_ALIASES` 短名)/`accept[]`/`status:"available"`/`claim:null` → `$CLAIM selftest`(id 唯一/deps 可解/無 active 撞)→ 再 `health` 轉綠。
- **絕不讓佇列空著就結束。**

### LOOP
回 LOCATE 做下一輪。**盡量一次開跑多輪**(各自提交),進度就算 context 用完也已落地。
**要跑到底**:每輪做完**不停下來問**,依 `reference/max-loop.md` 自動接續(同輪續跑 → context 快滿則續派子代理;**排程喚醒過夜跑需使用者事先明確同意**),直到**連續 2 輪確實無新可做**才停。

---

## 3. 停止條件 + 失敗恢復(只有這些才停)

| 情境 | 處置 |
|---|---|
| **佇列空 + 補不出**(剩全 decision/authorize) | 寫交接列「卡在使用者」清單,**停**。 |
| **跑到底模式收斂**(連續 2 輪 dry) | 停(見 `reference/max-loop.md`)。token 沒燒完**不是**繼續亂改的理由。 |
| **gate 卡紅** | 讀輸出→修一次→重跑;**同一錯誤 2 次仍紅 → 停手**寫 `DEBUG_HANDOFF.md`(最小 repro + 假設 + 下一步驗什麼),`release` 換別的。有可驗證新假設前不再改 code。 |
| **認領撞(exit 2)** | 不硬改;回 PICK 換不撞的。要動別人正鎖的共享檔 → 不並行,排 `deps` 在其後。 |
| **鎖忙(exit 3)** | 0–60s 序列化,稍後重試同指令;逾 60s 自動視孤兒鎖可搶。 |
| **STALE 認領(>8h)** | 先確認該 session 真死了 → 才 `release` 幫放鎖。沒確認別搶。 |
| **context 快滿** | 先 CLOSE 補任務 + 寫交接,再停/續派。**絕不在佇列空/半成品占鎖/沒交接下停。**細節 `reference/compression.md`。 |
| **git status 秒秒變/被連帶提交** | 停手別 `-A`;必要時 `git stash -u` 隔離,或 `git worktree add` 開隔離樹把自己的改動搬過去;`git diff --cached --name-only` 逐檔核對後只 add 自己的。 |

**不確定時**(不要亂問也不要亂做):不確定「該不該」→ **預設不做**、跳過;不確定「怎麼做」→ **先查證**(Grep/Read/最小實測),查不到就 `block`/`release` 交接卡點;不確定「對不對」(無法驗證的宣稱)→ **視為未通過**,不得 `done`。**只有整個佇列都推不動、剩全 decision/authorize 時,才在交接一次列清單**——平時不問。

---

## 4. 遇到什麼用什麼(skill 組合)

| 主迴圈步驟 / 情境 | 用哪個 | 怎麼串 |
|---|---|---|
| IMPLEMENT 寫 production code | §2 IMPLEMENT 內嵌反幻覺紀律(專案若有 grounded-coding 類 skill 則優先載入) | 引用先 Read → 一次一單元 → 立即驗 → 宣稱 vs 實跑交叉比對 |
| CHECK 前端 | 瀏覽器工具實測(專案若有 verify 類 skill 則優先用) | 開 `$VIEWPORT` 實測:到畫面、console 零錯、零回歸、DOM 佐證 |
| CHECK 後端 | HTTP 實測(curl / 內建 fetch 探針) | 起服務→探端點→紅燈基線 vs 綠燈對照 |
| 認領/自檢/補任務 | **`$CLAIM`** | status/next/claim/check/done/release/health/selftest;exit 2 換、3 重試 |
| 多帳號/多子代理並行 | `reference/orchestration.md` + `$AGENT` + `$CLAIM` 鎖 | 各不同代號;讀取型子代理平行、寫入序列化;整合者合併 |
| 要改高衝突大切片 / git 出事 | `git worktree` 隔離(§3 急救列) | 建樹隔離;status 秒變/連帶提交 → stash -u + 明確路徑 add |
| 跑到底 / 過夜 / 燒好燒滿 | 全域 **max** skill(對抗式驗證)+ `reference/max-loop.md`(接續膠水) | N 懷疑者對抗驗證 + 完整性批判 + loop-until-dry + 自動接續 |
| context 往上爬 | `reference/compression.md` | 外部化記憶、每步壓縮、`ctx.mjs boot` 幾百 token 接回、大檔外包子代理回結論 |
| 出圖/美術 ⚠ | 專案自帶的出圖管線(若有) | 真出圖=外部付費=authorize,**不自動花錢**;只做管線/接線 |
| 風險大切片收工前 | fresh-context 子代理審查 | 對抗式審自己 diff,確認才 `done` |

> 過度使用防呆:小改別套一堆模組/開一堆子代理;對抗式整批審查只在使用者要「徹底」或大重構時用。

---

## 5. 交接(每次停下來都寫「睡醒看這裡」)

回覆末尾(並可 append `$HANDOFF_DOC`,格式見 `reference/compression.md` 的 HANDOFF 五欄):
- **本輪做完**:任務 + commit sha + 一行自檢/懷疑者證據。
- **佇列現況**:`health` 可領幾個;若跑到底模式附 `round`/`dryRounds`。
- **補了什麼**:新增任務 id。
- **卡在使用者(只有這些需要你)**:待決策清單 + 待授權清單(主機/DB、外部帳號、付費出圖、真實模型花費、法遵、封測、公開上線)。讓使用者一眼看到「其餘讓 autopilot 自己跑」。

---

## 6. 附帶腳本(templates/;可 bootstrap 進任何專案)

- `resolve-context.mjs` — 印 CTX(§1)。開跑第一件事。
- `ctx.mjs` — 200K 壓縮小工具:`boot`(印最小接手 context)/`handoff`(append 固定交接)/`newpage`/`budget`/`stamp`。
- `next-round.mjs` — 跑到底迴圈狀態:`record`(更新 dryRounds)/`decide`(印 CONTINUE/STOP)。
- `.autopilot.json`(範例)— 每專案覆寫 config;換 repo 只改這一檔。
- 缺協作層(claim CLI / tasks.json)時的 bootstrap 步驟見 `reference/adapt.md`。

安裝到專案:把 `templates/*` 複製進專案的 `scripts/autopilot/`(或 `coordination/`),`.autopilot.json` 放專案根。已內建 coordination 的專案(如已有 `coordination/claim.mjs`)直接沿用,不必重造。
