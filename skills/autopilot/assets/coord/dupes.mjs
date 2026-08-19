#!/usr/bin/env node
// 平行分支去重(可選,worktree 層才需要)。唯讀:用 git ancestry 判定 wp/* 分支去重,
// 分類 SUBSUMED_BY_LEADER / SUBSET_OF_SIBLING / PARALLEL,給整合者 retire-vs-salvage 判定。
// 不 checkout 不改分支。用法: node <coord目錄>/dupes.mjs [leaderBranch]
import { execFileSync } from 'node:child_process'
const git = (...a) => { try { return execFileSync('git', a, {encoding:'utf8'}) } catch { return '' } }
const isAncestor = (a,b) => { try { execFileSync('git',['merge-base','--is-ancestor',a,b]); return true } catch { return false } }
const files = ref => new Set(git('ls-tree','-r','--name-only',ref).split('\n').filter(Boolean))
const branches = git('branch','--list','wp/*','--format=%(refname:short)').split('\n').filter(Boolean)
const leader = process.argv[2] || 'main'
const leaderFiles = files(leader)
for (const b of branches){
  if (b===leader) continue
  const behind = Number(git('rev-list','--count',`${leader}..${b}`).trim()||0)
  const unique = [...files(b)].filter(f=>!leaderFiles.has(f))
  let label, verdict
  if (isAncestor(b, leader)) { label='SUBSUMED_BY_LEADER'; verdict='retire — 每個 commit leader 都有,零損失' }
  else if (branches.find(s=>s!==b && isAncestor(b,s))) { label='SUBSET_OF_SIBLING'; verdict=`retire — 被 ${branches.find(s=>s!==b && isAncestor(b,s))} 完全包含` }
  else { label='PARALLEL'; verdict=`獨立線,leader 缺 ${behind} commit;先看獨特檔再 retire` }
  console.log(`\n${b}\n  ${label}: ${verdict}`)
  if (unique.length) console.log(`  獨特檔(考慮 cherry-pick): ${unique.slice(0,8).join(', ')}${unique.length>8?' …':''}`)
}
