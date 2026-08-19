#!/usr/bin/env node
/**
 * next-round.mjs — autopilot 「跑到底(loop-until-dry)」的持久狀態機。零依賴、純 fs。
 *
 * 讓「連續 2 輪確實無新可做才停」的 dryRounds 計數,能跨『同輪續跑 → 續派子代理 →
 * 排程喚醒』存活。續派/排程接手時先 `decide`,才不會把 dry 計數算錯或重跑已完成的輪。
 * 絕不做任何 git / network 動作(唯讀決策器)。
 *
 * 用法:
 *   node next-round.mjs record --agent s-XXXX --task <id|none> --commit <sha|none> \
 *        --evidence "gate 12/12 + 懷疑者全過" --refilled "id1,id2"
 *     → task!=none 或 refilled 非空 → 非空輪 → dryRounds=0;否則 dryRounds++。round++。
 *   node next-round.mjs decide --agent s-XXXX [--max-dry 2]
 *     → dryRounds>=max 或 stopReason 已設 → 印 STOP + 交接骨架;否則印 CONTINUE + 「立刻繼續下一輪」。
 *   node next-round.mjs show          # 印目前 loop-state
 *   node next-round.mjs pending --authorize "主機,出圖$" --decision "D1"   # 記待使用者清單
 *   node next-round.mjs stop --reason "剩全 authorize"                       # 手動標停
 *   node next-round.mjs selftest
 */
import { existsSync, readFileSync, writeFileSync, mkdirSync } from 'node:fs'
import { dirname } from 'node:path'

const cfg = (() => { try { return JSON.parse(readFileSync('.autopilot.json', 'utf8')) } catch { return {} } })()
const STATE = cfg.loopState || 'coordination/loop-state.json'

function load() {
  try { return JSON.parse(readFileSync(STATE, 'utf8')) }
  catch { return { schema: 'run-until-dry/v1', agentId: null, round: 0, dryRounds: 0, lastRound: null, refilledTaskIds: [], pendingUser: { authorize: [], decision: [] }, stopReason: null } }
}
function save(s) { mkdirSync(dirname(STATE) || '.', { recursive: true }); writeFileSync(STATE, JSON.stringify(s, null, 2) + '\n') }

function args(argv) {
  const o = { _: [] }
  for (let i = 0; i < argv.length; i++) {
    const a = argv[i]
    if (a.startsWith('--')) { const k = a.slice(2); o[k] = (argv[i + 1] && !argv[i + 1].startsWith('--')) ? argv[++i] : 'true' }
    else o._.push(a)
  }
  return o
}
const nowISO = () => { try { return new Date().toISOString() } catch { return '(ts)' } }

const [cmd, ...rest] = process.argv.slice(2)
const o = args(rest)

if (cmd === 'record') {
  const s = load()
  if (o.agent) s.agentId = o.agent
  const didWork = (o.task && o.task !== 'none') || (o.refilled && o.refilled !== 'true' && o.refilled.length)
  s.dryRounds = didWork ? 0 : (s.dryRounds || 0) + 1
  s.round = (s.round || 0) + 1
  s.lastRound = { taskId: o.task || 'none', commit: o.commit || 'none', evidence: o.evidence || '', ts: nowISO() }
  s.refilledTaskIds = (o.refilled && o.refilled !== 'true') ? o.refilled.split(',').map((x) => x.trim()).filter(Boolean) : []
  save(s)
  console.log(`[record] round=${s.round} dryRounds=${s.dryRounds} ${didWork ? '(非空輪→歸零)' : '(空輪→+1)'}`)
}
else if (cmd === 'decide') {
  const s = load()
  const maxDry = Number(o['max-dry'] || 2)
  const stop = s.stopReason || (s.dryRounds >= maxDry ? `連續 ${s.dryRounds} 輪 dry` : null)
  if (stop) {
    console.log(`STOP — ${stop}`)
    console.log('\n寫「睡醒看這裡」交接:')
    console.log(`  round=${s.round} dryRounds=${s.dryRounds}`)
    console.log(`  待授權(需你): ${(s.pendingUser?.authorize || []).join('、') || '(無)'}`)
    console.log(`  待決策(需你): ${(s.pendingUser?.decision || []).join('、') || '(無)'}`)
    process.exit(0)
  }
  console.log(`CONTINUE — round=${s.round} dryRounds=${s.dryRounds}`)
  console.log('→ 立刻繼續下一輪(不等使用者):回主迴圈 LOCATE,發 `$CLAIM status` + `next --agent ' + (s.agentId || 's-XXXX') + '`。')
  console.log('  (context 快滿改續派子代理;排程喚醒過夜跑需使用者事先明確同意 — 見 reference/max-loop.md。)')
}
else if (cmd === 'pending') {
  const s = load()
  if (o.authorize && o.authorize !== 'true') s.pendingUser.authorize = [...new Set([...(s.pendingUser.authorize || []), ...o.authorize.split(',').map((x) => x.trim())])]
  if (o.decision && o.decision !== 'true') s.pendingUser.decision = [...new Set([...(s.pendingUser.decision || []), ...o.decision.split(',').map((x) => x.trim())])]
  save(s); console.log('[pending] 已更新待使用者清單')
}
else if (cmd === 'stop') { const s = load(); s.stopReason = o.reason || '(手動停)'; save(s); console.log('[stop] stopReason=' + s.stopReason) }
else if (cmd === 'show') { console.log(JSON.stringify(load(), null, 2)) }
else if (cmd === 'selftest') {
  // 純邏輯自測(不動真檔):dry 計數規則
  let pass = 0, fail = 0
  const chk = (n, c) => c ? pass++ : (fail++, console.error('  ✗ ' + n))
  const sim = (didWork, prev) => didWork ? 0 : prev + 1
  chk('非空輪歸零', sim(true, 3) === 0)
  chk('空輪+1', sim(false, 1) === 2)
  chk('連兩空輪達停線', sim(false, 1) >= 2)
  console.log(`selftest: ${pass} pass, ${fail} fail`); process.exit(fail ? 1 : 0)
}
else {
  console.log('用法: node next-round.mjs <record|decide|pending|stop|show|selftest> ... (見檔頭)')
}
