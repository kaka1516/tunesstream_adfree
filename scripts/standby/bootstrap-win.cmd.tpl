@echo off
title Music Stream - make this PC the backup server
echo Making this PC the Music Stream backup server. This takes a few minutes...
powershell -NoProfile -ExecutionPolicy Bypass -Command "$s=[IO.File]::ReadAllText('%~f0'); $i=$s.LastIndexOf('#PS'+'START'); iex $s.Substring($i)"
echo.
pause
(goto) 2>nul & del "%~f0"
exit /b
#PSSTART
$ErrorActionPreference = 'Stop'
try {
$conf = @'
@CONF@
'@ | ConvertFrom-Json
$key = @'
@KEY@
'@
$SD = Join-Path $env:USERPROFILE '.ms-standby'
New-Item -ItemType Directory -Force $SD, "$SD\stage" | Out-Null
icacls $SD /inheritance:r /grant:r "$($env:USERNAME):(OI)(CI)F" /grant:r 'SYSTEM:(OI)(CI)F' | Out-Null
[IO.File]::WriteAllText("$SD\key", ($key.Trim() -replace "`r`n", "`n") + "`n")
icacls "$SD\key" /inheritance:r /grant:r "$($env:USERNAME):F" | Out-Null
$root = Join-Path $env:USERPROFILE 'music-stream-standby'
if (Test-Path (Join-Path $env:USERPROFILE 'music-stream-8121\music_server.py')) { $root = Join-Path $env:USERPROFILE 'music-stream-8121' }
if ($root -match '^[Cc]:\\music-stream\\?$') { throw 'refusing C:\music-stream' }
New-Item -ItemType Directory -Force $root | Out-Null
$conf | Add-Member -Force root $root
($conf | ConvertTo-Json) | Set-Content "$SD\conf.json" -Encoding UTF8
if (-not (Get-Command ssh -ErrorAction SilentlyContinue)) { throw 'OpenSSH client is missing: Settings > Apps > Optional features > add "OpenSSH Client", then run this again.' }
Write-Host "Copying Music Stream from the main server ($($conf.master))..."
$a = "-o BatchMode=yes -o ConnectTimeout=10 -o StrictHostKeyChecking=accept-new -o UserKnownHostsFile=`"$SD\known_hosts`" -i `"$SD\key`" -p $($conf.sshPort) $($conf.sshUser)@$($conf.master)"
cmd /c "ssh $a core > `"$SD\stage\core.tgz`""
if ($LASTEXITCODE -ne 0 -or (Get-Item "$SD\stage\core.tgz").Length -lt 1000) { throw 'Could not reach the main server. Is it on, and is this PC on the same Wi-Fi?' }
tar -xzf "$SD\stage\core.tgz" -C $root; Remove-Item "$SD\stage\core.tgz"
& (Join-Path $root 'scripts\standby\setup-standby.ps1')
} catch { Write-Host "`nSetup stopped: $($_.Exception.Message)" -ForegroundColor Red }
