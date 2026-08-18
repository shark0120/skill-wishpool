---
name: ai
description: >
  小時制 AI TOKEN 燃燒戰役：/ai 10、/ai 10h、燒 10 小時、無限迭代、大量做 skill。
  依使用者給的小時數排出詳細時程與任務密度，平行 scout、大量產出/強化 Skills、
  安全區實作與部署、loop-until-dry 無限迭代；每 N 輪強制 context 壓縮寫入持久狀態，
  換 session 可續跑。當使用者說 /ai、/AI、燒 token、燒額度 N 小時、開戰役、
  skill 工廠、無限迭代 N 小時 時使用。
argument-hint: "[HOURS] [site=<專案代號>|multi|skills] [mode=burn|skills|mixed] [+resume]"
---

# /ai — 小時制 TOKEN 燃燒戰役

> **一句話**：你給小時數 → 我排出每小時任務表 → **大量產 skill + 安全區實作 + 無限迭代到 dry 或時間到** → 過程中**強制壓縮上下文**，換窗也能接。

## 觸發與參數

```text
/ai 10
/ai 10h
/ai 10 site=web mode=mixed
/ai 6 mode=skills
/ai resume
/ai stop
```

也接受口語：`燒 10 小時`、`開 10h 戰役`、`無限迭代 8 小時`。

| 參數 | 含義 | 預設 |
|---|---|---|
| `HOURS` / `Nh` | 戰役時長（小時） | **必填**（resume/stop 除外） |
| `site=` | <專案代號> / multi / skills | multi(本機多專案) |
| `mode=burn` | 偏站點實作/修復/SEO | — |
| `mode=skills` | 偏大量寫/強化 Skills | — |
| `mode=mixed` | 前 30% skill 工廠 + 中 50% 實作 + 後 20% 驗證加固 | **預設** |
| `resume` | 讀既有 AI_CAMPAIGN 續跑 | — |
| `stop` | 寫 HANDOFF 停 | — |

**不要**先反問「要做什麼」。有小時數就開跑；只有 `/ai` 無數字時才問一次小時數。

## 絕對安全界（壓過「燃燒」）

燃燒給的是**強度與時長**，不是權限：

1. 不碰 payment/billing/ledger/balance/auth/ban/schema/secrets/nginx。
2. 不全量 `deploy.py`；部署走 `safe-deploy-loop` 單檔。
3. 不 push 遠端、不 mass ban、不刪庫、不外部付費 API（除非使用者另授權）。
4. `git add` 明確路徑。
5. token/密碼不進任何 state / skill / WORKLOG。
6. 無效忙碌禁止：重複同一 diff 空轉、無 accept 的假任務、為湊量複製貼上 skill。

## 持久狀態（跨 session / 壓縮後續命）

```text
<你的專案>\.claude\ai-campaign\
  AI_CAMPAIGN.md       # 主狀態（時程、進度、dry、下一刀）
  HOUR_PLAN.md         # 每小時詳細任務表（開跑時寫死，可微調）
  SKILL_BACKLOG.md     # 要製造/強化的 skill 清單
  WORK_BACKLOG.md      # 站點/ops 工作項
  ROUND_LOG.md         # 每輪一行
  COMPRESS.md          # 最新壓縮快照（context-compress 產物）
  HANDOFF.md           # 停手/換窗交接
  skills-outbox/       # 本戰役新建 skill 的暫存索引
```

模板在本 skill 的 `templates/`。開跑若目錄不存在就從模板複製。

## 時數 → 產能排程（核心）

設 `H` = 小時數（可小數，如 1.5）。所有數字是**工作規劃目標**，不是保證燒光 token。

### 總量公式

| 指標 | 公式 | 例 H=10 |
|---|---|---|
| 時段數 `slots` | `H`（每小時 1 大時段） | 10 |
| 每時段輪次 `rounds_per_hour` | mode=skills: 4；burn: 3；mixed: 3 | 3 |
| 目標總輪次 `max_rounds` | `slots * rounds_per_hour` | 30 |
| dry 停門檻 | 連續 **3** 輪無新可驗證產出（時間未到可降級 scout 再生） | 3 |
| 平行 scout/小時 | `min(4, 1+floor(H/4))` | 3 |
| 新建/強化 skill 目標 | mode=skills: `4*H`；mixed: `2*H`；burn: `max(2, H/2)` | mixed→20 |
| 站點可驗證切片目標 | mode=burn: `3*H`；mixed: `2*H`；skills: `max(2, H/2)` | mixed→20 |
| 壓縮節奏 | 每 **2** 輪 或 每 **25 分鐘** 牆鐘（先到先做）寫 `COMPRESS.md` | — |
| 驗證保留 | 最後 **max(0.5h, 0.1*H)** 只做 verify/加固/HANDOFF，不開新戰場 | 1h |

### 每小時時段模板（寫入 HOUR_PLAN.md）

對 `h = 1..H`：

```text
## Hour h / H  (wall target: T+h-1 → T+h)
- Theme: <依 mode 與 h 位置>
- Scout: N 個平行唯讀 lens
- Skill factory: 產出或強化 K 個 skill（有 trigger/驗收）
- Ship slices: 1–2 個可驗證實作（安全區）
- Verify: lint/curl/log 或 skill 自檢
- Compress?: 若本小時第偶數輪或距上次壓縮≥25m → 是
- Exit criteria: 本小時至少 1 個 skill 落地 或 1 個站點切片驗證綠
```

**Theme 隨進度變（mixed 預設）**：

| 進度 | Theme |
|---|---|
| 0–20% | 基建：狀態機、路由 skill、缺口掃描、finish-inflight |
| 20–50% | Skill 工廠高峰：模糊指令/部署/站點/ops/SEO/壓縮相關 skill 補齊 |
| 50–80% | 實作燃燒：用新 skill 真的改站/修洞/部署驗證 |
| 80–100% | 加固：對抗驗證、補測試文案、HANDOFF、砍無效 skill、dry 收斂 |

`mode=skills`：全程偏工廠，但每小時仍至少 1 次「用新 skill 跑一次真實任務」防假 skill。  
`mode=burn`：工廠只補缺口 skill，主力站點切片。

### 小時密度表示例（H=10, mixed）— 開跑時實寫進 HOUR_PLAN

| Hour | Theme | Skills 目標 | 站點切片 | Scout | 壓縮 |
|---|---|---|---|---|---|
| 1 | 基建+健康 | 2 | 1 | 3 | 是（開場基線） |
| 2 | Skill 工廠 | 3 | 1 | 3 | 否 |
| 3 | Skill 工廠 | 3 | 1 | 3 | 是 |
| 4 | Skill 工廠+試用 | 2 | 2 | 3 | 否 |
| 5 | 實作燃燒 | 2 | 3 | 2 | 是 |
| 6 | 實作燃燒 | 2 | 3 | 2 | 否 |
| 7 | 實作燃燒 | 2 | 3 | 2 | 是 |
| 8 | 實作+加固 | 2 | 2 | 2 | 否 |
| 9 | 加固/補洞 | 1 | 2 | 2 | 是 |
| 10 | VERIFY ONLY | 0 新戰場 | 驗收/回滾點 | 1 | 最終 COMPRESS+HANDOFF |

H 不是 10 時：**按比例縮放**同一曲線（前 20% 基建 … 末 10% verify-only）。

## 主迴圈（無限迭代直到時間或 dry）

```
BOOT → PLAN_HOURS → LOOP:
  LOCATE → SCOUT → FACTORY → PICK → DO → VERIFY → SHIP → RECORD → COMPRESS? → CHAIN
→ FINAL_VERIFY → HANDOFF
```

### BOOT
1. Parse `H` / mode / site / resume。
2. 建或讀 `ai-campaign/`。
3. `agent_id = ai-<4碼>`。
4. 記 `started_at`、`deadline_at ≈ now+H`（牆鐘參考；無精確時鐘就用 round 進度）。
5. 健康探測 + dirty → `finish-inflight`。
6. 中文 5 行開跑報告：H、mode、目標 skill 數、max_rounds、狀態路徑。

### PLAN_HOURS
- 生成完整 `HOUR_PLAN.md`（上表邏輯）。
- 預填 `SKILL_BACKLOG.md`（見 skill 工廠種子清單）。
- 預填 `WORK_BACKLOG.md`（站點安全區機會，scout 後再補）。

### LOOP 單輪（對應 autonomous-iterate 精神）

1. **LOCATE**：讀 `AI_CAMPAIGN.md` + `COMPRESS.md`（勿重讀整段對話史）。
2. **SCOUT**：平行唯讀（health/ux/seo/skills-gap/ops）；結果寫 backlog，**不要**把大 log 留在主 context。
3. **FACTORY**（若本小時還有 skill 配額）：
   - 呼叫 **skill-factory** 規則（本 skill `reference/skill-factory.md`）。
   - 每個新 skill 必須：明確 `name`、`description` 觸發句、鐵律、可執行步驟、與現有 skill 不重複。
   - 寫入 `<你的專案>/.claude/skills/<name>/SKILL.md` 或 `~/.claude/skills/<name>/`（全域工具放 user skills）。
   - 更新 `SKILL_BACKLOG` 打勾 + `skills-outbox` 索引一行。
4. **PICK**：1 個站點切片 **或** 1 組 skill 試跑任務（有 accept）。
5. **DO**：站點 skill / safe-deploy-loop / ops-recover；最小 diff。
6. **VERIFY**：綠才算；同一錯 2 次 → park。
7. **SHIP**：需上線才部署。
8. **RECORD**：ROUND_LOG 一行；更新 campaign 進度（hour_index、round、done 計數）。
9. **COMPRESS?**：達節奏 → 跑 context-compress 工作流，覆寫 `COMPRESS.md`（schema 見 templates）。主對話此後**只引用 COMPRESS + campaign 狀態**，不回放舊工具輸出。
10. **CHAIN**：
    - 有產出 → dry=0，立刻下一輪（**不問**要不要繼續）。
    - 無產出 → dry+=1；若 dry≥3 且未到末段 → 強制大 scout / 換 site lens 再生 backlog；仍 dry → 提前進入 FINAL。
    - 牆鐘/輪次進入最後 10% → FINAL_VERIFY。
    - `round >= max_rounds` 或使用者 `/ai stop` → FINAL。

### FINAL_VERIFY
- 抽樣驗證本戰役改動與新 skill 可觸發性。
- 刪/合併明顯重複的空殼 skill（若有）。
- 寫 `HANDOFF.md` + WORKLOG 一則。
- status=stopped。

## Context 壓縮協議（強制）

每次壓縮寫入 `COMPRESS.md`，結構固定：

```markdown
# COMPRESS snapshot @ <time> R<round>
## Goal / Hours left
## Constraints (no-touch)
## Done (evidence only)
## Skills added/updated (paths)
## Open backlog (top 10)
## Blockers (owner)
## Next 3 actions
## Do not reopen (rejected)
```

規則：
- 壓縮後**禁止**再依賴「我記得剛才 curl 全文」；要證據就短引用或重跑最小命令。
- 大工具輸出讀完只留結論進 COMPRESS / ROUND_LOG。
- 換 session：先讀 `HANDOFF.md` + `COMPRESS.md` + `AI_CAMPAIGN.md`，再 `/ai resume`。

詳細可再載入 `context-compress` skill；戰役內以本協議為準，避免重複讀長文。

## Skill 工廠種子（可擴、去重）

開跑時把尚未存在的項推進 `SKILL_BACKLOG.md`：

**路由/模糊**
- 更深的站點別名、錯誤碼→修復、中英口語映射

**部署/ops**
- php-fpm reload 檢查清單、單檔 scp 配方、cliproxy 雙池、log 脫敏 tail

**站點垂直**
- 站台 A:前台導流 UI、推薦流程、部落格 SEO、i18n 缺 key 掃描
- 站台 B:後台徽章、會員頁 RWD(禁金融相關)
- 站台 C:SEO 連打、文案一致性

**戰役元 skill**
- hour-burn 報告、skill 去重審計、accept 寫作器、scout 透鏡包

**品質**
- 對抗驗證清單、靜態測試觸發器、WORKLOG 格式器

工廠寫 skill 時遵守：description 要有真實觸發句；步驟可執行；標明 no-touch；避免與 `safe-deploy-loop` / `ops-recover` / `autonomous-extend` 重複——重複則**強化舊檔**而非新建。

## 對使用者輸出節奏

| 時機 | 長度 |
|---|---|
| 開跑 | ≤10 行：H、plan 摘要、路徑 |
| 每輪 | 3–6 行：做了什麼、證據、hour/round、dry |
| 每小時切段 | 6–10 行小時小結 |
| 壓縮後 | 1 行「已壓縮 → COMPRESS.md」 |
| 收工 | 完成 skill 列表、站點切片、HANDOFF 路徑 |

## 與既有 skill 接線

```
/ai (本 skill)
  ├─ autonomous-extend / autonomous-iterate / chain-next
  ├─ skill-factory 規則（reference/skill-factory.md）
  ├─ context-compress（協議對齊）
  ├─ intent-to-task / fuzzy-ship / safe-deploy-loop
  ├─ ops-recover / finish-inflight / site-health-sweep
  └─ <專案>-code / seo-growth-loop ...
```

`execute-better`：**不要**再包一層；本 skill 擁有整個 turn。

## 快速失敗

- 無 H 且非 resume/stop → 問：`要燒幾小時？例 /ai 10`
- 全是禁區缺口 → 只產 skill + 文件化 blocked，不硬改 production
- 配額/窗口將盡 → 提前 FINAL，不開新切片

## 開跑檢查清單（照做）

- [ ] 解析 H/mode/site
- [ ] 初始化 ai-campaign 從 templates
- [ ] 寫 HOUR_PLAN 全表
- [ ] 第一輪 compress 基線
- [ ] 進入 LOOP，直到時間或 dry
- [ ] HANDOFF + WORKLOG
