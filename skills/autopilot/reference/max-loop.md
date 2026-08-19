> **這一份是薄膠水層。** 它原本指向作者自己另一支叫 `max` 的 skill,那一支沒有
> 一起發佈。沒有那支也能用 autopilot ——「跑到底」時把下面的規則當成獨立作法讀:
> 每輪做完不停下來問、開幾個乾淨脈絡的懷疑者去打自己的改動、連續兩輪確實無新可做才停。

MODULE: run-until-dry — 跑到底迴圈(指向全域 max skill 的薄膠水層)

# 跑到底迴圈(指向 max,單一真相源)

> **對抗式驗證(N 個懷疑者視角)、完整性批判、token 縮放表、busywork 禁令、收斂判準與安全邊界,一律以全域 `max` skill(`/max`)為準。** 本檔不再複製那套內容——之前這裡有一份完整副本,與 max 重複且會各自漂移,已收斂;要那些細節就載入 max。

以下只保留 **autopilot 特有、max 沒有** 的接續膠水:

## 1. 輪與 dry 的定義

- **一輪** = SKILL.md §2 主迴圈跑完一次 = 一個已驗證切片落地並提交,**或**確實補了 ≥1 個新 ai 任務。輪不綁時鐘,綁「一個可驗證的產出」。
- **dry round(空輪)** = 該輪**同時**:(a) `$CLAIM next` 無可領 ai 任務;(b) 完整性批判找不到可轉成任務的實質缺口;(c) 補任務也拆不出新的原子 ai 任務(剩全 decision/authorize)。
- **主停止線**:`dryRounds >= 2`(連續 2 輪 dry)→ 停,寫 SKILL.md §5 交接。非空輪 dryRounds 歸零。

## 2. 持久狀態(跨續派存活)

用 `templates/next-round.mjs`(裝進專案後為 `scripts/autopilot/next-round.mjs`):

```bash
node scripts/autopilot/next-round.mjs record --agent $AGENT --task <id|none> --commit <sha|none> --evidence "..." --refilled "id1,id2"
node scripts/autopilot/next-round.mjs decide --agent $AGENT    # 印 CONTINUE 或 STOP
```

沒有 helper 也行:自己維護 `loop-state.json` 的 `round`/`dryRounds`/`lastRound`/`pendingUser`,照 §1 定義加減。

## 3. 自動接續階梯(能同輪就同輪)

1. **同輪續跑(預設)**:`decide` 印 CONTINUE 且 context 用量 < ~70% → 直接回主迴圈 LOCATE,不輸出「要繼續嗎」。
2. **續派子代理**:context > ~70% → 先寫交接 + 更新 loop-state → spawn 一個 fresh-context 子代理沿用同一 `$AGENT` 從 LOCATE 接續。
3. **停 + 交接**:兩者都不行,或 `decide` 印 STOP。

## 4. 排程喚醒(過夜跑)= 需使用者事先明確同意

註冊 scheduled task / cron 把自己叫醒屬於**持續性設定變更**,不在「開跑即授權」範圍內:

- 只有使用者**當次明確要求**「過夜跑 / 排程接著跑」才可建立排程;預設**不建**。
- 建立時一併告知使用者排程名稱與移除方式,收尾交接提醒移除。
- 每次被喚醒開頭重讀授權邊界;任何需授權動作(push/部署/花錢/上線)仍永遠累積留給使用者。

## 5. 授權邊界

「燒好燒滿」給的是**強度**,不是**權限**。SKILL.md §2 鐵律與授權紅線在本模式下一條不放寬;max 的 Safety boundaries 同義,以兩者較嚴者為準。
