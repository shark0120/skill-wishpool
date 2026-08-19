#!/usr/bin/env node
// 零依賴 Node 偵測腳本:唯讀掃描專案,判定 OS/git/runtimes/套件管理器/build-test-lint-typecheck 指令/
// 是否已有協作層/可拆任務的來源,寫出 .coord/project-profile.json;
// --write-gates 旗標把 commands.* 回填進 tasks.json 的 gateAliases(僅當該 tasks 為空)。
import { readFileSync, existsSync, writeFileSync, readdirSync } from 'node:fs'
import { execSync } from 'node:child_process'
import { join, dirname } from 'node:path'
import { fileURLToPath } from 'node:url'
const COORD = dirname(fileURLToPath(import.meta.url)); const ROOT = join(COORD, '..')
const has = p => existsSync(join(ROOT, p))
const readJSON = p => { try { return JSON.parse(readFileSync(join(ROOT,p),'utf8')) } catch { return null } }
const sh = c => { try { return execSync(c,{cwd:ROOT,stdio:['ignore','pipe','ignore']}).toString().trim() } catch { return null } }
const which = c => sh(process.platform==='win32'?`where ${c}`:`command -v ${c}`)
const git = { isRepo: !!sh('git rev-parse --is-inside-work-tree'), branch: sh('git rev-parse --abbrev-ref HEAD'), root: sh('git rev-parse --show-toplevel'), hasRemote: !!sh('git remote') }
const runtimes = {}; for (const r of ['node','python','python3','go','cargo','java']) { const v = which(r) && sh(`${r} --version`); if (v) runtimes[r]=v }
let pm=null, language=[], commands={install:null,build:null,test:null,lint:null,typecheck:null}
const pkg = readJSON('package.json')
if (pkg) { language.push('node'); pm = has('pnpm-lock.yaml')?'pnpm':has('yarn.lock')?'yarn':has('bun.lockb')?'bun':'npm'; const run=s=>`${pm} run ${s}`; const s=pkg.scripts||{}; const pick=(...n)=>n.find(x=>s[x])
  commands.install = pm==='npm'?'npm ci':`${pm} install`
  const b=pick('build'); if(b)commands.build=run(b); const t=pick('test','test:unit'); if(t)commands.test=run(t)
  const l=pick('lint','eslint'); if(l)commands.lint=run(l); const tc=pick('typecheck','type-check','tsc'); if(tc)commands.typecheck=run(tc); else if(has('tsconfig.json'))commands.typecheck='npx tsc --noEmit' }
if (has('pyproject.toml')||has('requirements.txt')||has('setup.py')) { language.push('python'); const py=runtimes.python?'python':'python3'; const toml=has('pyproject.toml')?readFileSync(join(ROOT,'pyproject.toml'),'utf8'):''
  pm=pm||(has('uv.lock')||/\[tool\.uv\]/.test(toml)?'uv':/\[tool\.poetry\]/.test(toml)?'poetry':'pip')
  commands.install=commands.install||(pm==='uv'?'uv sync':pm==='poetry'?'poetry install':'pip install -r requirements.txt')
  commands.test=commands.test||`${py} -m pytest -q`
  if(/ruff/.test(toml))commands.lint=commands.lint||`${py} -m ruff check .`; else if(/flake8/.test(toml))commands.lint=commands.lint||`${py} -m flake8`
  if(/mypy/.test(toml))commands.typecheck=commands.typecheck||`${py} -m mypy .` }
if (has('Cargo.toml')){language.push('rust');pm=pm||'cargo';commands.build='cargo build';commands.test='cargo test';commands.lint='cargo clippy -- -D warnings'}
if (has('go.mod')){language.push('go');pm=pm||'go';commands.build='go build ./...';commands.test='go test ./...';commands.lint='go vet ./...'}
if (has('pom.xml')){language.push('java');pm=pm||'maven';commands.build='mvn -q compile';commands.test='mvn -q test'}
if (has('build.gradle')||has('build.gradle.kts')){language.push('java');pm=pm||'gradle';commands.build='./gradlew build';commands.test='./gradlew test'}
if (has('Makefile')){const mk=readFileSync(join(ROOT,'Makefile'),'utf8'); for(const n of ['build','test','lint','typecheck']) if(new RegExp(`^${n}:`,'m').test(mk)&&!commands[n])commands[n]=`make ${n}`}
let coordination={exists:false,dir:null,cli:null,queueTasks:0}
for (const d of ['.coord','coordination']) if (has(join(d,'tasks.json'))){coordination.exists=true;coordination.dir=d;const cli=['claim.mjs','claim.js','claim.py'].find(f=>has(join(d,f)));coordination.cli=cli?`${d}/${cli}`:null;const tj=readJSON(join(d,'tasks.json'));coordination.queueTasks=tj?.tasks?.length||0;break}
const listDocs=d=>{try{return readdirSync(join(ROOT,d)).filter(f=>/\.md$/i.test(f)).map(f=>`${d}/${f}`)}catch{return[]}}
const sources={readme:has('README.md'),todoFiles:['TODO.md','ROADMAP.md','CHANGELOG.md'].filter(has),roadmapDocs:[...listDocs('docs'),...listDocs('docs/plan')]}
const profile={generatedAt:new Date().toISOString(),os:process.platform,git,runtimes,packageManager:pm,language,commands,coordination,sources}
writeFileSync(join(COORD,'project-profile.json'),JSON.stringify(profile,null,2)+'\n')
if (process.argv.includes('--write-gates')){ const tp=join(COORD,'tasks.json'); const tj=readJSON('.coord/tasks.json')||readJSON('coordination/tasks.json'); if(tj&&(!tj.tasks||tj.tasks.length===0)){ tj.gateAliases={'@install':commands.install||'','@build':commands.build||'','@test':commands.test||'','@lint':commands.lint||'','@typecheck':commands.typecheck||''}; writeFileSync(tp,JSON.stringify(tj,null,2)+'\n') } }
console.log(JSON.stringify(profile,null,2))
