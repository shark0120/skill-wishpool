#!/usr/bin/env node
// 非破壞性自動拆任務:讀 project-profile.json 指出的來源(跑 @test 收失敗檔、grep TODO/FIXME、
// 抓 TODO.md/ROADMAP 的 - [ ] 項),產出 .coord/seed-candidates.json 任務草稿陣列供 AI 覆核;
// 不直接寫 tasks.json。owns[] 依 adapt.md A4 規則推導,推不出就標 ownerType=decision。
import { readFileSync, writeFileSync, existsSync } from 'node:fs'
import { execSync } from 'node:child_process'
import { join, dirname } from 'node:path'; import { fileURLToPath } from 'node:url'
const COORD=dirname(fileURLToPath(import.meta.url)); const ROOT=join(COORD,'..')
const prof=JSON.parse(readFileSync(join(COORD,'project-profile.json'),'utf8'))
const sh=c=>{try{return execSync(c,{cwd:ROOT,encoding:'utf8'})}catch(e){return (e.stdout||'')+(e.stderr||'')}}
const cands=[]
// 1) 失敗測試 → 每個失敗檔一個任務(gate=@test)
if (prof.commands.test){ const out=sh(prof.commands.test); const files=[...new Set((out.match(/[\w./-]+\.(test|spec)\.[a-z]+/g)||[]))]
  for (const f of files) cands.push({ id:`fix-${f.replace(/[^a-z0-9]+/gi,'-').toLowerCase()}`.slice(0,40), title:`修失敗測試 ${f}`, ownerType:'ai', owns:[f], sharedTouch:[], deps:[], gate:['@test'], accept:[`${f} 全綠`], priority:'high', blocking:false }) }
// 2) 原始碼 TODO/FIXME
const todo=sh(process.platform==='win32'?'git grep -n "TODO\\|FIXME"':'git grep -nE "TODO|FIXME"')
for (const line of todo.split('\n').slice(0,20)){ const m=line.match(/^([^:]+):(\d+):/); if(!m)continue; cands.push({ id:`todo-${m[1].replace(/[^a-z0-9]+/gi,'-').toLowerCase()}-${m[2]}`.slice(0,40), title:`處理 TODO ${m[1]}:${m[2]}`, ownerType:'ai', owns:[m[1]], sharedTouch:[], deps:[], gate:['@typecheck','@test'], accept:['TODO 已解且不回歸'], priority:'med', blocking:false }) }
// 3) TODO.md / ROADMAP 未打勾
for (const f of prof.sources.todoFiles){ if(!existsSync(join(ROOT,f)))continue; for(const l of readFileSync(join(ROOT,f),'utf8').split('\n')){ const m=l.match(/^\s*-\s*\[ \]\s*(.+)/); if(!m)continue; cands.push({ id:`roadmap-${cands.length}`, title:m[1].slice(0,60), ownerType:'decision', owns:[], sharedTouch:[], deps:[], gate:[], accept:[m[1]], priority:'med', blocking:false, _note:'需人工切出 owns 檔案範圍' }) } }
writeFileSync(join(COORD,'seed-candidates.json'),JSON.stringify(cands.slice(0,8),null,2)+'\n')
console.log(`寫出 ${Math.min(cands.length,8)} 個候選到 .coord/seed-candidates.json。逐一覆核、補 owns[]、存成 seed-approved.json,再 claim.mjs import。`)
