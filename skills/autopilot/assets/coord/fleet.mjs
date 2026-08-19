#!/usr/bin/env node
// 平行派發規劃器(零依賴、唯讀,不改 tasks.json)。與 claim.mjs 同目錄使用。
// claim.mjs 的 next 只給一個且只保證不撞現有 active;fleet.mjs 一次挑出最多 N 個
// 『彼此 owns[] 也互不重疊』的可領任務,依 擋上線>優先級 排序,並為每個代理印出分工塊。
// 用法: node <coord目錄>/fleet.mjs --agents a,b,c  (或 --n 3)
import { readFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import { dirname, join } from 'node:path'
const TASKS = join(dirname(fileURLToPath(import.meta.url)), 'tasks.json')
const norm = p => String(p).replace(/\\/g,'/').replace(/\/+$/,'')
const overlaps = (a,b) => (a=norm(a),b=norm(b), a===b||a.startsWith(b+'/')||b.startsWith(a+'/'))
const lockPaths = t => [...new Set([...(t.owns||[]),...(t.sharedTouch||[])].map(norm))]
const isActive = t => t.status==='claimed'||t.status==='in-review'
const depsMet = (t,ts) => (t.deps||[]).every(d => ts.find(x=>x.id===d)?.status==='done')
const clash = (a,b) => lockPaths(a).some(p=>lockPaths(b).some(q=>overlaps(p,q)))
const rank = { high:0, med:1, low:2 }
const arg = k => (process.argv.find(a=>a.startsWith(k+'='))?.split('=')[1]) || (process.argv[process.argv.indexOf(k)+1])
const agents = (arg('--agents')||'').split(',').filter(Boolean)
const N = agents.length || Number(arg('--n')||3)
const { tasks } = JSON.parse(readFileSync(TASKS,'utf8'))
let cands = tasks.filter(t => t.ownerType==='ai' && t.status==='available' && depsMet(t,tasks)
    && !tasks.some(o=>o.id!==t.id && isActive(o) && clash(t,o)))
  .sort((a,b)=> (Number(!!b.blocking)-Number(!!a.blocking)) || ((rank[a.priority]??1)-(rank[b.priority]??1)))
const picked = []
for (const t of cands){ if(picked.length>=N) break; if(!picked.some(p=>clash(p,t))) picked.push(t) }
if(!picked.length){ console.log('沒有可平行派發的任務(佇列空或全撞)。先 health/next 補任務。'); process.exit(0) }
picked.forEach((t,i)=>{ const who=agents[i]||`agent-${i+1}`
  console.log(`\n===== 派給 ${who} :: ${t.id} =====`)
  console.log(`認領: node <coord目錄>/claim.mjs claim ${t.id} --agent ${who}`)
  console.log(`只准寫(owns): ${(t.owns||[]).join(', ')}`)
  console.log(`共享檔(已鎖住,只改你負責區段): ${(t.sharedTouch||[]).join(', ')||'（無）'}`)
  console.log(`禁碰: 上面以外一切,尤其其他代理的鎖與 sharedFiles`)
  console.log(`Gate(done 自動跑): ${(t.gate||[]).join(' && ')}`)
  console.log(`目標: ${t.goal||t.title||''}`) })
console.log(`\n共 ${picked.length} 個互不重疊任務可同時開工。整合者:序列化合併,一次一個。`)
