# Music Stream control script (copied to %LOCALAPPDATA%\MusicStream\ms.ps1 by install.cmd).
#   ms.ps1 start [-Open] | stop | restart | status | open | uninstall
# Only ever touches python processes running THIS install's app\music_server.py.
param([Parameter(Position = 0)][string]$Cmd = 'status', [switch]$Open, [switch]$Quiet)
$ErrorActionPreference = 'Stop'
$Dir = $PSScriptRoot; $App = Join-Path $Dir 'app'; $Srv = Join-Path $App 'music_server.py'
$vpy = Join-Path $Dir 'venv\Scripts\python.exe'
function Say($m) { if (-not $Quiet) { Write-Host $m } }
function Get-Port { $p = 8125; $f = Join-Path $App 'music.env'; if (Test-Path $f) { foreach ($l in Get-Content $f) { if ($l -match '^\s*MUSIC_PORT\s*=\s*(\d+)') { $p = [int]$matches[1] } } }; return $p }
function Get-Mine { @(Get-CimInstance Win32_Process -Filter "Name like 'python%'" | Where-Object { $_.CommandLine -and $_.CommandLine.ToLower().Contains($Srv.ToLower()) }) }
function Test-Health($port) { try { $r = Invoke-WebRequest -UseBasicParsing -TimeoutSec 3 -Uri "http://127.0.0.1:$port/health"; return $r.StatusCode -eq 200 } catch { return $false } }
$port = Get-Port; $url = "http://127.0.0.1:$port/"
switch ($Cmd.ToLower()) {
  'start' {
    if (@(Get-Mine).Count -gt 0 -and (Test-Health $port)) { Say "Already running: $url" }
    else {
      if (-not (Test-Path $vpy)) { throw "Not installed (missing $vpy). Run install.cmd again." }
      $env:PYTHONUNBUFFERED = '1'; $env:PYTHONIOENCODING = 'utf-8'
      Start-Process -FilePath $vpy -ArgumentList "`"$Srv`"" -WorkingDirectory $App -WindowStyle Hidden `
        -RedirectStandardOutput (Join-Path $App 'server.log') -RedirectStandardError (Join-Path $App 'server.err.log') | Out-Null
      $ok = $false; for ($i = 0; $i -lt 60; $i++) { Start-Sleep -Milliseconds 500; if (Test-Health $port) { $ok = $true; break } }
      if (-not $ok) { Say "The server did not answer on $url within 30 s. See $App\server.err.log"; exit 1 }
      Say "Running: $url"
    }
    if ($Open) {
      $uf = Join-Path $App 'users.json'
      if (-not ((Test-Path $uf) -and ((Get-Content $uf -Raw) -match '"role"\s*:\s*"admin"'))) { Start-Process ($url + 'setup') } else { Start-Process $url }
    }
  }
  'stop' {
    $m = @(Get-Mine)
    foreach ($p in $m) { try { Stop-Process -Id $p.ProcessId -Force -ErrorAction Stop } catch {} }
    if ($m.Count) { Say "Stopped Music Stream ($($m.Count) process(es))." } else { Say "Music Stream was not running." }
  }
  'restart' { & $PSCommandPath stop -Quiet; & $PSCommandPath start }
  'status' { if (Test-Health $port) { Say "Running: $url" } else { Say "Not running (port $port)." ; exit 1 } }
  'open' { Start-Process $url }
  'uninstall' {
    & $PSCommandPath stop -Quiet
    $pp = Join-Path $Dir 'public.ps1'; if (Test-Path $pp) { & powershell -NoProfile -ExecutionPolicy Bypass -File $pp off | Out-Null }
    $desk = [Environment]::GetFolderPath('Desktop')
    foreach ($n in 'Music Stream.lnk', 'Stop Music Stream.lnk', 'Make Music Stream public.lnk', 'Stop public link.lnk') { Remove-Item -Force -ErrorAction SilentlyContinue (Join-Path $desk $n) }
    $a = Read-Host "Shortcuts removed and server stopped. Also delete $Dir including your accounts and settings? Type DELETE to confirm"
    if ($a -ceq 'DELETE') { Set-Location $env:TEMP; Remove-Item -Recurse -Force $Dir; Write-Host "Deleted." } else { Write-Host "Folder kept." }
  }
  default { Write-Host "usage: ms.ps1 start [-Open] | stop | restart | status | open | uninstall"; exit 2 }
}
exit 0
