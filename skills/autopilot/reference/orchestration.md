MODULE: parallel-fleet — 多代理平行艦隊(排隊 · 分工 · 不撞 · 序列化整合)

# 模組:多代理平行艦隊(Parallel Agent Fleet)

> 一句話:**同時派 N 個子代理,每個只鎖一塊「彼此不重疊」的檔案範圍,撞到自動拒絕;整合者一次合一個。**
> 這是「多 Claude / 多 session / workflow 同時推進同一個 repo 而不互相截斷」的機械閘,不是禮貌約定。
> 本專案已有實作:`coordination/claim.mjs`(檔案鎖層)+ `AGENTS.md` §2(worktree 層)。本模組教你怎麼**同時開跑一群**、怎麼**排隊**、怎麼**分工到不撞**、怎麼**收斂合併**。

---

## 0. 先做這一步:選層(decision tree,不要猜)

多代理防撞有**兩層**,先選對層再往下做:

```
要同時動手的代理數 N ≥ 2?
├─ 否 → 不需要本模組,直接 claim 一個任務做(見 §2)。
└─ 是 → 這批任務會不會動到「高衝突共享檔」或是「大切片」?
        (高衝突檔 = tasks.json 的 sharedFiles[],依該專案偵測值為準,常見如:入口元件 / 全域樣式 / schema / package.json …)
        ├─ 會,或每個切片很大/會跑很久 → 用【worktree 層】:每個代理一棵隔離工作樹,整合者序列化合併(§3-B)。
        └─ 不會,都是範圍清楚的小切片、在同一個 checkout 內 → 用【檔案鎖層】:claim.mjs 鎖 owns[](§3-A)。
```

**兩層可以同時存在**,鐵律永遠相同:**主工作目錄裡同一個檔、同一時刻,只准一條線寫。**
- 檔案鎖層用 `owns[]` 重疊偵測達成(claim 撞到 → exit 2 拒絕)。
- worktree 層用「隔離複本 + 整合者是唯一寫 main 的人」達成。

| 情境 | 用哪層 | 認領動作 = 鎖 |
|------|--------|----------------|
| 單一 checkout、小切片、不動高衝突檔 | 檔案鎖層(`claim.mjs`) | `claim <id>` 鎖住 `owns[]`;重疊即拒 |
| harness 能開 worktree、大規模並行、或改高衝突檔的大切片 | worktree 層(`AGENTS.md`) | `git worktree add`(建樹即鎖,先到先得) |

---

## 1. 佇列與認領:認領 = 鎖住不重疊的檔案範圍

核心工具:`node coordination/claim.mjs`。核心資料:`coordination/tasks.json`(機器登記表,schema `heartbeat-coord-tasks/v1`)。

**每筆任務的關鍵欄位(認領前一定要看懂):**

| 欄位 | 意義 | 對「不撞」的作用 |
|------|------|------------------|
| `owns[]` | 這任務**獨佔寫入**的路徑 | 認領=鎖住它;**只在這裡面寫檔** |
| `sharedTouch[]` | 會動到的高衝突共享檔 | 也被獨佔鎖住 → 同一共享檔不會兩人同時改 |
| `deps[]` | 前置任務 | 全部 `done` 前這任務不 `available`(排隊相依) |
| `gate[]` | 機器自檢指令 | `check`/`done` 逐條跑,全綠才准收工 |
| `accept[]` | 人工核對驗收(Gate 抓不到的) | 例:瀏覽器 console 零錯誤、landing 零回歸 |
| `ownerType` | `ai` / `decision` / `authorize` | 只有 `ai` 可被代理認領執行;其餘卡在使用者 |
| `blocking` | 是否擋公開上線 | 排序時擋上線者優先 |
| `priority` | `high`/`med`/`low` | 次要排序鍵 |

**重疊怎麼判定(claim.mjs 的機械閘,你不用背,但要知道原理):**
`lockPaths(t) = owns[] ∪ sharedTouch[]`。兩個 active 任務的 lockPaths 只要有一對路徑「相等,或一方是另一方的祖先目錄」就算撞。撞了 → `claim` 直接 `exit 2` 拒絕(先到先得,防並寫截斷)。

### 指令速查(所有指令在 repo 根目錄跑;`<name>` 換成你的代號如 `sonnet-a`)

```bash
# 看板:誰在做什麼、哪些現在能領
node coordination/claim.mjs status              # 進行中認領 + 每個鎖住的檔 + 統計 + ⚠STALE 標記
node coordination/claim.mjs list --available    # 現在就能領(ai + 相依已完成 + 範圍不撞)
node coordination/claim.mjs next --agent <name> # 推薦下一個(排序:擋上線 > 優先級)

# 認領(鎖範圍;與他人重疊 → exit 2)
node coordination/claim.mjs claim <id> --agent <name> --note "我要這樣切"

# 執行中隨時自檢(唯讀,不改狀態)
node coordination/claim.mjs check <id>          # 跑該任務 gate[]

# 收工:done 先跑 gate[],全綠才標 done + 放鎖 + 印出被解鎖的下游任務
node coordination/claim.mjs done <id> --agent <name> --note "證據:xxx 12/12、瀏覽器 console 乾淨"

# 中途放棄/交還 or 轉審查(鎖仍持有)
node coordination/claim.mjs release <id> --agent <name>   # 放鎖,回 available
node coordination/claim.mjs review  <id> --agent <name>   # 標 in-review(待整合者複審)
```

**退出碼(照它反應,別硬幹):** `0` 成功 · `1` 失敗/Gate 紅 · `2` 認領衝突(範圍重疊→換一個)· `3` 鎖忙(0–60s→稍後重試)。

### 排隊機制(四個閘,面試會考)

1. **相依閘(`deps[]`)**:任務只有在**所有前置 `done`** 後才 `available`。`done` 完成時會印出「解鎖了:X, Y」。→ 相依鏈自動排隊,別手動跳過。
2. **優先序排序(`next` / 規劃器用)**:`(blocking 降序) → (priority: high>med>low)`。擋上線的先做,同級再比優先級。
3. **佇列健康閘(`health`)**:
   ```bash
   node coordination/claim.mjs health --min 3   # 可立即認領的 ai 任務 < 3 → exit 1
   ```
   `< 門檻` 代表佇列快乾了。**收尾時(/start 尾聲)必須把佇列補到門檻以上**才准停——否則下一批代理沒任務可領。
4. **STALE 認領回收(`STALE_CLAIM_HOURS = 8`)**:`status` 會把超過 8h 沒更新的認領標 `⚠STALE`。確認該 session 真的死了(對方沒在寫),才可 `release <id>` 幫它放鎖,讓任務回 `available` 重新入佇列。

---

## 2. 分工明確:每個子代理的 prompt 必含這 7 塊(缺一就會撞/離題)

派一個子代理出去,它拿到的 prompt **一定要自帶下列 7 塊**。少任何一塊,它就會越界寫沒鎖的檔(截斷)或做交付物以外的事(離題)。用 §7 的範本填,不要即興。

1. **你的任務 id + 你的鎖範圍(`owns[]`)**:逐條列出。「你只准寫這些路徑。」
2. **共享檔警告(`sharedTouch[]`)**:「這些已為你獨佔鎖住,但仍要小心只改你負責的區段。」
3. **禁碰清單**:owns[] 以外的一切,**特別點名** `tasks.json.sharedFiles[]` 與「其他代理正鎖住的範圍」(附上當下 `status` 的鎖列表)。
4. **Gate(`gate[]`)**:逐條列;告訴它「`done` 會自動跑這些,全綠才准收工」。
5. **人工驗收(`accept[]`)**:Gate 抓不到的行為證據(前端→瀏覽器 375×812 實測 console 零錯誤、landing 零回歸;後端→端點紅燈基線 vs 綠燈)。
6. **commit 紀律**:`git add <明確路徑>` **絕不 `-A`/`.`**;結尾接 `$COMMIT_TRAILER`(從近 5 個 commit 偵測既有 Co-Authored-By;沒有就不加);不 amend 別人的 commit。
7. **退出碼協議 + 停損**:`claim` 回 2 → 換 `list --available` 裡不撞的;回 3 → 稍後重試;**同一錯誤修 2 次還在 → 停手,寫 `DEBUG_HANDOFF.md`,把任務 `block`**。

---

## 3. 平行派發 N 個子代理(整合者流程)

### 3-A. 檔案鎖層(同一 checkout,小切片,推薦預設)

整合者(主 session)照這個順序做:

```bash
# ① 規劃:挑出最多 N 個「彼此範圍也不撞」的可領任務,並印出每個代理的分工塊
node coordination/fleet.mjs --agents sonnet-a,sonnet-b,sonnet-c
#   （fleet.mjs 出貨於 <SKILL>/assets/coord/fleet.mjs,先複製進協作目錄再跑;
#     它做 claim.mjs 沒做的事:一次挑 N 個互不重疊的,不只 next 的一個）

# ② 一則訊息並發 spawn N 個子代理(Task / workflow)。每個代理的 prompt = §7 範本 + ① 印出的它那一塊。
#    重點:N 個 spawn 放在同一則訊息裡,才會真正並行。

# ③ 每個子代理自己做:claim → 只在 owns[] 改 → check → done(自動 gate)→ review
#    （子代理若被拒 exit 2,自己換 list --available 的下一個,不回頭問整合者)

# ④ 收斂:整合者「一次驗一個」把 in-review 的合入 main(序列化,見 §5),再跑佇列健康閘補料:
node coordination/claim.mjs status
node coordination/claim.mjs health --min 3   # <門檻就補新任務進 tasks.json 才收工
```

**為什麼要 fleet.mjs 而不是各代理各自 `next`?** 因為 `next` 只保證「不撞現有 active」,不保證「這 N 個彼此不撞」。若三個代理各自 `next` 可能拿到三個 owns[] 互撞的任務,結果兩個 `claim` 被拒、白 spawn。規劃器一次挑好互斥集,零浪費。

### 3-B. worktree 層(隔離複本,大切片/高衝突檔)

認領動作 = 建 worktree(建樹即鎖,先到先得):

```powershell
# 每個代理一棵樹(整合者先建、或代理自建都行;先到先得)
# <worktrees 根> = repo 上層的 <repo名>-worktrees\(或 .autopilot.json.worktreesDir)
git worktree add "<worktrees 根>\wp-<id>-<slug>" -b "wp/<id>-<slug>" main
cd "<worktrees 根>\wp-<id>-<slug>"
npm install     # 每棵樹獨立 install(Windows 原生綁定,勿共用 node_modules)
# 第一個 commit 必須把該 WP 檔狀態塊改 claimed + 認領者 + 日期
```

- 兩個代理撞同一包:worktree 先建立者贏;後者刪自己的樹換下一包。
- 代理只在自己樹裡工作,`gate` 綠 → WP 狀態塊改 `in-review` → **停止改動**。
- **合併只由整合者做**(squash → main、更新 WORK_BOARD 標 done、刪樹刪分支),序列化(§5)。

---

## 4. 衝突 / 競態處理(四道保險)

| 機制 | 在哪 | 防什麼 |
|------|------|--------|
| **諮詢式檔鎖 `.tasks.lock`** | `claim.mjs` `withLock()`;`wx` 建鎖、`process.on('exit')` 必放、超 `60s` 視孤兒可搶、忙碌 `exit 3` | 兩個 CLI 同時讀-算重疊-寫 tasks.json → 用同一份舊快照各自算「沒撞」而雙雙認領。鎖把讀-改-寫**序列化**。 |
| **原子寫 tmp+rename** | `claim.mjs` `save()`:寫 `tasks.json.tmp` 再 `rename`(同檔系統原子) | 寫到一半崩潰 → 半截 JSON 壞掉整個看板。 |
| **owns[] 重疊拒絕(exit 2)** | `claim` 時 `conflictsWith()` | 兩個 active 任務寫到重疊路徑 → 並寫截斷。 |
| **整合者序列化合併** | worktree 層鐵律:唯一寫 main 的人;一次合一個 | 兩條合併同時進 main → merge 打架 / 半合狀態。合併前先跑去重(§5)。 |

**序列化整合 SOP(整合者一次一個):**
```
for 每個 in-review 的分支/任務:
  1. 讀它的交付物 + gate 綠 + accept 勾;git diff --cached --name-only 確認只改了 owns[] 內的檔
  2. 跑去重判定(§5)——這個分支是否已被別的分支超集?是→retire 不合
  3. 合入 main(squash)→ 跑一次 post-merge gate(build/verify)確認沒回歸
  4. 更新看板標 done / claim.mjs done;放鎖;下一個
絕不同時合兩個。
```

---

## 5. 去重(`dupes.mjs`,出貨於 `<SKILL>/assets/coord/`):平行分支合併前一定要跑

平行艦隊最大的浪費是**兩個代理默默做了同一件事**。合併前,整合者對「同一條線/同一目標」的多個分支做分類,決定 retire(退掉零損失)還是 salvage(有獨特改動要挑走):

`dupes.mjs` 的分類法:

| 標籤 | 判準(git ancestry / tree diff) | 處置 |
|------|-------------------------------|------|
| `SUBSUMED_BY_LEADER` | 分支 tip 是 leader 的祖先 | **retire,零損失**(每個 commit leader 都有) |
| `SUBSET_OF_SIBLING` | 分支 tip 是另一條同線分支的祖先 | **retire**(完全被含) |
| `PARALLEL` | 獨立線,只共早期 base | **先看 `unique_files`**、挑走值得的 cherry-pick,再 retire |

預防勝於治療:**先用 §3 的規劃器分好互斥集**,平行分支就不會做重工;dupes 是合併前的最後一道去重保險。
另一個去重原則:同一目標有 >1 條分支在建 → 指定 leader,其餘 rebase 而非重建。

---

## 6. 笨模型照抄範本(整段可貼)

### 6-A. 整合者:開一批平行艦隊(貼上就跑)

```bash
# 1. 現況
node coordination/claim.mjs status
node coordination/claim.mjs list --available

# 2. 規劃 3 個互不重疊的任務 + 各自分工塊
node coordination/fleet.mjs --agents sonnet-a,sonnet-b,sonnet-c
# → 把輸出的每一塊,連同下面 6-B 範本,分別當成一個子代理的 prompt,
#   在「同一則訊息」裡並發 spawn 三個 Task 子代理。

# 3.（艦隊跑完後)序列化收斂
node coordination/claim.mjs status               # 看誰 in-review
node coordination/dupes.mjs                       # 去重:哪些分支可 retire(worktree 層才需要;先從 <SKILL>/assets/coord/ 複製進來)
#   逐一驗收 + 合併(一次一個)…
node coordination/claim.mjs health --min 3        # 補佇列到門檻才收工;<門檻請往 tasks.json 加任務
```

### 6-B. 子代理:分派 prompt 範本(填空,別即興)

```
你是平行艦隊的一員,代號 <AGENT_NAME>。整個 repo 有別的代理同時在跑,你必須嚴格待在自己鎖住的範圍內,否則會截斷別人的檔。

【你的任務】<TASK_ID> — <一句話目標>

【第一步:認領(鎖範圍)】
  node coordination/claim.mjs claim <TASK_ID> --agent <AGENT_NAME> --note "<你的切法>"
  - 若 exit 2(範圍撞):不要硬改。跑 `node coordination/claim.mjs list --available`,挑一個不撞的,重來。
  - 若 exit 3(鎖忙):等幾秒重試同一指令。

【你只准寫這些路徑(owns)】
  <逐條列 owns[]>
【這些是共享檔(已為你鎖住,只改你負責的區段)】
  <逐條列 sharedTouch[],沒有就寫「無」>
【禁碰(碰了=截斷別人)】
  - 上面兩區以外的一切檔案。
  - 特別是 tasks.json 的 sharedFiles[](逐條列出該專案 `$SHARED_FILES` 的實際值)。
  - 其他代理當下鎖住的範圍(開工前先 `node coordination/claim.mjs status` 看清楚)。

【做完前必過的 Gate(done 會自動跑,全綠才准收工)】
  <逐條列 gate[]>
【人工驗收(Gate 抓不到,你要自己確認並附證據)】
  <逐條列 accept[];前端一定含:瀏覽器 375×812 進到該畫面、console 零錯誤、landing/既有行為零回歸>

【commit 紀律】
  - git add <明確路徑>,絕不 -A 或 .（你不知道 index 裡混了誰的在途改動)。
  - 訊息結尾:接 $COMMIT_TRAILER(從近 5 個 commit 偵測;沒有就不加)
  - 不 amend 別人的 commit;高衝突檔的 snapshot 基準留給整合者重生。

【收工】
  node coordination/claim.mjs done <TASK_ID> --agent <AGENT_NAME> --note "證據:<測試行數 / gate 輸出 / 瀏覽器 DOM>"
  然後改狀態為 in-review 交整合者複審。git diff --cached --name-only 自查:只 commit 了 owns[] 內的檔。

【停損】同一錯誤修 2 次還在 → 停手,寫 DEBUG_HANDOFF.md,跑
  node coordination/claim.mjs block <TASK_ID> --reason "<卡在哪>"
  然後回報,不要繼續盲修。
```

---

## 7. 反模式(踩到就撤)

- ❌ **不 claim 就動手**:沒鎖到範圍就寫 = 賭博。永遠先 `claim` 成功再寫。
- ❌ **N 個代理各自 `next`**:會拿到互撞的任務,白 spawn。用規劃器一次挑互斥集。
- ❌ **`git add -A` / `.`**:把別人在途改動連帶 commit(多 session 共用 checkout 的頭號事故)。只加明確路徑。
- ❌ **兩個合併同時進 main**:序列化,一次一個,合前跑去重。
- ❌ **佇列乾了還收工**:`health` exit 1 就代表下一批沒任務可領;補到門檻才停。
- ❌ **代理認領 `decision`/`authorize` 任務**:那些卡在使用者,AI 不可執行。只碰 `ownerType: ai`。
- ❌ **`--force` 略過 Gate 標 done**:紅燈進 main = 把回歸塞給別人。除非整合者明確授權,不用 `--force`。

=== supportingFiles ===

--- coordination/fleet.mjs ---
平行派發規劃器(零依賴、唯讀,不改 tasks.json)。**完整可跑版出貨於 `<SKILL>/assets/coord/fleet.mjs`**(單一真相源,此處不內嵌副本)。一次挑出最多 N 個『彼此 owns[] 也互不重疊』的可領任務,依 擋上線>優先級 排序,並為每個代理印出可直接貼進 prompt 的分工塊(owns / sharedTouch / 禁碰 / gate / 目標)。整合者開艦隊的第一支指令:先複製進協作目錄,`node coordination/fleet.mjs --agents a,b,c`(或 `--n 3`)。

--- coordination/dupes.mjs ---
平行分支去重(可選,worktree 層才需要)。**完整可跑版出貨於 `<SKILL>/assets/coord/dupes.mjs`**(單一真相源,此處不內嵌副本)。合併前對同目標的多個 wp/* 分支用 git ancestry 分類 SUBSUMED_BY_LEADER / SUBSET_OF_SIBLING / PARALLEL,給整合者 retire-vs-salvage 判定。唯讀,不 checkout 不改分支:`node coordination/dupes.mjs [leaderBranch]`。

--- coordination/AGENT_PROMPT_TEMPLATE.md ---
子代理分派 prompt 的填空範本(即 SKILL.md §6-B 的獨立檔),讓整合者/workflow 每次派代理時複製一份填 owns/sharedTouch/gate/accept,保證每個代理都自帶鎖範圍+禁碰+驗收+退出碼協議+停損,不靠即興。
# 子代理分派範本(複製一份,填 <...> 後當一個 Task 的 prompt)
# 你是平行艦隊一員,代號 <AGENT_NAME>。全 repo 有別的代理同時在跑,嚴禁越出你鎖住的範圍。
# 任務: <TASK_ID> — <一句話目標>
# 認領: node coordination/claim.mjs claim <TASK_ID> --agent <AGENT_NAME>  (exit2 換不撞的;exit3 重試)
# 只准寫(owns): <...>
# 共享檔(已鎖,只改你區段): <...>
# 禁碰: owns 以外一切 + sharedFiles + 其他代理的鎖(先 status)
# Gate(done 自動跑,全綠才收工): <...>
# 人工驗收(附證據;前端含瀏覽器375×812 console 零錯誤+landing 零回歸): <...>
# commit: git add <明確路徑> 絕不 -A;結尾接 $COMMIT_TRAILER(偵測不到就不加)
# 收工: node coordination/claim.mjs done <TASK_ID> --agent <AGENT_NAME> --note "<證據>" → in-review
# 停損: 同錯修2次→ block <TASK_ID> --reason "..." + DEBUG_HANDOFF.md,不盲修


=== integrationNotes ===
本模組是整個「多 AI 協作 SKILL」的排程/防撞核心層,與其他模組銜接如下:

1. 與既有工具零改動嵌合:直接驅動 repo 內已存在的 `coordination/claim.mjs`(檔案鎖層)與 `AGENTS.md` §2 / `docs/plan/05`(worktree 層)。本模組只新增「一次挑 N 個互斥任務的規劃器 fleet.mjs」與「合併前去重 dupes.mjs」兩支薄工具,以及分派 prompt 範本;不改 claim.mjs 的鎖/退出碼語義。

2. 上游(任務從哪來):依賴一個「任務定義 / 看板」模組維護 `coordination/tasks.json`(owns/deps/gate/accept 必填)與 `WORK_PACKAGES/*.md`。本模組只消費 tasks.json,不定義任務內容。新增任務後務必 `node coordination/claim.mjs selftest`(id 唯一、deps 可解、現況無 active 撞範圍)。

3. 下游(每個子代理進場後):子代理拿到分派 prompt 後,寫 code 遵 SKILL.md §2 IMPLEMENT 的內嵌反幻覺紀律(專案若有 grounded-coding 類 skill 則優先載入);accept[] 的瀏覽器實測直接用瀏覽器工具(專案若有 verify 類 skill 則優先用);多 session 卡住/index 打架照 SKILL.md §3 急救列(stash -u / worktree 隔離)。

4. 收尾銜接:`health --min N` 佇列閘與 `/start` 收尾模組共用——/start 尾聲必須用它確認佇列補到門檻才停。整合者的序列化合併 SOP 與「12h 驗收 / ACCEPTANCE_12H.md」收斂模組銜接(以檔案+git 為準收斂看板)。

5. 判準出處(歷史備註):fleet.mjs / dupes.mjs 的三個判準(同目標多 builder→指定 leader、SUBSUMED/SUBSET/PARALLEL 去重、看板與 git 不一致時以檔案+git 為準)源自另一專案的 Python 艦隊參考實作;本 skill 只出貨 Node 版(assets/coord/),該 Python 版不隨 skill 出貨、也不需要。