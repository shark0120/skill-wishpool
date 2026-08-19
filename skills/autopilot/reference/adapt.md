MODULE: 自適應專案偵測 + 一鍵啟動 bootstrap

# 模組 A —— 自適應專案偵測 + 一鍵啟動 bootstrap

> **這個模組的工作**:讓這支 SKILL 能用在**任何**專案(不只某個特定 repo)。開始任何多步工作前,先**偵測環境**(語言/套件管理器/build-test-lint-typecheck 指令/git/是否已有協作佇列);**若缺協作層 → 自動 bootstrap 一份可攜的 coordination**(`tasks.json` + 一支零依賴 claim CLI + 協議),再**從專案現況自動拆出第一批任務**,最後把控制權交給主迴圈模組。
>
> **這是笨模型也能照抄的流程**:每一步都有「貼上去就能跑的指令」+「if 有 X 就用 Y」的決策樹 + 「你現在應該看到什麼」的檢查點。不要跳步、不要憑記憶臆測指令 —— 一律讓偵測腳本告訴你答案。

---

## A0. 鐵律(跨專案通用,越界即停)

1. **先偵測、再動手。** 在跑任何 build/test 或改任何檔之前,必須先產出 `./.coord/project-profile.json`(A1)。沒有 profile 就不知道這個專案的指令長怎樣 —— 禁止用記憶猜 `npm test`。
2. **偵測與 bootstrap 只寫 `.coord/`(或既有協作目錄)這一個資料夾**,不碰專案原始碼。這一步本身是**唯讀專案 + 只新增工具檔**,不需要使用者授權。
3. **能自動化的絕不手改 JSON。** 插入任務用 `claim.mjs import`(會驗證 id 唯一、deps 存在、範圍不撞),不要手動編輯 `tasks.json` 的 `tasks[]`。
4. **授權紅線一律不自動做**:`git push` / 動 `main` / 開 PR / 部署 / 任何外部花費(付費 API)/ 刪資料 / 改權限 / 寫 `.env` 祕密值。偵測到這類需求 → 拆成 `ownerType: authorize` 的任務丟給使用者,不自己執行。
5. **偵測不到就標記,不要編。** 指令(尤其 lint/typecheck)偵測不到 → 該欄位留空,對應 gate 會**自動略過並警告**,而不是硬跑一個不存在的指令假裝 PASS。

---

## A1. Phase 0 —— 偵測(產出 project-profile.json)

**做什麼**:跑本 SKILL 附的 `detect.mjs`,它會唯讀掃描專案並寫出一份機器可讀的環境檔。之後每個模組都讀這份檔,不再各自猜。

### 前置決策樹:偵測腳本用什麼跑?

| if | then |
|---|---|
| `node --version` 有輸出 | 用 **Node** 版偵測(主線,零依賴):`node <SKILL>/assets/coord/detect.mjs` |
| 沒有 Node | **停**。回報使用者「這台機器沒有 Node,無法啟動可攜協作層(本 skill 只出貨 Node 版工具)」,不要繼續。若專案自帶 Python 版 claim CLI(`claim.py`),可沿用該專案自己的,見 A2/A6。 |

> `<SKILL>` = 這支 skill 自己的資料夾。若不確定路徑,先把偵測腳本複製進專案再跑(見 A3 的複製指令);複製後路徑固定為 `.coord/detect.mjs`。

### 執行(shell 無關,Node 指令在 bash / PowerShell 都一樣)

```bash
# 1) 先把協作資產放進專案(冪等:已存在就跳過覆蓋,見 A3 決策樹)
#    最省事的做法:先複製,再從 .coord/ 內就地執行偵測。
node .coord/detect.mjs          # 若還沒複製,先做 A3 再回來
```

`detect.mjs` 會把結果同時印到畫面 **並** 寫入 `.coord/project-profile.json`,長這樣:

```jsonc
{
  "os": "win32",
  "git": { "isRepo": true, "branch": "feature/x", "root": "...", "hasRemote": true },
  "runtimes": { "node": "v20.11.0", "python": "3.11.5" },
  "packageManager": "pnpm",
  "language": ["node"],
  "commands": {
    "install":  "pnpm install",
    "build":    "pnpm run build",
    "test":     "pnpm test",
    "lint":     "pnpm run lint",
    "typecheck": "pnpm run typecheck"   // 或 null(偵測不到)
  },
  "coordination": { "exists": false, "dir": null, "cli": null, "queueTasks": 0 },
  "sources": { "readme": true, "todoFiles": ["TODO.md"], "roadmapDocs": ["docs/plan/00.md"] }
}
```

### 偵測邏輯決策樹(detect.mjs 內建;此表供你「看懂它為什麼這樣判」與人工覆核)

**套件管理器 + 指令**(由「哪個 manifest / lockfile 存在」決定,先命中先用):

| 偵測到的檔 | 語言 | 套件管理器 | test | lint | typecheck |
|---|---|---|---|---|---|
| `pnpm-lock.yaml` | node | pnpm | `pnpm test` | `pnpm run lint` | `pnpm run typecheck`* |
| `yarn.lock` | node | yarn | `yarn test` | `yarn lint` | `yarn typecheck`* |
| `bun.lockb` | node | bun | `bun test` | `bun run lint` | — |
| `package-lock.json` / 只有 `package.json` | node | npm | `npm test` | `npm run lint` | `npm run typecheck`*(否則 `npx tsc --noEmit`,若有 `tsconfig.json`) |
| `pyproject.toml` 含 `[tool.poetry]` | python | poetry | `python -m pytest -q` | `ruff`/`flake8`(讀 toml) | `mypy`/`pyright`(讀 toml) |
| `pyproject.toml` 含 `[tool.uv]` 或 `uv.lock` | python | uv | `python -m pytest -q` | 同上 | 同上 |
| `requirements.txt` / `setup.py` | python | pip | `python -m pytest -q` | 同上 | 同上 |
| `Cargo.toml` | rust | cargo | `cargo test` | `cargo clippy -- -D warnings` | (clippy 兼任) |
| `go.mod` | go | go | `go test ./...` | `go vet ./...` | (vet/build 兼任) |
| `pom.xml` | java | maven | `mvn -q test` | — | — |
| `build.gradle[.kts]` | java | gradle | `./gradlew test` | — | — |

\* Node 的 `build`/`test`/`lint`/`typecheck` 一律**從 `package.json.scripts` 實際挑名**(`typecheck`→`type-check`→`tsc` 依序找),挑不到才留 null。
**`Makefile` 覆寫規則**:若有 `Makefile` 且某目標(`build`/`test`/`lint`/`typecheck`)存在、而上面沒偵測到對應指令 → 用 `make <target>` 補上。

### ✅ 檢查點 A1

- [ ] `.coord/project-profile.json` 存在且能 `JSON.parse`。
- [ ] `commands.test` **不是 null**(至少測試指令要有;若是 null → 這專案沒有測試入口,到 A4 拆任務時 gate 會退化成人工 accept,先記下來)。
- [ ] `git.isRepo` 為 true。若 false → **先問使用者**要不要 `git init`(這是狀態變更,不自動做);未 init 前協作鎖仍可用(只是無法用分支隔離)。
- 沒過 → 別往下走,先解掉(多半是複製資產沒成功,回 A3)。

---

## A2. Phase 1 —— 決策:採用既有協作層,還是 bootstrap 新的?

讀 `project-profile.json` 的 `coordination` 欄位,走這棵樹:

```
coordination.exists == true ?
├─ 是 → coordination.cli 指向一支 claim CLI ?
│       ├─ 是 → 【採用】用既有的。跑一次 selftest 確認可用:
│       │        node <dir>/claim.mjs selftest   (或 python <dir>/claim.py selftest)
│       │        → selftest 綠 → 直接跳到 A5(交棒主迴圈),不要 bootstrap、不要覆蓋。
│       │        → selftest 紅/報錯 → 視為壞掉,走「並存升級」:把可攜 CLI 複製成
│       │          <dir>/claim.portable.mjs 並用它,不刪原檔(避免破壞別人的東西)。
│       └─ 否(只有 tasks.json 沒有 CLI) → 複製可攜 claim.mjs 進同一個 <dir>,
│                指到既有 tasks.json。跑 selftest。
└─ 否 → 【Bootstrap】進 A3 建立全新可攜協作層。
```

> **為什麼要先問「有沒有」**:多個 session / 多帳號可能已經在同一個 repo 跑過這支 SKILL。重複 bootstrap 會覆蓋別人正在用的佇列 = 事故。偵測到就採用,是預設安全行為。

---

## A3. Phase 2 —— Bootstrap 可攜協作層(缺才做)

### 目錄選擇決策樹

| if | then |
|---|---|
| 專案已有 `coordination/` 目錄(即使沒 tasks.json) | 就用 `coordination/`(尊重既有慣例) |
| 否則 | 用 **`.coord/`**(點前綴、一望即知是工具、好 gitignore) |

以下用 `.coord/` 示範;若走 `coordination/` 就整段替換目錄名。

### 步驟 1:複製資產(冪等)

**bash / Git Bash / macOS / Linux:**
```bash
mkdir -p .coord
cp -n "<SKILL>/assets/coord/claim.mjs"          .coord/claim.mjs
cp -n "<SKILL>/assets/coord/detect.mjs"         .coord/detect.mjs
cp -n "<SKILL>/assets/coord/seed.mjs"           .coord/seed.mjs
cp -n "<SKILL>/assets/coord/PROTOCOL.md"        .coord/PROTOCOL.md
cp -n "<SKILL>/assets/coord/tasks.template.json" .coord/tasks.json   # 只在不存在時建立
```

**PowerShell:**
```powershell
New-Item -ItemType Directory -Force .coord | Out-Null
foreach ($f in 'claim.mjs','detect.mjs','seed.mjs','PROTOCOL.md') {
  if (-not (Test-Path ".coord/$f")) { Copy-Item "<SKILL>/assets/coord/$f" ".coord/$f" }
}
if (-not (Test-Path '.coord/tasks.json')) { Copy-Item '<SKILL>/assets/coord/tasks.template.json' '.coord/tasks.json' }
```

> `-n` / `Test-Path` 守衛 = **絕不覆蓋已存在的 tasks.json**(那是活的共享狀態)。CLI 腳本可安全覆蓋更新。

### 步驟 2:把偵測到的指令灌進 gate 別名

`tasks.template.json` 的 `gateAliases` 是空殼。跑這行讓 `detect.mjs` 回填(它偵測後會把 `commands.*` 寫進 `.coord/tasks.json` 的 `gateAliases`,若該檔的 tasks 為空才寫,避免動到別人的佇列):

```bash
node .coord/detect.mjs --write-gates
```

回填後 `.coord/tasks.json` 應有:
```jsonc
"gateAliases": {
  "@install": "pnpm install", "@build": "pnpm run build",
  "@test": "pnpm test", "@lint": "pnpm run lint", "@typecheck": "pnpm run typecheck"
}
```
之後任務的 `gate` 欄只要寫 `["@typecheck","@test"]`,CLI 執行時自動替換成真指令;**別名對應到空字串就自動略過那道 gate 並印警告**(專案沒 lint 也不會假 FAIL)。

### 步驟 3:忽略執行期暫存檔(避免被連帶提交)

在 `.gitignore` 追加(沒有就建立):
```
.coord/.tasks.lock
.coord/*.tmp
.coord/project-profile.json
.coord/seed-candidates.json
```
`tasks.json`、`claim.mjs`、`PROTOCOL.md` **要進版控**(共享狀態與工具);`.tasks.lock`、`project-profile.json`、seed 候選是機器本地暫存,不進版控。

### 步驟 4:自我驗證

```bash
node .coord/claim.mjs selftest     # 驗重疊/相依/鎖邏輯 + tasks.json 合法性
node .coord/claim.mjs status       # 應顯示「無人認領中」+ 統計
```

### ✅ 檢查點 A3

- [ ] `.coord/` 內有 `claim.mjs`、`tasks.json`、`PROTOCOL.md`、`detect.mjs`、`seed.mjs`。
- [ ] `claim.mjs selftest` 印出 `N pass, 0 fail`。
- [ ] `tasks.json.gateAliases` 已填入真實指令(至少 `@test`)。
- [ ] `.gitignore` 已排除 `.tasks.lock`。
- 全過 → 協作層已就緒。進 A4 填任務。

---

## A4. Phase 3 —— 從專案現況自動拆出第一批任務

**做什麼**:此時 `tasks.json` 的 `tasks[]` 是空的。從專案自己的現況萃取候選任務,人/AI 覆核後 import 進去。**第一批控制在 5–8 個**,寧少勿爛。

### 來源優先序(越上面越「具體可驗證」,越優先)

| 來源 | 怎麼抓 | 為什麼優先 |
|---|---|---|
| 1. **失敗中的測試** | 跑 `@test` 指令,解析 FAIL 的檔名 | 最硬:gate 天生 = 重跑該測試,綠不綠一翻兩瞪眼 |
| 2. **原始碼 TODO/FIXME** | `grep -rn "TODO\|FIXME" <src>`(排除 node_modules/.git) | 有明確檔案位置 → `owns[]` 好推 |
| 3. **TODO.md / ROADMAP.md 未打勾項** | 抓 `- [ ]` 開頭的行 | 作者明列的待辦 |
| 4. **roadmap/plan 文件** | `sources.roadmapDocs` 裡的下一里程碑 | 方向性,但常需人工切細 |
| 5. **README 的「Getting Started 缺口」** | 讀不通就跑不起來的步驟 | 補基礎設施 |

### 用附的 seed.mjs 自動產候選(非破壞性)

```bash
node .coord/seed.mjs           # 讀上述來源,寫出 .coord/seed-candidates.json(草稿,不動 tasks.json)
```

它輸出一個任務草稿陣列。**你(AI)逐一覆核**,套下面的「欄位填法」補全,存成 `.coord/seed-approved.json`,再:

```bash
node .coord/claim.mjs import .coord/seed-approved.json   # 驗證後併入 tasks.json
```

### 每個任務的欄位填法(照抄這張對照表)

| 欄位 | 怎麼決定 | 例 |
|---|---|---|
| `id` | `<類別>-<短名>`,kebab-case,唯一 | `fix-login-null-guard` |
| `title` | 一句話講清楚交付物 | `修 login 空值崩潰` |
| `ownerType` | 見下方「ownerType 決策樹」 | `ai` |
| `owns[]` | 這任務**會寫入**的檔/目錄(鎖範圍)。**推不出來就別猜 → 設 ownerType=decision** | `["src/auth/login.ts","tests/auth/login.test.ts"]` |
| `sharedTouch[]` | 需輕改但也算獨佔的共用檔(如 `types.ts`) | `["src/types.ts"]` |
| `deps[]` | 必須先完成的其他任務 id | `[]` |
| `gate[]` | 用 `@alias`(A3 填好的),或原始指令 | `["@typecheck","@test"]` |
| `accept[]` | gate 蓋不到的人工驗收點(逐條可勾) | `["空 email 不再 throw、回 400"]` |
| `priority` | `high`/`med`/`low` | `high` |
| `blocking` | 擋上線/擋其他任務就 `true` | `false` |
| `status` | 一律先 `"available"` | `available` |
| `claim` | 一律 `null` | `null` |

**owns[] 從來源推導的規則:**
- 來源=失敗測試 → `owns` = 該測試檔 + 它測的來源檔(同名/同目錄推)。gate = 重跑該測試檔。
- 來源=某檔的 TODO → `owns` = 該檔(+ 明顯關聯的測試檔)。
- 來源=roadmap 一句話 → 多半推不出精確檔 → **設 `ownerType: decision`**,`title` 寫清楚「需使用者/整合者切出檔案範圍」,不要亂鎖一大片。

**ownerType 決策樹:**
```
這任務可以由 AI 全自動完成、且不越 A0 授權紅線嗎?
├─ 可以,而且範圍(owns)明確 → "ai"
├─ 需要人拍板方向/取捨(選型、砍功能、UX 決策) → "decision"
└─ 需要人授權或親自(push/部署/花錢/改權限/填祕密) → "authorize"
```

### ✅ 檢查點 A4

- [ ] `claim.mjs import` 後 `claim.mjs status` 顯示任務數 ≥ 1。
- [ ] `claim.mjs list --available` 至少列出 1 個 `ownerType: ai` 且範圍不撞的任務。
- [ ] `claim.mjs selftest` 仍 `0 fail`(import 內建驗證:id 唯一、deps 都解析得到、無兩個 active 撞範圍)。
- [ ] 每個 `ai` 任務都有非空 `owns[]`。
- 若 `list --available` 是空的(全是 decision/authorize)→ 寫一份「卡在使用者的清單」交給使用者,本模組到此為止。

---

## A5. Phase 4 —— 交棒主迴圈

協作層與第一批任務就緒後,**這個模組的責任結束**。把控制權交給「認領→實作→自檢→提交→收尾」的主迴圈模組。標準起手三連(shell 無關):

```bash
node .coord/claim.mjs status                 # 現況
node .coord/claim.mjs next --agent <你的代號>  # 推薦下一個(blocking > priority)
# → claim <id> → 實作(只在 owns[] 內)→ check(跑 gate)→ 提交 → done
```

給自己一個獨特代號 `--agent <name>`(如 `a-7f3k`),多 session/多帳號各用不同代號,`claim.mjs` 的檔案範圍鎖保證不會兩個同時寫同一檔。

### ✅ 模組總出口檢查點

- [ ] `.coord/` 協作層存在且 `selftest` 綠。
- [ ] `project-profile.json` 記錄了可用的 test 指令。
- [ ] 佇列有 ≥1 個可立即認領的 `ai` 任務。
- 三者齊備 → 呼叫主迴圈模組;否則回對應 Phase 補齊。

---

## A6. 疑難決策速查(笨模型遇到就查這表)

| 症狀 | 判斷 | 動作 |
|---|---|---|
| `detect.mjs` 印 `packageManager: null` | 沒認得的 manifest | 人工看根目錄有什麼 build 檔;真的沒有 → 這不是可自動 build 的專案,gate 退化成人工 accept |
| `claim.mjs claim` 回 exit 2 | 範圍撞別人認領 | 換 `list --available` 裡另一個;先到先得,不要搶 |
| `claim.mjs done` 卡紅 | gate 沒過 | 修到綠;連兩輪修不好 → `release` 交還 + 交接註明,換別的任務 |
| `import` 報 `deps 無法解析` | 任務 deps 指到不存在的 id | 修 seed-approved.json 的 deps,或先 import 被依賴的那個 |
| 既有 `coordination/` 但 CLI 是 Python | 別的 SKILL 版本 | 用它的 `claim.py`;介面對等(list/claim/check/done/status);不要並存兩套 CLI 打架 |
| 多帳號同時 bootstrap | 競態 | 誰先寫成 `tasks.json` 誰贏;後到者偵測到 `coordination.exists` 就採用,不覆蓋 |


=== supportingFiles ===

--- assets/coord/(五件套,實際出貨) ---
以下五個檔案的**完整可跑版**實際出貨於 `<SKILL>/assets/coord/`,A3 的複製指令直接可用;原始碼以出貨檔為單一真相源,此處只留一行摘要,不再內嵌副本(避免兩份版本打架):

- `detect.mjs` — 零依賴唯讀偵測:OS/git/runtimes/套件管理器/build-test-lint-typecheck 指令/既有協作層/任務來源 → 寫 `.coord/project-profile.json`;`--write-gates` 回填 gateAliases(僅當 tasks 為空)。
- `claim.mjs` — 認領+自檢 CLI:諮詢式檔鎖、範圍重疊 exit 2、鎖忙 exit 3、原子寫、STALE 標記、status/list/next/claim/check/done/release/review/block/health/selftest/import,gate @alias 解析(空字串=略過+警告)。
- `seed.mjs` — 非破壞性拆任務:失敗測試/TODO/FIXME/未打勾清單 → `.coord/seed-candidates.json` 草稿,不動 tasks.json。
- `tasks.template.json` — 空佇列模板(schema `portable-coord/v1`),bootstrap 時複製成 `.coord/tasks.json`。
- `PROTOCOL.md` — 可攜協作協議常駐文件(鐵律/指令速查/停止條件)。

另有兩支選配(多代理並行時才需要,見 `reference/orchestration.md`):`fleet.mjs`(一次挑 N 個互斥任務的規劃器)、`dupes.mjs`(合併前分支去重)。同樣出貨於 `assets/coord/`。

=== integrationNotes ===
此模組是整支 SKILL 的「開機自舉層」,永遠最先跑,產出的兩份契約檔給後續模組消費:(1) `.coord/project-profile.json` —— 所有需要跑指令的模組(自檢/驗證/CI 模組)都讀這裡的 `commands.*`,絕不自行猜測 `npm test`;(2) `.coord/tasks.json` + `.coord/claim.mjs` —— 「主迴圈模組」(認領→實作→自檢→提交→收尾,對應本 repo 既有的 /start skill 概念)靠這兩者運作,claim CLI 的檔案範圍鎖是多 session/多帳號並行安全的唯一來源。銜接點:A5 出口 = 主迴圈入口,交棒條件是「selftest 綠 + test 指令存在 + ≥1 可認領 ai 任務」。與「收尾/佇列健康模組」互補:本模組負責「從零到有第一批任務」,收尾模組負責「佇列將空時補下一批」——兩者共用同一套 owns[] 推導規則與 ownerType 決策樹(ai/decision/authorize),應抽成 SKILL 共用附錄避免各寫一份。與「驗證模組」的 gate 概念統一:本模組把偵測到的指令寫成 gateAliases,驗證模組只需引用 @alias。安全上與 A0 授權紅線一致:凡 push/部署/花費/改權限一律拆成 authorize 任務丟回使用者,任何模組都不得自動執行。注意可攜性抉擇:協作 CLI 只出貨 Node 版(零依賴,見 assets/coord/);目標專案若自帶 Python 版 claim.py 則沿用該專案自己的;無 Node 且無既有 CLI → 本模組直接停並回報,不硬啟動。