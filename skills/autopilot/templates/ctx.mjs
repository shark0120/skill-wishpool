#!/usr/bin/env node
/**
 * ctx.mjs — autopilot 的 200K context 壓縮小工具。零依賴、跨平台。
 *
 * 心法:context 是會被清空的草稿,磁碟才是記憶。腦子只留「當前一小步 + 幾個指標 + 檔案指標」。
 * 路徑優先序:.autopilot.json(stateDoc/handoffDoc)→ 偵測(CURRENT_STATE.md / CODEX_HANDOFF.md)
 *            → 通用 .coord/*。這樣同一支腳本在任何專案都對得上,不另起爐灶造成「動態真相兩處」。
 *
 * 子命令:
 *   boot                          印「最小接手 context」= STATE 的 NOW/METRICS + journal 最後一塊交接(通常 <400 token)
 *   handoff --task .. --done .. --evidence .. --files .. --next .. --open ..   append 固定 5 欄交接
 *   newpage --task .. --title .. --goal ..   開任務頁 .coord/tasks/<id>.md
 *   budget <path...>              估每個檔的 token,>~4k 建議外包子代理只回結論
 *   stamp --agent s-XXXX          覆寫 STATE 的 Updated 行
 */
import fs from 'node:fs'
import path from 'node:path'

const cfg = (() => { try { return JSON.parse(fs.readFileSync('.autopilot.json', 'utf8')) } catch { return {} } })()
const has = (p) => { try { fs.accessSync(p); return true } catch { return false } }
const firstExisting = (arr, fallback) => arr.find(has) || fallback

const STATE = cfg.stateDoc || firstExisting(['CURRENT_STATE.md', 'STATE.md'], '.coord/STATE.md')
const JOURNAL = cfg.handoffDoc || firstExisting(['CODEX_HANDOFF.md', 'HANDOFF.md', 'docs/ITERATION_LOG.md'], '.coord/journal.md')
const TASKDIR = cfg.taskDir || (has('coordination/WORK_PACKAGES') ? 'coordination/WORK_PACKAGES' : '.coord/tasks')
const BUDGET_WARN = 4000

function now() { const d = new Date(Date.now() + 8 * 3600e3); return d.toISOString().slice(0, 16).replace('T', ' ') + ' UTC+8' }
function args(argv) { const o = { _: [] }; for (let i = 0; i < argv.length; i++) { const a = argv[i]; if (a.startsWith('--')) { const k = a.slice(2); o[k] = (argv[i + 1] && !argv[i + 1].startsWith('--')) ? argv[++i] : 'true' } else o._.push(a) } return o }
// 混合 token 估:CJK≈1 char/token,ASCII≈4 char/token(保守)
function estTokens(s) { let cjk = 0, other = 0; for (const ch of s) { if (/[⺀-鿿豈-﫿＀-￯]/.test(ch)) cjk++; else other++ } return Math.round(cjk + other / 4) }
function lastBlock(md, marker = '### [HANDOFF]') { const i = md.lastIndexOf(marker); return i < 0 ? '(journal 尚無 [HANDOFF] 交接;讀檔尾即可)' : md.slice(i).trim() }

const [cmd, ...rest] = process.argv.slice(2)
const o = args(rest)

if (cmd === 'boot') {
  const state = has(STATE) ? fs.readFileSync(STATE, 'utf8') : `(${STATE} 不存在)`
  const cut = state.split('## POINTERS')[0].split('## 5')[0].trim().slice(0, 2400) // 只取開頭 NOW/METRICS 段
  const j = has(JOURNAL) ? fs.readFileSync(JOURNAL, 'utf8') : ''
  const out = `# BOOT (最小接手 context)\n來源 STATE=${STATE} JOURNAL=${JOURNAL}\n\n${cut}\n\n--- 最後一塊交接 ---\n${lastBlock(j)}`
  console.log(out)
  console.error(`\n[boot] 約 ${estTokens(out)} token 起手,足夠接回。要改某任務再開它的頁,別預讀其他。`)
}
else if (cmd === 'handoff') {
  const block = `\n### [HANDOFF] ${o.task || '?'} — ${o.title || (o.done ? o.done.slice(0, 24) : '')} @ ${now()} by ${o.agent || 'agent'}\n`
    + `- DONE: ${o.done || ''}\n- EVIDENCE: ${o.evidence || ''}\n- FILES: ${o.files || ''}\n- NEXT: ${o.next || ''}\n- OPEN: ${o.open || 'none'}\n`
  fs.mkdirSync(path.dirname(JOURNAL) || '.', { recursive: true })
  fs.appendFileSync(JOURNAL, block)
  console.log(`[handoff] append 到 ${JOURNAL}(${estTokens(block)} token)。記得 stamp / 更新 ${STATE} 的 NOW。`)
}
else if (cmd === 'newpage') {
  fs.mkdirSync(TASKDIR, { recursive: true })
  const p = path.join(TASKDIR, `${o.task}.md`)
  if (has(p)) { console.log(`[newpage] 已存在:${p}`) }
  else { fs.writeFileSync(p, `# TASK ${o.task} — ${o.title || ''}\nStatus: claimed\nOwner: ${o.agent || ''}\n\n## GOAL（可驗收,一句）\n${o.goal || ''}\n\n## SCOPE（只能碰這些檔）\n- \n\n## ACCEPT（逐條可勾）\n- [ ] \n\n## LOG（壓縮後重點 append;禁貼原始長輸出）\n- ${now()} 建立\n\n## DECISIONS\n`); console.log(`[newpage] 建立 ${p}`) }
}
else if (cmd === 'budget') {
  let total = 0
  for (const f of o._) { if (!has(f)) { console.log(`  (缺) ${f}`); continue } const t = estTokens(fs.readFileSync(f, 'utf8')); total += t; const flag = t > BUDGET_WARN ? '  ⚠ 太大→外包子代理回結論' : ''; console.log(`  ${String(t).padStart(6)} tok  ${f}${flag}`) }
  console.log(`  ------\n  ${String(total).padStart(6)} tok  合計`)
  if (total > BUDGET_WARN) console.error(`[budget] 偏大。別全吞進 context:挑最小必要,或外包子代理只回結論。`)
}
else if (cmd === 'stamp') {
  if (!has(STATE)) { console.error(`${STATE} 不存在`); process.exit(1) }
  let s = fs.readFileSync(STATE, 'utf8')
  if (/^Updated:.*$/m.test(s)) s = s.replace(/^Updated:.*$/m, `Updated: ${now()} by ${o.agent || 'agent'}`)
  else s = `Updated: ${now()} by ${o.agent || 'agent'}\n` + s
  fs.writeFileSync(STATE, s); console.log(`[stamp] ${STATE} Updated 行已更新`)
}
else {
  console.log('用法: node ctx.mjs <boot|handoff|newpage|budget|stamp> ...  (見檔頭)')
}
