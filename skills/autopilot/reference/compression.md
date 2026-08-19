MODULE: 200K Context 自帶壓縮協議（外部化工作記憶 + 壓縮節奏 + 結構化交接 + 子代理外包 + 觸發線）

## 模組 — 200K Context 自帶壓縮協議

> **一句話鐵律**:**Context 是會被清空的草稿,磁碟才是你的記憶。腦子裡只留「當前這一小步 + 幾個指標 + 檔案指標」,其他全部寫進檔、丟掉原文。**
>
> 這個模組讓 context 只有 200K 的較笨模型能**掛著長時間自駕不爆掉**:每做完一小步就把細節沉澱進磁碟、把原始長輸出丟棄,任何一輪被清空後都能靠幾百 token 接回來。

### 何時啟用(符合任一就開)

- 你要連續跑**多個任務 / 多輪迭代**(例:被 `/start` 掛著跑、無人值守)。
- 你發現自己**快忘記前面做過什麼**、或想重讀剛剛讀過的大檔。
- 單次工具輸出很長(整個檔、整段搜尋結果、整份 log)。
- 你估計 context 用量正在往上爬(harness 有顯示 % 就看 %;沒有就看下面的**代理計數器**)。

**可略**:單一、一次就做完、不需要跨輪記憶的小改動。

---

### 心法:三條鐵律(每一步都成立)

1. **能寫進檔的,就不要留在腦子裡。** 結論、指標、下一步 → 寫檔;原始長輸出 → 讀完抽完重點**立刻丟**,不要留在推理裡反覆咀嚼。
2. **隨時可被殺。** 每做完一小步就讓磁碟處於「別人能接手」的狀態(STATE 更新 + 一塊交接)。假設你下一秒 context 就被清空。
3. **摘要往檔裡寫,不要往 context 裡寫。** 你「總結一下剛剛」的動作,產物要落到 `journal` / 任務頁,而不是變成 context 裡又一段長文字。

---

### 磁碟記憶佈局(可攜版:任何專案照抄)

三個檔各司其職,**動態真相只在一處**:

| 檔 | 性質 | 寫法 | 裡面放什麼 |
|---|---|---|---|
| `.coord/STATE.md` | **唯一動態快照** | **覆寫**(過期即刪,不堆疊) | 當前任務、當前這一小步、關鍵指標、指到細節的指標 |
| `.coord/journal.md` | 交接流水帳 | **append**(只往後加) | 每完成一小步一塊固定格式交接;接手時**只讀最後 1 塊** |
| `.coord/tasks/<id>.md` | 每任務一頁 | append 該任務的重點 | 這個任務的目標 / 範圍 / 驗收 / 壓縮後的重點 log |

> **對應專案既有體系(不要另起爐灶)**:若目標專案已有等價檔,直接沿用、不建 `.coord/*` 重複:`.coord/STATE.md` ↔ `$STATE_DOC`(如 `CURRENT_STATE.md`,唯一動態快照,覆寫);`.coord/journal.md` ↔ `$HANDOFF_DOC`(如 `CODEX_HANDOFF.md` / `ITERATION_LOG*`,append 交接);`.coord/tasks/<id>.md` ↔ 專案的任務頁(如 `WORK_PACKAGES/*.md`)。認領/鎖檔仍走 `$CLAIM`。**本模組只加「壓縮節奏 + context 預算」這層紀律,檔案沿用現有的。**

---

### Context 預算:什麼**留**、什麼**丟**

**永遠留在 context(加起來應該很小,幾千 token 內):**
- 當前任務一句目標 + 當前這一小步。
- 3–6 個關鍵指標(build PASS、tests 12/12、blockers 0…)。
- 檔案**指標**(路徑),不是檔案內容。

**讀完就丟(抽出結論寫檔,原文不留):**
- 任何整檔內容、整段搜尋結果、整份指令輸出 / log。
- 已完成任務的細節(它的結論已在 journal + 任務頁)。
- 探索過程的死路 / 試錯(只把「結論:X 此路不通,因為 Y」寫一行到任務頁)。

**判斷法**:問自己「這段文字,下一輪的我需要**逐字**看到嗎?」——
- 需要逐字 → 它是產出,寫進**檔**(source code / 任務頁),不是靠記憶。
- 不需要逐字,只需要結論 → 抽一句結論,丟原文。

---

### 壓縮節奏(每一步做完都跑這個檢查)

做完**任何一小步**後,照順序問:

```
[ ] 這步有沒有產生「下一輪需要知道的結論或指標」?
      有 → 更新 .coord/STATE.md 的 NOW/METRICS(覆寫)
[ ] 這步有沒有吐出很長的原始輸出(整檔 / 大搜尋 / 長 log)?
      有 → 抽 1–3 行重點寫進 .coord/tasks/<id>.md 的 LOG,然後把原文丟出腦子
[ ] 這一小步是不是一個「可交接的節點」(做完一個可驗收的東西)?
      是 → 往 .coord/journal.md append 一塊【交接格式】(見下),幾百 token
[ ] 我是不是想重讀一個剛剛讀過的大檔?
      是 → 停。代表上一輪沒把它壓好 → 現在補寫任務頁,之後讀你自己的摘要,不要重讀原檔
```

**節拍(硬性):**
- **每完成 1 個任務** → 必寫一塊 journal 交接 + STATE 覆寫。
- **每 ~6 個工具步** → 做一次壓縮 checkpoint(把手上累積的長輸出沉澱掉)。
- **任何單次輸出你需要「往下捲」才看得完** → 當場視為「原始資料」:抽重點寫檔、丟原文。

---

### 觸發線:何時**主動壓縮** vs 何時**開新輪**

分兩種情況,笨模型二選一:

**A. Harness 有顯示 context 用量 %(或有 auto-compact 警告)** → 用硬數字:

| 用量 | 動作 |
|---|---|
| 到 **~60%** | **立刻壓縮**:把手上所有長輸出沉澱進檔、丟原文;STATE 覆寫成最新;**不要**開新任務前不壓 |
| 到 **~75%** | **收束開新輪**:做完當前這一微步 → 寫完整 journal 交接 → **停,開新輪**(乾淨 context,用下面的 Boot SOP 接回) |
| **不要**撐到 90%+ | 撐到自動壓縮 = 你會失去對「留什麼、丟什麼」的控制,品質崩 |

**B. 看不到 %(多數笨模型看不到)** → 用**代理計數器**,任一成立就當作到線:

| 代理訊號(≈60%,該壓縮) | 代理訊號(≈75%,該開新輪) |
|---|---|
| 距上次壓縮已做 ~6+ 步 | 這一連續輪已完成 **2 個以上**任務 |
| 手上同時「掛著」1 個以上大段原始輸出 | 你**重讀**了一個本輪讀過的檔(記憶已開始漏) |
| 剛吞了一整個大檔 / 大搜尋 | 你發現自己對早前步驟的細節「記不太清」 |

→ 命中「該壓縮」:執行上面的**壓縮節奏**。
→ 命中「該開新輪」:寫完整交接 → **停**(或明確開下一輪),不要硬撐把 context 塞爆。

---

### 結構化交接格式(固定、極短;下一輪/下個 agent 幾百 token 接手)

**每塊交接 append 到 `.coord/journal.md`,欄位固定、不加戲:**

```markdown
### [HANDOFF] <task-id> — <一句話標題> @ <YYYY-MM-DD HH:MM UTC+8> by <agent-id>
- DONE: <做了什麼,1–3 行,只留結論,不貼過程>
- EVIDENCE: <怎麼證明:指令 + 結果。例:`node scripts/verify-safety.cjs` → exit 0, 15/15>
- FILES: <碰過的檔,逗號分隔>
- NEXT: <下一步一句話,要能讓下一輪直接動手>
- OPEN: <待決/卡點,標類型:decision(要人拍板)/authorize(要人授權)/blocker;沒有就寫 none>
```

**規則**:5 個欄位缺一不可;每欄一句話;**不要**在交接裡貼原始輸出、貼整段 code、複述過程。它的唯一目的是讓「幾乎沒有 context 的下一個你」在 300 token 內知道站在哪、往哪走。

---

### 子代理外包重讀(大檔 / 大搜尋 → 只收「結論」)

**原則:凡是會吐出大量原文、但你只需要一個結論的動作,外包給子代理,讓它回結論不回原文。** 你的 context 只吸收那幾行結論。

**什麼該外包:**
- 「這個 30 檔的目錄裡,哪個檔定義了 X?」→ 子代理回**檔:行**,不回檔內容。
- 「跑 verify-*,綠不綠?」→ 子代理回 `PASS/FAIL + 關鍵數字`,不回整份 log。
- 「這份 2000 行的檔,跟 Y 有關的規則有哪些?」→ 子代理回**條列摘要 + 行號**,不回全文。
- 「這個大 JSON 裡符合條件的有幾筆、長怎樣?」→ 子代理回**計數 + 3 筆代表樣本**。

**外包指令模板(直接貼給子代理):**

```
任務:在 <路徑/範圍> 裡找出 <具體問題>。
只回:
1) 結論(1–3 句)
2) 證據(檔:行,或 指令→退出碼/關鍵數字)
3) 我下一步需要知道的 1 件事(若有)
不要回:整檔內容、整段搜尋結果、逐行過程。上限 ~200 字。
```

**收到後**:把那幾行結論寫進 `.coord/tasks/<id>.md` 或 STATE,原始問題結束——你**不需要**自己再讀那個大檔。

> 現成外包點:`$CLAIM check/status`(回 gate 綠紅)、瀏覽器/HTTP 實測子代理(回 PASS/FAIL + 數字)。優先用它們,別自己吞整份輸出。

---

### 開新輪 Boot SOP(乾淨 context,幾百 token 接回)

新一輪 / 新 agent **開場只做這 3 件事,不要一次讀一堆檔**:

```bash
node scripts/autopilot/ctx.mjs boot  # 印出 STATE 的 NOW/METRICS + journal 最後一塊交接
# ↑ 腳本出貨於 <SKILL>/templates/ctx.mjs,依 SKILL.md §6 裝進專案 scripts/autopilot/ 後這樣跑
# ↑ 這一份輸出就是你的全部起手 context(通常 <400 token)
```

1. 讀 `boot` 印出的 **NOW + METRICS + 最後一塊 HANDOFF** → 你已經知道站在哪、下一步是什麼。
2. **只在真的要動手改某任務時**,才打開那一個 `.coord/tasks/<id>.md`;**不要**預讀其他任務頁。
3. 開始做 → 回到上面的**壓縮節奏**。

**禁止的開場**:一上來把 CURRENT_STATE 全文 + 整份 journal + 一堆 docs 全讀進來——那正是把 context 一開場就燒掉一半的元凶。**只讀最後一塊交接 + NOW。**

---

### 反模式(出現任一 = 你正在把 context 燒掉)

- ❌ 把整檔 / 整段搜尋結果貼進推理後,還一直帶著它往下走。→ 抽結論、丟原文。
- ❌ 「總結一下目前」然後把總結**留在 context**。→ 總結要寫進 `journal`/任務頁。
- ❌ 重讀一個本輪讀過的檔。→ 讀你自己上次寫的摘要。
- ❌ 開場把所有狀態檔全文吸進來。→ 只 `ctx boot`。
- ❌ 做了 3 個任務都沒寫交接才想壓縮。→ 每 1 個任務就交接一次。
- ❌ 撐到 context 自動壓縮才處理。→ 60% 就主動壓,75% 就開新輪。
- ❌ 自己吞大檔找一個答案。→ 外包給子代理回結論。

---

### 附:狀態檔格式與壓縮腳本(見 supportingFiles)

- `.coord/STATE.md`、`.coord/tasks/<id>.md` 的可貼模板。
- `ctx.mjs`(出貨於 `<SKILL>/templates/ctx.mjs`,裝進專案後為 `scripts/autopilot/ctx.mjs`):一支小腳本,子命令 `boot / handoff / newpage / budget / stamp`,把「印最小接手 context」「append 交接」「開任務頁」「估 token 預算」自動化,讓笨模型少手抖。

=== supportingFiles ===

--- .coord/STATE.md ---
唯一動態快照（覆寫、不堆疊）。context 開場只需要這份的 NOW+METRICS。本 repo 可改用既有 CURRENT_STATE.md 取代。
# STATE — <project>（單一動態快照;覆寫,不 append 堆疊）
Updated: <YYYY-MM-DD HH:MM UTC+8> by <agent-id>

## NOW  （context 只需要這一塊）
- TASK: <當前任務 id + 一句目標>
- STEP: <當前這一小步,一句話,要能直接動手>
- BRANCH: <branch/worktree;若在 main 註明>
- LAST GREEN: <最近一次通過的 gate,如 verify-safety 15/15 @ 10:20>

## METRICS （關鍵指標,一行一個,3–6 條）
- build: <PASS/FAIL>
- tests: <12/12>
- blockers: <0 / 列出>

## POINTERS （要細節去這裡讀,不要塞進 context）
- 任務頁: .coord/tasks/<id>.md
- 交接流水帳: .coord/journal.md（只讀最後一塊）
- 路線圖: <docs/plan/00-...>

## QUEUE （下 1–3 步,每步一句,做完就往上換掉）
1. <...>
2. <...>


--- .coord/tasks/<id>.md ---
每任務一頁。壓縮後的重點與證據沉澱處；原始長輸出不入此檔。本 repo 對映 coordination/WORK_PACKAGES/*.md。
# TASK <id> — <title>
Status: claimed | in-progress | green | released
Owner: <agent-id>

## GOAL  （可驗收,一句話）
<...>

## SCOPE （只能碰這些檔;不在清單=不做）
- <path>

## ACCEPT （綠燈條件,逐條可勾）
- [ ] <...>
- [ ] <...>

## LOG  （壓縮後重點,append;禁止貼原始長輸出）
- <HH:MM> <一句重點 + 證據指標,如 `verify-x` → exit0 12/12>
- <HH:MM> <死路結論也記一行:X 此路不通,因為 Y>

## DECISIONS （這任務內拍過的板 / 待人拍板事項）
- <...>


--- ctx.mjs(出貨於 <SKILL>/templates/ctx.mjs)---
壓縮/交接小腳本(Node ESM,零依賴,跨平台)。**完整可跑版出貨於 `<SKILL>/templates/ctx.mjs`,單一真相源,此處不內嵌副本**(之前這裡有一份舊版內嵌,與 templates 版漂移,已收斂)。依 SKILL.md §6 複製進專案 `scripts/autopilot/` 後使用。子命令:`boot`(印最小接手 context)、`handoff`(append 固定格式交接)、`newpage`(開任務頁)、`budget`(估 token 預算並建議是否外包子代理)、`stamp`(覆寫 STATE 的 Updated 行)。路徑常數讀 `.autopilot.json`(stateDoc/handoffDoc),沒有就用 `.coord/*` 預設。


=== integrationNotes ===
與其他模組/既有體系的銜接:

1. 不另起爐灶,疊在既有收斂體系上。本 repo 的 docs/plan/07（Worklog System）已規定「動態真相只在 CURRENT_STATE.md、交接 append 到 CODEX_HANDOFF.md / ITERATION_LOG.md」。本模組的 .coord/STATE.md / journal.md / tasks/<id>.md 是「可攜版」抽象；在本 repo 落地時直接對映到 CURRENT_STATE.md / CODEX_HANDOFF.md / WORK_PACKAGES。若 SKILL 是通用發佈給任意專案，就用 .coord/*；若專供本 repo，把腳本裡的路徑常數指到既有檔即可（腳本頂部已留 PATHS 常數）。

2. 與 /start（自主迭代主迴圈）銜接:/start 的「停止條件 = context 快滿 → 先補任務 + 寫交接再停」正是本模組的 75% 觸發線。建議在 /start 的每輪步驟 6（收工）插一行「跑 ctx handoff 落交接」，並在「context 快滿」判斷改用本模組的代理計數器。

3. 與反幻覺紀律銜接:SKILL.md §2 IMPLEMENT 管「引用先確認存在、不離題、跑過才宣稱」(專案若有 grounded-coding 類 skill 則同義);本模組管「跑過的證據壓進檔、原文丟掉」。交接格式的 EVIDENCE 欄正好承接「沒跑過不宣稱」——EVIDENCE 必須是指令+退出碼/數字。

4. 與實測工具 / $CLAIM 銜接:第④點「子代理外包重讀」的現成外包點是瀏覽器/HTTP 實測子代理（回 PASS/FAIL + 數字）與 $CLAIM check/status（回 gate 綠紅）。模組明確要求優先用它們，而不是自己吞整份 log。

5. 若總 SKILL 有「多子代理/worktree」模組:本模組的交接格式與 STATE 覆寫原則，應被那個模組引用為「跨 agent 交棒的標準載體」，避免兩套交接格式並存。

風險/注意:.coord/ 目錄若進版控會與 CURRENT_STATE 體系重複造成雙寫。建議二選一——通用發佈用 .coord/ 且 .gitignore（純本地工作記憶）；本 repo 用則不建 .coord/、把腳本指向既有檔。務必避免「動態真相兩處」。