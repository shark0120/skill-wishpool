# AI_CAMPAIGN

> /ai 戰役主狀態。禁止寫 secrets。

```yaml
status: idle          # idle | running | finalizing | stopped
command: ""           # e.g. /ai 10 mode=mixed
hours: 0
mode: mixed           # burn | skills | mixed
site_focus: multi
agent_id: ai-xxxx
started_at: ""
deadline_hint: ""     # started + hours
updated_at: ""
hour_index: 0         # 1..hours
round: 0
max_rounds: 0
dry_rounds: 0
dry_stop_at: 3
skills_done: 0
skills_target: 0
slices_done: 0
slices_target: 0
last_compress_round: 0
last_ship: ""
parked: []
blocked: []
next_action: ""
```

## 本戰役一句話目標



## 禁區（每輪重讀）

- payment / billing / ledger / balance / auth / ban / schema
- secrets / nginx / 全量 deploy.py / push 遠端

## 續跑

1. 讀 `HANDOFF.md` + `COMPRESS.md` + 本檔
2. `/ai resume` 或口語「接著燒」
