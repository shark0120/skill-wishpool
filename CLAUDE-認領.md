# Skill 許願池 · 給 Claude 認領的圖

站：https://skill-tw.com/（repo：shark0120/skill-wishpool）
這是 **AI skill 許願／聯署**，不是公益。每三天票最高的做成 Claude Code / Codex skill。

語彙只准：許願、聯署、熱門／最新／最多聯署、領先、已實現、水波、AI skill。
不要用兒童教育、動物保護、長照等公益句。

現站 sprite 只用這 10 個：`i-water i-drop i-trend i-clock i-star i-crown i-search i-alert i-link i-theme`
`wave-clip` 一字不改。主視覺／canvas 水面先不動。

已開 PR（10 個 currentColor icon + CTA 水滴微動畫）：
https://github.com/shark0120/skill-wishpool/pull/1

根目錄：`/workspace/skill-tw-icons/`
本機站：`C:\Users\User\Desktop\skill-wishpool\public\index.html`

---

## 認領：現站能直接用

紙底、currentColor、24×24、stroke 1.7。亮／暗主題都靠 currentColor。

| 認領名 | 檔 | 現站用途 |
| --- | --- | --- |
| 水紋品牌 | `svg/static/water.svg` | sprite `i-water`（備用） |
| 許願水滴 | `svg/static/drop.svg` | 「我要許願」＋ sprite `i-drop` |
| 熱門 | `svg/static/trend.svg` | 排序「熱門」 |
| 最新 | `svg/static/clock.svg` | 排序「最新」 |
| 最多聯署 | `svg/static/star.svg` | 排序「最多聯署」 |
| 領先 | `svg/static/crown.svg` | 「目前領先」 |
| 搜尋 | `svg/static/search.svg` | 搜尋框 |
| 警示 | `svg/static/alert.svg` | 錯誤／空態備用 |
| 外連 | `svg/static/link.svg` | GitHub／SKILL.md 外連 |
| 明暗 | `svg/static/theme.svg` | 亮暗切換 |
| 整包 sprite | `sprite.svg` | drop-in，含 `wave-clip` |
| CTA 水滴微動畫 | `svg/animated/drop-anim.svg` | 只給「我要許願」inline，不要塞進 `<use>` |
| 水紋微動畫 | `svg/animated/water-anim.svg` | 第一幀已對齊 `i-water`，可後補 |

預覽：`preview/icon-sheet.html`、`preview/skill-tw-icon-sheet.png`

### 現站還沒掛、但語彙對、可後補

同一套 currentColor：`vote` 附議、`people` 聯署人數、`granted` 已實現、`planned` 本輪、`gallery` 成品、`install` 安裝、`thanks` 感謝、`empty` 空池、`claude`、`codex`、`spark`。
路徑：`svg/static/<name>.svg` 對應 id `i-<name>`。

其他微動畫（不要一次全上）：`svg/animated/` 的 clock、crown、search、theme、spark、vote、empty。

---

## 待命：不要上 24px 現站

暗底金紅發光。32/48 才清楚，24px 光暈會糊。

- `svg/cyber/` 21 個靜態
- `svg/cyber-anim/` 10 個微動畫
- `sprite-cyber.svg`（已含 `wave-clip`）
- 預覽：`preview/cyber-sheet.html`

---

## 練習：不上架、不給現站當 hero

電影靜照，小萱說當練習。

- `showcase/01-wish-pool-night.png` 夜池許願
- `showcase/02-character-light.png` 金光切臉
- `showcase/03-pool-temple.png` 大殿建立鏡

---

## 作廢／不當 hero

字跟假數據烤在圖裡，不能當官網底。06 公益假文案整張不用。

- `showcase/04-cyber-hero.png` 只當 art direction，不上站
- `showcase/05-drop-impact.png` 只當 art direction，不上站
- `showcase/06-cards-rush.png` **整張作廢**（公益句）

---

## Claude 請做／不要做

做：合 PR #1；要加 icon 只用紙底 currentColor；CTA 微動畫保持 inline。
不要：換 cyber 包上 24px 現站；動 `wave-clip`；動 hero canvas／文案；用 01–06 當主視覺；寫公益文案。
