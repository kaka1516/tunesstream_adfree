# failover-20261111: makes THIS Windows PC the backup server. Called by setup-standby.cmd (from ms-standby-pair on the
# main phone) after it has copied the code. Safe to run again. Never touches port 8120, C:\music-stream or other tasks.
$ErrorActionPreference = 'Continue'
$ROOT = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
$SD = Join-Path $env:USERPROFILE '.ms-standby'
$cf = Join-Path $SD 'conf.json'; $C = Get-Content $cf -Raw | ConvertFrom-Json
if ($ROOT -match '^[Cc]:\\music-stream\\?$') { throw 'Refusing to use C:\music-stream (other service).' }
function Step($m) { Write-Host "`n== $m" -ForegroundColor Cyan }
function HaveCmd($c) { [bool](Get-Command $c -ErrorAction SilentlyContinue) }
$env:Path = [Environment]::GetEnvironmentVariable('Path','Machine') + ';' + [Environment]::GetEnvironmentVariable('Path','User')

Step '1/6 Programs (Python, yt-dlp, cloudflared)'
$needPy = -not (HaveCmd 'python'); if (-not $needPy) { python -c "import yt_dlp" 2>$null; $needPy = ($LASTEXITCODE -ne 0) -and -not (Test-Path "$ROOT\.venv\Scripts\python.exe") }
if ($needPy -or -not (Test-Path "$ROOT\music.env")) { & (Join-Path $ROOT 'install.ps1') -Yes } else { Write-Host 'already installed' }
$cfx = (Get-Command cloudflared -ErrorAction SilentlyContinue).Source
if (-not $cfx -and (Test-Path 'C:\Program Files (x86)\cloudflared\cloudflared.exe')) { $cfx = 'C:\Program Files (x86)\cloudflared\cloudflared.exe' }
if (-not $cfx) { winget install -e --id Cloudflare.cloudflared --accept-package-agreements --accept-source-agreements | Out-Null
  $env:Path = [Environment]::GetEnvironmentVariable('Path','Machine') + ';' + [Environment]::GetEnvironmentVariable('Path','User'); $cfx = (Get-Command cloudflared -ErrorAction SilentlyContinue).Source
  if (-not $cfx -and (Test-Path 'C:\Program Files (x86)\cloudflared\cloudflared.exe')) { $cfx = 'C:\Program Files (x86)\cloudflared\cloudflared.exe' } }
if (-not $cfx) { throw 'cloudflared could not be installed. Install it from https://github.com/cloudflare/cloudflared/releases and run this again.' }
$C | Add-Member -Force cloudflared $cfx; $C | Add-Member -Force root $ROOT; ($C | ConvertTo-Json) | Set-Content $cf -Encoding UTF8

Step '2/6 Server launcher (run.ps1)'
$run = Join-Path $ROOT 'run.ps1'
if (-not (Test-Path $run)) {
@'
$ErrorActionPreference = 'Continue'
$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $Root
$py = if (Test-Path "$Root\.venv\Scripts\python.exe") { "$Root\.venv\Scripts\python.exe" } else { 'python' }
while ($true) {
  $entry = if (Test-Path (Join-Path $Root 'standby.on')) { 'ms_standby.py' } else { 'music_server.py' }  # failover-20261111
  "$(Get-Date -Format o) start $entry" | Out-File -Append run.log
  & $py $entry *>> server.log
  "$(Get-Date -Format o) exit $LASTEXITCODE" | Out-File -Append run.log
  Start-Sleep -Seconds 5
}
'@ | Set-Content $run -Encoding ASCII; Write-Host 'created run.ps1'
} elseif ((Get-Content $run -Raw) -notmatch 'standby\.on') {
  Copy-Item $run "$run.bak-standby-$(Get-Date -Format yyyyMMdd)" -Force
  $t = Get-Content $run -Raw
  $re = [regex]'(?m)^(\s*)(.*python[^\r\n]*?)\bmusic_server\.py\b'; $t = $re.Replace($t, [Text.RegularExpressions.MatchEvaluator]{ param($m) $m.Groups[1].Value + '$entry = if (Test-Path (Join-Path $PSScriptRoot ''standby.on'')) { ''ms_standby.py'' } else { ''music_server.py'' }  # failover-20261111' + "`r`n" + $m.Groups[1].Value + $m.Groups[2].Value + '$entry' }, 1)
  Set-Content $run $t -Encoding ASCII; Write-Host 'run.ps1 now starts ms_standby.py while standby.on exists (backup kept)'
} else { Write-Host 'already set' }
New-Item -ItemType File -Force (Join-Path $ROOT 'standby.on') | Out-Null
Remove-Item (Join-Path $SD 'off') -ErrorAction SilentlyContinue

Step '3/6 Copy code, accounts, likes, playlists and link settings from the main server'
& (Join-Path $PSScriptRoot 'ms-standby.ps1') sync -force

Step '4/6 Scheduled task (checks every 20 s)'
& (Join-Path $PSScriptRoot 'install-task.ps1')

Step '5/6 Start the backup server'
# PowerShell reads run.ps1 once when it starts, so an already-running loop must be restarted to pick up the change.
$isStandby = $false; try { $isStandby = ((Invoke-WebRequest "http://127.0.0.1:$($C.port)/api/server-role" -UseBasicParsing -TimeoutSec 4).Content -match 'standby') } catch {}
if (-not $isStandby) {
  Get-CimInstance Win32_Process -Filter "name='powershell.exe'" | Where-Object { $_.CommandLine -like "*$ROOT\run.ps1*" } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }
  $own = Get-NetTCPConnection -LocalPort ([int]$C.port) -State Listen -ErrorAction SilentlyContinue | Select-Object -First 1
  if ($own -and $own.OwningProcess -notin 11888,16624) { $p = Get-CimInstance Win32_Process -Filter "ProcessId=$($own.OwningProcess)"
    if ($p.Name -like 'python*' -and $p.CommandLine -match '(music_server|ms_standby)\.py') { Stop-Process -Id $own.OwningProcess -Force; Write-Host 'restarting it in backup mode' } }
  Start-Sleep 2
  Start-Process powershell.exe -ArgumentList @('-NoProfile','-WindowStyle','Hidden','-ExecutionPolicy','Bypass','-File',"`"$run`"") -WindowStyle Hidden }
$ok = $false; for ($i = 0; $i -lt 60 -and -not $ok; $i++) { Start-Sleep 3; try { $ok = ((Invoke-WebRequest "http://127.0.0.1:$($C.port)/api/server-role" -UseBasicParsing -TimeoutSec 4).Content -match 'standby') } catch {} }
Write-Host $(if ($ok) { 'backup server is up' } else { 'backup server did not answer yet (it keeps trying)' })

Step '6/6 Desktop shortcuts'
$dk = [Environment]::GetFolderPath('Desktop')
"@echo off`r`npowershell -NoProfile -ExecutionPolicy Bypass -File `"$PSScriptRoot\ms-standby.ps1`" status`r`npause" | Set-Content (Join-Path $dk 'Music Stream backup - status.cmd') -Encoding ASCII
"@echo off`r`npowershell -NoProfile -ExecutionPolicy Bypass -File `"$PSScriptRoot\ms-standby.ps1`" off`r`npause" | Set-Content (Join-Path $dk 'Music Stream backup - turn off.cmd') -Encoding ASCII
"@echo off`r`npowershell -NoProfile -ExecutionPolicy Bypass -File `"$PSScriptRoot\ms-standby.ps1`" on`r`npause" | Set-Content (Join-Path $ROOT 'standby-on.cmd') -Encoding ASCII
& (Join-Path $PSScriptRoot 'ms-standby.ps1') status
Write-Host "`nDone. This PC is now the backup. Status any time: double-click 'Music Stream backup - status' on the desktop." -ForegroundColor Green
