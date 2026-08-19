#!/usr/bin/env node
/**
 * resolve-context.mjs — autopilot 的跨專案執行上下文(CTX)解析器。零依賴。
 *
 * 開跑第一件事跑它:偵測本專案的認領 CLI / 看板 / 路線圖 / 狀態檔 / gate 候選 /
 * commit 署名 …，印成 JSON。之後 autopilot 所有步驟只引用 CTX,不硬編任何專案專屬值。
 * 偵測不到的標 UNKNOWN,**絕不編造**。
 *
 * 優先序(每個變數):.autopilot.json → 自動偵測 → 保守安全預設。
 * 用法:node resolve-context.mjs [--check]   (--check 只回 go/no-go)
 */
import { existsSync, readFileSync } from 'node:fs'
import { execSync } from 'node:child_process'

const read = (p) => { try { return readFileSync(p, 'utf8') } catch { return null } }
const json = (p) => { try { return JSON.parse(readFileSync(p, 'utf8')) } catch { return null } }
const firstExisting = (arr) => arr.find(existsSync) || 'UNKNOWN'

// 1) 顯式 config 優先
const cfg = json('.autopilot.json') || json('.claude/autopilot.json') || {}

// 2) 偵測 claim CLI / board
const claimCli = cfg.claimCli || (existsSync('coordination/claim.mjs') ? 'node coordination/claim.mjs' : 'UNKNOWN')
const boardPath = cfg.board || (existsSync('coordination/tasks.json') ? 'coordination/tasks.json' : 'UNKNOWN')
const board = boardPath !== 'UNKNOWN' ? json(boardPath) : null

// 3) gate hints:掃 package.json scripts
const pkg = json('package.json') || {}
const gateHints = Object.keys(pkg.scripts || {}).filter((s) => /^(verify|build|typecheck|test|smoke|lint)/.test(s))

// 4) commit trailer:config → 近 5 個 commit 既有 trailer
let trailer = cfg.commitTrailer || ''
if (!trailer) {
  try {
    const log = execSync('git log -5 --format=%b', { encoding: 'utf8' })
    const m = log.match(/^Co-Authored-By:.*$/m)
    if (m) trailer = m[0]
  } catch { /* not a git repo / no history */ }
}

let branch = 'UNKNOWN'
try { branch = execSync('git branch --show-current', { encoding: 'utf8' }).trim() || 'DETACHED' } catch {}
// 自適應分支:有遠端/共享 main → 不在 main 提交(先切工作分支);
// 單人/無遠端(main 就是本機工作線)→ 可直接在 main 本機提交(仍永不 push)。
// 可用 .autopilot.json.soloMode 明確覆寫。
let hasRemote = false
try { hasRemote = execSync('git remote', { encoding: 'utf8' }).trim().length > 0 } catch {}
const mainIsWorkingLine = (cfg.soloMode ?? !hasRemote)
const onMain = branch === 'main' || branch === 'master'

const ctx = {
  agentHint: cfg.agent || '(每次開跑自己生成 <model>-<4碼>)',
  branch,
  hasRemote,
  mainIsWorkingLine,
  branchPolicy: mainIsWorkingLine
    ? 'solo/無遠端:可直接在 main 本機提交(永不 push)'
    : '有遠端/共享:不在 main 提交,先切工作分支',
  claimCli,
  board: boardPath,
  sharedFiles: cfg.sharedFiles || board?.sharedFiles || [],
  gateAliases: cfg.gateAliases || board?.gateAliases || {},
  gateHints,
  planDoc: cfg.planDoc || firstExisting(['docs/plan/00-MASTER_PLAN_TO_LAUNCH.md', 'ROADMAP.md', 'PLAN.md', 'docs/ROADMAP.md']),
  stateDoc: cfg.stateDoc || firstExisting(['CURRENT_STATE.md', 'STATE.md', '.coord/STATE.md']),
  handoffDoc: cfg.handoffDoc || firstExisting(['CODEX_HANDOFF.md', 'HANDOFF.md', 'docs/ITERATION_LOG.md', '.coord/journal.md']),
  loopState: cfg.loopState || (existsSync('coordination/loop-state.json') ? 'coordination/loop-state.json' : 'coordination/loop-state.json'),
  commitTrailer: trailer || '(none)',
  viewport: cfg.frontendViewport || '375x812',
  healthMin: cfg.healthMin ?? 3,
  degraded: (claimCli === 'UNKNOWN' || boardPath === 'UNKNOWN'),
}

if (process.argv.includes('--check')) {
  if (onMain && !mainIsWorkingLine) { console.error(`NO-GO: 在 ${branch}(有遠端/共享 main)→ 先切/建工作分支再開跑`); process.exit(1) }
  if (ctx.degraded) console.log('GO(降級):無看板 → 走 §1.2,向使用者要一個目標')
  else if (onMain && mainIsWorkingLine) console.log(`GO(solo):${branch} 即本機工作線,提交到本機、永不 push`)
  else console.log(`GO: branch=${branch}, CTX 就緒`)
  process.exit(0)
}

console.log(JSON.stringify(ctx, null, 2))
if (ctx.degraded) console.error('\n⚠ 無看板(claimCli/board=UNKNOWN):走 SKILL §1.2 降級,或讀 reference/adapt.md bootstrap 自建。')
if (onMain && !mainIsWorkingLine) console.error('\n⚠ 你在 ' + branch + '(有遠端):動手前先切/建工作分支,別在共享 main 上寫。')
else if (onMain && mainIsWorkingLine) console.error('\nℹ solo/無遠端:main 就是你的工作線,可直接本機提交(仍永不 push;push/PR 要使用者授權)。')
