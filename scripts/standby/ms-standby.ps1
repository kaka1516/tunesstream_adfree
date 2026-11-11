# Music Stream failover-20261111: BACKUP (standby) server for Windows.
#   ms-standby.ps1 tick      every minute from the "MusicStreamStandby" scheduled task: 3 checks, 20 s apart
#   ms-standby.ps1 status    print "Main server: OK / Backup: ready"
#   ms-standby.ps1 sync      copy code + data from the main server now
#   ms-standby.ps1 off       switch failover off (stop the backup link, remove the task)
#   ms-standby.ps1 on        switch it back on
#   ms-standby.ps1 takeover  (testing) start the backup link now;  release = stop it
# Settings: %USERPROFILE%\.ms-standby\conf.json (written by setup-standby.cmd). Never prints secrets.
param([string]$cmd = 'status')
$ErrorActionPreference = 'Continue'
$SD = Join-Path $env:USERPROFILE '.ms-standby'
$C = Get-Content (Join-Path $SD 'conf.json') -Raw -ErrorAction SilentlyContinue | ConvertFrom-Json
if (-not $C) { Write-Host 'Backup server is not set up on this PC (no .ms-standby\conf.json). Run setup-standby.cmd first.'; exit 1 }
$ROOT = $C.root; $PORT = [int]$C.port; $PUB = $C.public.TrimEnd('/')
if ($ROOT -match '^[Cc]:\\music-stream\\?$') { Write-Host 'Refusing: C:\music-stream belongs to the other service.'; exit 2 }
$CF = $C.cloudflared; if (-not $CF -or -not (Test-Path $CF)) { $CF = (Get-Command cloudflared -ErrorAction SilentlyContinue).Source }
$KEY = Join-Path $SD 'key'; $KH = Join-Path $SD 'known_hosts'
$STF = Join-Path $SD 'state.json'; $STATUS = Join-Path $SD 'status.json'; $EVL = Join-Path $SD 'events.log'
$CFY = Join-Path $SD 'cf\standby.yml'; $CFPID = Join-Path $SD 'cf.pid'; $CFLOG = Join-Path $SD 'cf.log'
$OFF = Join-Path $SD 'off'
$MARK = Join-Path $ROOT 'standby.on'
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12

function Now { [int64][DateTimeOffset]::UtcNow.ToUnixTimeSeconds() }
function Ev($m) { $l = "$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss') $m"; Add-Content -Path $EVL -Value $l -Encoding UTF8; $script:events += $l }
function LoadState { try { $s = Get-Content $STF -Raw -ErrorAction Stop | ConvertFrom-Json } catch { $s = $null }; if (-not $s) { $s = [pscustomobject]@{} }
  foreach ($k in 'fails','okSince','lastSync','lastCode','masterVer','myVer','lastPub') { if (-not ($s.PSObject.Properties.Name -contains $k)) { $s | Add-Member $k 0 } }; $s }
function SaveState($s) { $s | ConvertTo-Json -Depth 4 | Set-Content -Path "$STF.tmp" -Encoding UTF8; Move-Item -Force "$STF.tmp" $STF }
function Get-Url($u, $t = 6) { try { $r = Invoke-WebRequest -Uri $u -UseBasicParsing -TimeoutSec $t -Headers @{ 'Cache-Control' = 'no-cache' }; return @{ code = [int]$r.StatusCode; body = [string]$r.Content } } catch { $c = 0; try { $c = [int]$_.Exception.Response.StatusCode } catch {}; return @{ code = $c; body = '' } } }
function Ssh-Args { @('-o','BatchMode=yes','-o','ConnectTimeout=8','-o','ServerAliveInterval=10','-o','StrictHostKeyChecking=accept-new','-o',"UserKnownHostsFile=$KH",'-i',$KEY,'-p',"$($C.sshPort)","$($C.sshUser)@$($C.master)") }
function Master-Text($req) { $o = & ssh @(Ssh-Args) $req 2>$null; if ($LASTEXITCODE -ne 0) { return $null }; return ($o -join "`n") }
function Master-File($req, $out) { # binary-safe: cmd redirection, not PowerShell pipes
  $a = (Ssh-Args | ForEach-Object { if ($_ -match '\s') { '"' + $_ + '"' } else { $_ } }) -join ' '
  cmd /c "ssh $a $req > `"$out`" 2>nul"; return ($LASTEXITCODE -eq 0 -and (Test-Path $out) -and (Get-Item $out).Length -gt 0) }
function Master-Status { $t = Master-Text 'status'; if (-not $t) { return $null }; @{ server = ($t -match 'server ok'); tunnel = (([regex]::Match($t, 'tunnel (\w+)')).Groups[1].Value) } }

function Cf-Proc { $p = $null; try { $id = [int](Get-Content $CFPID -ErrorAction Stop) } catch { return $null }
  $p = Get-CimInstance Win32_Process -Filter "ProcessId=$id" -ErrorAction SilentlyContinue
  if ($p -and $p.Name -eq 'cloudflared.exe' -and $p.CommandLine -like '*standby.yml*') { return $p }; return $null }
function Cf-Start { if (Cf-Proc) { return }; if (-not (Test-Path $CFY)) { Ev 'cannot take over: tunnel settings missing (run sync)'; return }
  $p = Start-Process -FilePath $CF -ArgumentList @('tunnel','--no-autoupdate','--metrics','127.0.0.1:20249','--config',"`"$CFY`"",'--logfile',"`"$CFLOG`"",'run') -WindowStyle Hidden -PassThru
  Set-Content $CFPID $p.Id; Ev "BACKUP TAKING OVER the public link (cloudflared pid $($p.Id))" }
function Cf-Stop($why) { $p = Cf-Proc; if ($p) { Stop-Process -Id $p.ProcessId -Force -ErrorAction SilentlyContinue; Ev "backup link stopped: $why" }; Remove-Item $CFPID -ErrorAction SilentlyContinue }

function Server-Pid { $c = Get-NetTCPConnection -LocalPort $PORT -State Listen -ErrorAction SilentlyContinue | Select-Object -First 1; if ($c) { return [int]$c.OwningProcess }; return 0 }
function Server-Restart($why) { # restarts ONLY the python that owns $PORT and runs from this folder; run.ps1 starts it again
  $id = Server-Pid; if (-not $id -or $id -in 11888,16624) { return }
  $p = Get-CimInstance Win32_Process -Filter "ProcessId=$id" -ErrorAction SilentlyContinue
  if ($p -and $p.Name -like 'python*' -and $p.CommandLine -match '(ms_standby|music_server)\.py') { Stop-Process -Id $id -Force -ErrorAction SilentlyContinue; Ev "backup server restarted: $why" } }
function Is-Standby { try { return ((Invoke-WebRequest "http://127.0.0.1:$PORT/api/server-role" -UseBasicParsing -TimeoutSec 4).Content -match 'standby') } catch { return $false } }
function Loop-Restart($why) { # restart the 8121 run.ps1 loop (PowerShell reads run.ps1 only when it starts)
  Get-CimInstance Win32_Process -Filter "name='powershell.exe'" -ErrorAction SilentlyContinue | Where-Object { $_.CommandLine -like "*$ROOT\run.ps1*" } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }
  Server-Restart $why; Start-Sleep 2
  Start-Process powershell.exe -ArgumentList @('-NoProfile','-WindowStyle','Hidden','-ExecutionPolicy','Bypass','-File',"`"$ROOT\run.ps1`"") -WindowStyle Hidden }
function Server-Ensure { $id = Server-Pid
  if ($id) { if ((Test-Path $MARK) -and -not (Is-Standby)) { $p = Get-CimInstance Win32_Process -Filter "ProcessId=$id" -ErrorAction SilentlyContinue
      if ($p -and $p.CommandLine -match 'music_server\.py') { Loop-Restart 'was running in normal mode' } }; return }
  $loop = Get-CimInstance Win32_Process -Filter "name='powershell.exe'" -ErrorAction SilentlyContinue | Where-Object { $_.CommandLine -like "*$ROOT\run.ps1*" }
  if (-not $loop) { Start-Process powershell.exe -ArgumentList @('-NoProfile','-WindowStyle','Hidden','-ExecutionPolicy','Bypass','-File',"`"$ROOT\run.ps1`"") -WindowStyle Hidden; Ev 'backup server started' } }

function Atomic-Copy($src, $dst) { $tmp = "$dst.sbtmp"; Copy-Item -Force $src $tmp; if (Test-Path $dst) { Move-Item -Force $tmp $dst } else { Rename-Item $tmp (Split-Path $dst -Leaf) } }
function Sync-Data { $tmp = Join-Path $SD 'stage\data'; Remove-Item -Recurse -Force $tmp -ErrorAction SilentlyContinue; New-Item -ItemType Directory -Force $tmp | Out-Null
  $f = Join-Path $SD 'stage\data.tgz'; if (-not (Master-File 'data' $f)) { return $false }
  tar -xzf $f -C $tmp 2>$null; if ($LASTEXITCODE -ne 0) { return $false }
  try { $null = Get-Content (Join-Path $tmp 'users.json') -Raw | ConvertFrom-Json } catch { Ev 'data copy skipped: users.json from main did not parse'; return $false }
  foreach ($x in 'users.json','sessions.json') { if (Test-Path "$tmp\$x") { Atomic-Copy "$tmp\$x" "$ROOT\$x" } }
  New-Item -ItemType Directory -Force "$ROOT\user_data","$ROOT\lcache\plays" | Out-Null
  $keep = @{}; Get-ChildItem "$tmp\user_data" -File -ErrorAction SilentlyContinue | ForEach-Object { $keep[$_.Name] = 1; Atomic-Copy $_.FullName "$ROOT\user_data\$($_.Name)" }
  Get-ChildItem "$ROOT\user_data" -File -Filter *.json -ErrorAction SilentlyContinue | Where-Object { -not $keep[$_.Name] } | Remove-Item -Force -ErrorAction SilentlyContinue
  if (Test-Path "$tmp\lcache\plays\plays.json") { Atomic-Copy "$tmp\lcache\plays\plays.json" "$ROOT\lcache\plays\plays.json" }
  Remove-Item -Recurse -Force $tmp, $f -ErrorAction SilentlyContinue; return $true }
function Sync-Creds { $tmp = Join-Path $SD 'cf'; New-Item -ItemType Directory -Force $tmp | Out-Null
  $f = Join-Path $SD 'stage\creds.tgz'; if (-not (Master-File 'creds' $f)) { return $false }
  tar -xzf $f -C $tmp 2>$null; Remove-Item -Force $f
  $y = Get-Content "$tmp\config.yml" -Raw; Remove-Item "$tmp\config.yml" -Force
  $tid = ([regex]::Match($y, '(?m)^tunnel:\s*"?([0-9a-f-]+)')).Groups[1].Value; $hn = ([regex]::Match($y, '(?m)hostname:\s*"?([^"\s]+)')).Groups[1].Value
  if (-not $tid -or -not (Test-Path "$tmp\$tid.json")) { return $false }
  @("tunnel: $tid", "credentials-file: $tmp\$tid.json", 'protocol: http2', 'ingress:', "  - hostname: $hn", "    service: http://127.0.0.1:$PORT", '  - service: http_status:404') | Set-Content -Path $CFY -Encoding ASCII
  icacls $tmp /inheritance:r /grant:r "$($env:USERNAME):(OI)(CI)F" /grant:r 'SYSTEM:(OI)(CI)F' | Out-Null; return $true }
function Sync-Code([switch]$force) { $v = Master-Text 'version'; if (-not $v) { return $false }
  $have = @{}; $vf = Join-Path $SD 'ver.txt'; if (Test-Path $vf) { Get-Content $vf | ForEach-Object { $a = $_ -split ' '; if ($a.Count -ge 2) { $have[$a[0]] = $a[1] } } }
  $restart = $false; $new = @()
  foreach ($line in ($v -split "`n")) { $a = $line.Trim() -split ' '; if ($a.Count -lt 2) { continue }; $b = $a[0]; $h = $a[1]; $new += "$b $h"
    if ($b -eq 'app') { $script:S.masterVer = $h; continue }
    if (-not $force -and $have[$b] -eq $h) { continue }
    $f = Join-Path $SD "stage\$b.tgz"; $tmp = Join-Path $SD "stage\$b"; Remove-Item -Recurse -Force $tmp -ErrorAction SilentlyContinue; New-Item -ItemType Directory -Force $tmp | Out-Null
    if (-not (Master-File $b $f)) { Ev "code copy failed: $b"; return $false }
    tar -xzf $f -C $tmp 2>$null; if ($LASTEXITCODE -ne 0) { Ev "code unpack failed: $b"; return $false }
    if ($b -eq 'core' -and -not (Test-Path "$tmp\music_server.py")) { Ev 'code copy incomplete'; return $false }
    $pyh = { (Get-ChildItem $ROOT -Filter *.py -File -ErrorAction SilentlyContinue | Sort-Object Name | Get-FileHash -Algorithm MD5 | ForEach-Object Hash) -join ',' }
    $before = & $pyh
    robocopy $tmp $ROOT /E /NFL /NDL /NJH /NJS /NP /R:1 /W:1 | Out-Null
    Remove-Item -Recurse -Force $tmp, $f -ErrorAction SilentlyContinue
    if ($b -eq 'core' -and (& $pyh) -ne $before) { $restart = $true }; Ev "code updated from main: $b" }
  $new | Set-Content $vf -Encoding ASCII
  $script:S.myVer = $script:S.masterVer
  if ($restart -and -not (Cf-Proc)) { Server-Restart 'new code from main' }
  return $true }

function Write-Status($lan, $pubOk) { $act = [bool](Cf-Proc)
  $old = @(); try { $old = @((Get-Content $STATUS -Raw -ErrorAction Stop | ConvertFrom-Json).events) } catch {}
  $ev = @($old + $script:events | Where-Object { $_ } | Select-Object -Last 20)
  $o = [ordered]@{ ts = (Now); master = $C.master; master_ok = $lan; active = $act; off = (Test-Path $OFF); public = $PUB; public_ok = $pubOk
    last_sync = $S.lastSync; master_ver = $S.masterVer; my_ver = $S.myVer; events = $ev }
  ($o | ConvertTo-Json -Depth 4) | Set-Content "$STATUS.tmp" -Encoding UTF8; Move-Item -Force "$STATUS.tmp" $STATUS }

function Check-Once { $script:events = @()
  if (Test-Path $OFF) { if (Cf-Proc) { Cf-Stop 'switched off' }; Write-Status $null $null; return }
  Server-Ensure
  $lan = ((Get-Url "http://$($C.master):$($C.masterPort)/health" 4).body -eq 'ok')
  $pubOk = $null
  if (-not (Cf-Proc)) {
    $pubOk = ((Get-Url "$PUB/health" 8).body -eq 'ok')
    if ($pubOk) { $S.fails = 0 } else { $S.fails = [int]$S.fails + 1
      if ($S.fails -ge 3) { $ms = if ($lan) { Master-Status } else { $null }
        if ($ms -and $ms.server -and $ms.tunnel -eq 'ready') { if ($S.fails -eq 3) { Ev 'public link failing but the main tunnel is up: not taking over (internet problem?)' } }
        else { Cf-Start; $S.okSince = 0 } } }
  } else {
    $ms = if ($lan) { Master-Status } else { $null }
    if ($lan -and $ms -and $ms.server -and $ms.tunnel -in 'ready','running') { if (-not $S.okSince) { $S.okSince = Now; Ev 'main server is back; handing over in 60 s' }
      elseif ((Now) - [int64]$S.okSince -ge 60) { Cf-Stop 'main server healthy for 60 s'; $S.fails = 0; $S.okSince = 0 } }
    else { $S.okSince = 0 }
  }
  if (-not (Cf-Proc) -and $lan) {
    if ((Now) - [int64]$S.lastCode -ge 1800 -or -not $S.myVer) { if (Sync-Code) { $S.lastCode = Now } }
    if ((Now) - [int64]$S.lastSync -ge 290) { if (Sync-Data) { $S.lastSync = Now } else { Ev 'data copy from main failed' } }
    if (-not (Test-Path $CFY)) { if (Sync-Creds) { Ev 'tunnel settings copied' } } }
  Write-Status $lan $pubOk; SaveState $S }

New-Item -ItemType Directory -Force (Join-Path $SD 'stage') | Out-Null
$S = LoadState; $events = @()
switch ($cmd) {
  'tick' { $mx = New-Object Threading.Mutex($false, 'Global\MusicStreamStandbyTick'); if (-not $mx.WaitOne(0)) { exit 0 }
           try { for ($i = 0; $i -lt 3; $i++) { Check-Once; if ($i -lt 2) { Start-Sleep -Seconds 20 } } } finally { $mx.ReleaseMutex() } }
  'sync' { $events = @(); $a = Sync-Code -force:($args -contains '-force'); $b = Sync-Data; $c2 = Sync-Creds; if ($b) { $S.lastSync = Now }; if ($a) { $S.lastCode = Now }
           SaveState $S; Write-Status $null $null; Write-Host "code: $(if($a){'OK'}else{'FAILED'})  data: $(if($b){'OK'}else{'FAILED'})  tunnel settings: $(if($c2){'OK'}else{'FAILED'})" }
  'off'  { New-Item -ItemType File -Force $OFF | Out-Null; Cf-Stop 'switched off by you'; Unregister-ScheduledTask -TaskName 'MusicStreamStandby' -Confirm:$false -ErrorAction SilentlyContinue
           Remove-Item $MARK -ErrorAction SilentlyContinue; Server-Restart 'standby off (normal mode)'; Write-Status $null $null
           Write-Host 'Failover is OFF. This PC will not take over the link. (Turn on again: setup-standby.cmd or ms-standby.ps1 on)' }
  'on'   { Remove-Item $OFF -ErrorAction SilentlyContinue; New-Item -ItemType File -Force $MARK | Out-Null; & (Join-Path $PSScriptRoot 'install-task.ps1'); Server-Restart 'standby on'; Write-Host 'Failover is ON.' }
  'takeover' { Cf-Start; Write-Status $null $null }
  'release'  { Cf-Stop 'released by hand'; Write-Status $null $null }
  default {
    $lan = ((Get-Url "http://$($C.master):$($C.masterPort)/health" 4).body -eq 'ok')
    $ms = if ($lan) { Master-Status } else { $null }
    $who = (Get-Url "$PUB/api/server-role" 8)
    $onb = ($who.code -eq 200 -and $who.body -match '"standby"')
    $age = if ($S.lastSync) { [int](((Now) - [int64]$S.lastSync) / 60) } else { -1 }
    Write-Host ''
    Write-Host ("Main server : " + $(if ($lan -and $ms -and $ms.tunnel -in 'ready','running') { 'OK' } elseif ($lan) { "UP, but its link is $(if($ms){$ms.tunnel}else{'unknown'})" } else { 'DOWN (not answering on home Wi-Fi)' }))
    Write-Host ("Backup      : " + $(if (Test-Path $OFF) { 'OFF (switched off)' } elseif (Cf-Proc) { 'SERVING the link now' } elseif (Is-Standby) { 'ready' } elseif (Server-Pid) { 'NOT ready (server is running in normal mode; it fixes itself within a minute)' } else { 'NOT ready (backup server not running)' }))
    Write-Host ("Link now on : " + $(if ($who.code -eq 0) { 'nobody (link down)' } elseif ($onb) { 'BACKUP' } else { 'main server' }))
    Write-Host ("Last copy   : " + $(if ($age -ge 0) { "$age min ago" } else { 'never' }))
    Write-Host ("Versions    : main $($S.masterVer) / backup $($S.myVer)")
    Write-Host "Details     : http://127.0.0.1:$PORT/standby"
  }
}
