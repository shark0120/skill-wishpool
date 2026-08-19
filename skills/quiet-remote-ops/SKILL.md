---
name: quiet-remote-ops
description: 遠端操作使用者仍在使用中的 Windows 電腦時,不彈視窗、不搶焦點、不打斷對方工作。當使用者說「不要亂跳視窗」「那台我在用」「不要打擾我工作」「安靜一點動」「不要搶滑鼠」「怕搞亂」「那台是工作機」「背景做就好」,或任何要透過 SSH/遠端對「有人正在使用」的機器做安裝、啟動服務、改設定時使用。特別針對「透過 SSH 操作一台有人正在使用的工作站」這個情境。
---

# 安靜遠端操作

在別人正在用的電腦上做事。**預設是不可見**:對方不應該因為你在工作而看到任何視窗、閃爍、焦點跳動或音訊裝置被搶走。

## 核心原則

**沒有把握不可見的操作,就先問。** 彈一個視窗打斷對方開會或錄音,比慢五分鐘嚴重得多。

## 第一步:先看有沒有人在用

動任何東西之前先查,不要假設沒人。

```powershell
# 有沒有互動式登入工作階段
query user 2>$null
# 有沒有正在跑的前景程式(遠端桌面、會議、錄音、剪輯)
Get-Process | Where-Object { $_.MainWindowTitle } |
  Select-Object Name, MainWindowTitle
```

看到 `anydesk`、`teamviewer`、`zoom`、`teams`、`obs`、`audacity`、`剪輯/DAW` 這類程式在跑,或有 `Active` 狀態的工作階段 → **停下來,先問使用者現在方不方便**。

## 安全的執行方式

### 要在背景跑長時間工作 → 用排程工作,不要用 Start-Process

Windows 的 sshd **會在連線結束時殺掉整個子行程樹**。用 `Start-Process` 啟動的東西 SSH 一斷就死,而且如果沒加 `-WindowStyle Hidden` 還會閃視窗。

```powershell
# 對:排程工作以 SYSTEM 身分跑在 session 0,對方完全看不到
$wrapper = 'C:\ProgramData\my-task.ps1'
Set-Content -Path $wrapper -Value @(
  '& powershell -NoProfile -ExecutionPolicy Bypass -File C:\path\to\work.ps1 *> C:\ProgramData\my-task.log'
) -Encoding ascii
schtasks /create /tn MyTask /tr "powershell.exe -NoProfile -ExecutionPolicy Bypass -File $wrapper" `
         /sc once /st 00:00 /ru SYSTEM /rl highest /f
schtasks /run /tn MyTask
```

用完一定要 `schtasks /delete /tn MyTask /f`,不要留在對方機器上。

**代價要知道**:SYSTEM 跑在 session 0,**拿不到音訊裝置、拿不到對方的桌面**。所以它適合下載、安裝、檔案處理;**不適合**任何需要麥克風、喇叭或顯示的東西。那些必須由對方自己啟動。

### 要截圖看網頁 → 無頭瀏覽器,不要開瀏覽器視窗

```powershell
& "$env:ProgramFiles\Google\Chrome\Application\chrome.exe" `
  --headless=new --disable-gpu --hide-scrollbars `
  --user-data-dir=C:\ProgramData\headless-profile `
  --window-size=1600,1100 --virtual-time-budget=20000 `
  --screenshot=C:\ProgramData\shot.png "http://127.0.0.1:PORT"
```

`--headless=new` 不會出現在螢幕上也不會搶焦點。`--user-data-dir` 指到獨立目錄,避免動到對方正在用的瀏覽器設定檔。再 `scp` 回來看。

同樣方式可以用 `--dump-dom` 取得渲染後的 DOM,不用開 DevTools。

### 要裝軟體 → 靜默安裝

```powershell
msiexec /i "installer.msi" /quiet /norestart      # MSI
setup.exe /S                                       # NSIS
setup.exe /VERYSILENT /NORESTART                   # Inno Setup
```

`/quiet` 沒加的話 MSI 會在對方畫面上跳出安裝精靈。

### 要跑指令 → 隱藏視窗

```powershell
Start-Process -FilePath $exe -ArgumentList $args -WindowStyle Hidden -Wait
```

## 絕對不要做的事

- **不要開 GUI 程式到對方的互動工作階段**(`schtasks /ru <使用者>` 加 `/it`、`psexec -i`、`Invoke-WmiMethod Win32_Process Create` 指到 session 1)
- **不要搶焦點**:任何會 `SetForegroundWindow` 的東西
- **不要重開機、不要登出、不要鎖定螢幕**
- **不要動音訊裝置預設值**——對方可能正在通話或錄音
- **不要 kill 有視窗的行程**,先看 `MainWindowTitle` 確認不是對方在用的
- **不要改桌布、解析度、主題、電源設定**
- **不要在對方桌面根目錄丟檔案**,用 `C:\ProgramData\` 或 `%TEMP%`

## 需要先問過才做

- 任何會出現在螢幕上的東西
- 佔用麥克風、喇叭、攝影機
- 佔用大量 CPU/GPU(對方可能正在算圖或開會)
- 大檔下載(可能吃掉對方的頻寬)
- 重啟對方正在用的服務或程式

問法要具體:「我要裝 X,過程全程隱藏不會跳視窗,但會下載 3 GB 吃頻寬,現在方便嗎?」

## 收尾檢查

做完一定要:

1. 刪掉臨時排程工作 `schtasks /delete /tn <name> /f`
2. 停掉自己起的、對方用不到的服務(尤其是佔埠的)
3. 清掉 `C:\ProgramData\` 下的臨時 log、profile、截圖
4. 如果建了捷徑或改了設定,明確告訴對方改了什麼、在哪裡、怎麼還原
5. 回報時說清楚「哪些是你自己要動手做的」——例如需要音訊裝置的程式只能由對方啟動

## 回報格式

做完後直說三件事:

- **對方看得到的變化**:桌面多了什麼、哪個設定變了
- **完全在背景、對方看不到的**:裝了什麼、下載了多少
- **對方需要自己做的**:什麼必須由他親自啟動,為什麼

不要只說「完成了」。對方要能自己驗證你沒有弄亂他的機器。
