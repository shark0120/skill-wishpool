#!/usr/bin/env node
// 可攜版認領+自檢 CLI(零依賴 Node)。放在 .coord/(或 coordination/)內,與 tasks.json 同目錄。
// 子命令:status | list [--available] | next --agent <n> | claim <id> --agent <n> [--note ...]
//         check <id> | done <id> --agent <n> [--note ...] | release <id> [--agent <n>]
//         review <id> --agent <n> | block <id> --reason ... | health [--min N] | selftest | import <file>
// 退出碼:0 成功 · 1 失敗/gate 紅 · 2 認領範圍衝突 · 3 鎖忙(稍後重試)
import { readFileSync, writeFileSync, existsSync, unlinkSync, renameSync, statSync, openSync, closeSync, writeSync } from 'node:fs'
import { spawnSync } from 'node:child_process'
import { join, dirname } from 'node:path'
import { fileURLToPath } from 'node:url'

const COORD = dirname(fileURLToPath(import.meta.url))
const TASKS = join(COORD, 'tasks.json')
const LOCK  = join(COORD, '.tasks.lock')
const repoRoot = join(COORD, '..')
const STALE_LOCK_MS = 60_000        // 諮詢鎖超過 60s 視孤兒可搶
const STALE_CLAIM_HOURS = 8         // 認領超過 8h 未更新標 ⚠STALE

// ---- 參數解析 ----
const argv = process.argv.slice(2)
const cmd = argv[0]
const pos = []; const opt = {}
for (let i = 1; i < argv.length; i++) {
  const a = argv[i]
  if (a.startsWith('--')) { const k = a.slice(2); const v = (argv[i+1] && !argv[i+1].startsWith('--')) ? argv[++i] : 'true'; opt[k] = v }
  else pos.push(a)
}

// ---- 檔案鎖(讀-改-寫序列化)----
let held = false
function acquireLock () {
  for (let tries = 0; tries < 2; tries++) {
    try { const fd = openSync(LOCK, 'wx'); writeSync(fd, `${process.pid} ${new Date().toISOString()}\n`); closeSync(fd); held = true; return }
    catch (e) {
      if (e.code !== 'EEXIST') throw e
      try { if (Date.now() - statSync(LOCK).mtimeMs > STALE_LOCK_MS) { unlinkSync(LOCK); continue } } catch { continue }
      console.error('鎖忙(.tasks.lock 被另一個 CLI 持有)。稍後重試同一指令。'); process.exit(3)
    }
  }
  console.error('搶孤兒鎖失敗,稍後重試。'); process.exit(3)
}
process.on('exit', () => { if (held) { try { unlinkSync(LOCK) } catch {} } })
function withLock (fn) { acquireLock(); try { return fn() } finally { if (held) { try { unlinkSync(LOCK) } catch {} held = false } } }

// ---- 讀寫(原子)----
function load () { return JSON.parse(readFileSync(TASKS, 'utf8')) }
function save (data) { const tmp = TASKS + '.tmp'; writeFileSync(tmp, JSON.stringify(data, null, 2) + '\n'); renameSync(tmp, TASKS) }

// ---- 範圍重疊 ----
const norm = p => String(p).replace(/\\/g, '/').replace(/\/+$/, '')
const overlaps = (a, b) => { a = norm(a); b = norm(b); return a === b || a.startsWith(b + '/') || b.startsWith(a + '/') }
const lockPaths = t => [...new Set([...(t.owns || []), ...(t.sharedTouch || [])].map(norm))]
const isActive = t => t.status === 'claimed' || t.status === 'in-review'
const clash = (a, b) => lockPaths(a).some(p => lockPaths(b).some(q => overlaps(p, q)))
const depsMet = (t, ts) => (t.deps || []).every(d => ts.find(x => x.id === d)?.status === 'done')
const rank = { high: 0, med: 1, low: 2 }
const availableOf = data => data.tasks.filter(t => t.ownerType === 'ai' && t.status === 'available' && depsMet(t, data.tasks)
  && !data.tasks.some(o => o.id !== t.id && isActive(o) && clash(t, o)))
const sortQueue = ts => [...ts].sort((a, b) => (Number(!!b.blocking) - Number(!!a.blocking)) || ((rank[a.priority] ?? 1) - (rank[b.priority] ?? 1)))
const find = (data, id) => { const t = data.tasks.find(x => x.id === id); if (!t) { console.error(`找不到任務 ${id}`); process.exit(1) } return t }

// ---- gate ----
function resolveGate (c, data) { if (!c.startsWith('@')) return c; const real = (data.gateAliases || {})[c]; return real === undefined ? null : real }
function runGate (t, data) {
  let ok = true
  for (const raw of (t.gate || [])) {
    const c = resolveGate(raw, data)
    if (c === null || c === '') { console.log(`  略過(別名未定義/專案無此指令):${raw}`); continue }
    const r = spawnSync(c, { cwd: repoRoot, shell: true, stdio: 'inherit' })
    const pass = r.status === 0 && !r.signal
    console.log(pass ? `  PASS ${c}` : `  FAIL ${c}`)
    if (!pass) ok = false
  }
  return ok
}

// ---- selftest(也被 import 用)----
function validate (data) {
  const errs = []
  const ids = new Set()
  for (const t of data.tasks) {
    if (!t.id) { errs.push('有任務缺 id'); continue }
    if (ids.has(t.id)) errs.push(`id 重複:${t.id}`); ids.add(t.id)
    for (const d of (t.deps || [])) if (!data.tasks.find(x => x.id === d)) errs.push(`${t.id} deps 無法解析:${d}`)
    if (!['ai', 'decision', 'authorize'].includes(t.ownerType || 'ai')) errs.push(`${t.id} ownerType 不合法:${t.ownerType}`)
  }
  const act = data.tasks.filter(isActive)
  for (let i = 0; i < act.length; i++) for (let j = i + 1; j < act.length; j++)
    if (clash(act[i], act[j])) errs.push(`active 範圍互撞:${act[i].id} × ${act[j].id}`)
  return errs
}

// ---- 子命令 ----
const cmds = {
  status () {
    const data = load()
    const act = data.tasks.filter(isActive)
    if (!act.length) console.log('無人認領中。')
    for (const t of act) {
      const ageH = t.claim?.ts ? (Date.now() - Date.parse(t.claim.ts)) / 3600e3 : null
      const stale = ageH !== null && ageH > STALE_CLAIM_HOURS ? ' ⚠STALE' : ''
      console.log(`${t.id} [${t.status}] by ${t.claim?.agent || '?'}${ageH !== null ? ` (${ageH.toFixed(1)}h)` : ''}${stale}`)
      console.log(`  鎖住:${lockPaths(t).join(', ') || '(無)'}`)
    }
    const by = {}; for (const t of data.tasks) by[t.status] = (by[t.status] || 0) + 1
    console.log(`統計:${Object.entries(by).map(([k, v]) => `${k}=${v}`).join(' ')} | 可立即認領 ai=${availableOf(data).length}`)
  },
  list () {
    const data = load()
    const ts = opt.available ? sortQueue(availableOf(data)) : data.tasks
    for (const t of ts) console.log(`${t.id} [${t.status}] (${t.ownerType || 'ai'}${t.blocking ? ',blocking' : ''},${t.priority || 'med'}) ${t.title || ''}`)
    if (!ts.length) console.log(opt.available ? '沒有可立即認領的 ai 任務。' : '佇列是空的。')
  },
  next () {
    const data = load()
    const q = sortQueue(availableOf(data))
    if (!q.length) { console.log('沒有可認領的 ai 任務(佇列空/全撞/剩 decision-authorize)。'); process.exit(0) }
    const t = q[0]
    console.log(`建議認領:${t.id} — ${t.title || ''}`)
    console.log(`  owns: ${(t.owns || []).join(', ')}`)
    console.log(`  認領:node ${COORD.split(/[\\/]/).pop()}/claim.mjs claim ${t.id} --agent ${opt.agent || '<代號>'}`)
  },
  claim () {
    withLock(() => {
      const data = load(); const t = find(data, pos[0])
      if (!opt.agent) { console.error('缺 --agent <代號>'); process.exit(1) }
      if (t.status !== 'available') { console.error(`${t.id} 不是 available(現況 ${t.status})。`); process.exit(1) }
      if (t.ownerType && t.ownerType !== 'ai') { console.error(`${t.id} 是 ${t.ownerType},卡在使用者,AI 不可認領。`); process.exit(1) }
      if (!depsMet(t, data.tasks)) { console.error(`${t.id} 的 deps 尚未全部 done。`); process.exit(1) }
      const hit = data.tasks.find(o => o.id !== t.id && isActive(o) && clash(t, o))
      if (hit) { console.error(`範圍撞到 ${hit.id}(by ${hit.claim?.agent || '?'})。換 list --available 裡不撞的。`); process.exit(2) }
      t.status = 'claimed'; t.claim = { agent: opt.agent, note: opt.note || '', ts: new Date().toISOString() }
      save(data); console.log(`已認領 ${t.id},鎖住:${lockPaths(t).join(', ') || '(無)'}`)
    })
  },
  check () {
    const data = load(); const t = find(data, pos[0])
    console.log(`check ${t.id} — 跑 gate[]:`)
    const ok = runGate(t, data)
    console.log(`accept[](人工逐條核):`)
    for (const a of (t.accept || [])) console.log(`  [ ] ${a}`)
    process.exit(ok ? 0 : 1)
  },
  done () {
    withLock(() => {
      const data = load(); const t = find(data, pos[0])
      if (!isActive(t)) { console.error(`${t.id} 不在認領中(現況 ${t.status})。`); process.exit(1) }
      if (opt.agent && t.claim?.agent && opt.agent !== t.claim.agent) { console.error(`${t.id} 由 ${t.claim.agent} 認領,你是 ${opt.agent}。`); process.exit(1) }
      console.log(`done 前重跑 gate[]:`)
      if (!runGate(t, data)) { console.error('gate 紅,不收。修到綠或 release。'); process.exit(1) }
      t.status = 'done'; t.claim = { ...(t.claim || {}), doneTs: new Date().toISOString(), doneNote: opt.note || '' }
      save(data)
      const unlocked = data.tasks.filter(x => x.status === 'available' && (x.deps || []).includes(t.id) && depsMet(x, data.tasks))
      console.log(`已完成 ${t.id},放鎖。${unlocked.length ? `解鎖了:${unlocked.map(x => x.id).join(', ')}` : ''}`)
    })
  },
  release () {
    withLock(() => {
      const data = load(); const t = find(data, pos[0])
      if (!isActive(t) && t.status !== 'blocked') { console.error(`${t.id} 不在認領/blocked 狀態。`); process.exit(1) }
      t.status = 'available'; t.claim = null; save(data)
      console.log(`已釋放 ${t.id},回 available。`)
    })
  },
  review () {
    withLock(() => {
      const data = load(); const t = find(data, pos[0])
      if (t.status !== 'claimed') { console.error(`${t.id} 不是 claimed。`); process.exit(1) }
      t.status = 'in-review'; save(data); console.log(`${t.id} → in-review(鎖仍持有,待整合者複審)。`)
    })
  },
  block () {
    withLock(() => {
      const data = load(); const t = find(data, pos[0])
      t.status = 'blocked'; t.blockReason = opt.reason || ''; save(data)
      console.log(`${t.id} → blocked:${t.blockReason}`)
    })
  },
  health () {
    const data = load(); const min = Number(opt.min || 3); const n = availableOf(data).length
    console.log(`可立即認領的 ai 任務:${n}(門檻 ${min})`)
    process.exit(n >= min ? 0 : 1)
  },
  selftest () {
    const data = load(); const errs = validate(data)
    const checks = ['tasks.json 可解析', 'id 唯一', 'deps 可解析', 'ownerType 合法', 'active 無範圍互撞']
    if (errs.length) { for (const e of errs) console.error(`FAIL ${e}`); console.error(`${checks.length - errs.length} pass, ${errs.length} fail`); process.exit(1) }
    console.log(`${checks.length} pass, 0 fail`)
  },
  import () {
    if (!pos[0]) { console.error('用法:import <file.json>(任務陣列)'); process.exit(1) }
    const incoming = JSON.parse(readFileSync(pos[0], 'utf8'))
    if (!Array.isArray(incoming)) { console.error('import 檔必須是任務陣列。'); process.exit(1) }
    withLock(() => {
      const data = load(); const ids = new Set(data.tasks.map(t => t.id))
      for (const nt of incoming) {
        if (!nt.id || ids.has(nt.id)) { console.error(`重複/缺 id:${nt.id}`); process.exit(1) }
        nt.status = nt.status || 'available'; nt.claim = nt.claim || null; ids.add(nt.id)
      }
      const merged = { ...data, tasks: [...data.tasks, ...incoming] }
      const errs = validate(merged)
      if (errs.length) { for (const e of errs) console.error(`拒絕 import:${e}`); process.exit(1) }
      save(merged); console.log(`import ${incoming.length} 個任務。跑 selftest 覆核。`)
    })
  }
}

if (!cmd || !cmds[cmd]) {
  console.log('用法:node claim.mjs <status|list|next|claim|check|done|release|review|block|health|selftest|import> ...(見檔頭註解)')
  process.exit(cmd ? 1 : 0)
}
cmds[cmd]()
