# Music Stream - make your install reachable from the internet (Windows).
#   public.ps1                 menu (A = instant temporary link, B = permanent own address)
#   public.ps1 quick [-AutoStart] [-NoOpen]   A: instant link, no account (changes when restarted)
#   public.ps1 permanent [-Hostname music.example.com] [-TunnelName music-stream] [-DryRun]   B: your own address
#   public.ps1 status | off
# Private files live in %LOCALAPPDATA%\MusicStream\public and %USERPROFILE%\.cloudflared (never in the repo).
param([Parameter(Position = 0)][string]$Cmd = 'menu', [string]$Dir = (Join-Path $env:LOCALAPPDATA 'MusicStream'),
      [string]$Hostname = '', [string]$TunnelName = 'music-stream', [switch]$AutoStart, [switch]$NoOpen, [switch]$DryRun, [switch]$Yes)
$ErrorActionPreference = 'Stop'; $ProgressPreference = 'SilentlyContinue'
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
$App = Join-Path $Dir 'app'; $Pub = Join-Path $Dir 'public'; $Cf = Join-Path $Pub 'cloudflared.exe'
$LinkFile = Join-Path $Dir 'PUBLIC LINK.txt'; $Cfg = Join-Path $Pub 'config.yml'; $Mode = Join-Path $Pub 'mode.txt'
$TaskName = 'Music Stream public link'   # its own task; never the other "MusicStream" task
function Say($m, $c = 'White') { Write-Host $m -ForegroundColor $c }
function Fail($m) { Say ""; Say $m 'Red'; exit 1 }
function Get-Port { $p = 8125; $f = Join-Path $App 'music.env'; if (Test-Path $f) { foreach ($l in Get-Content $f) { if ($l -match '^\s*MUSIC_PORT\s*=\s*(\d+)') { $p = [int]$matches[1] } } }; return $p }
function Get-EnvVal($k) { $f = Join-Path $App 'music.env'; if (Test-Path $f) { foreach ($l in Get-Content $f) { if ($l -match "^\s*$k\s*=\s*(.*)$") { return $matches[1].Trim() } } }; return '' }
function Get-Mine { @(Get-CimInstance Win32_Process -Filter "Name = 'cloudflared.exe'" | Where-Object { $_.CommandLine -and $_.CommandLine.ToLower().Contains($Pub.ToLower()) }) }
function Test-Health($port) { try { return (Invoke-WebRequest -UseBasicParsing -TimeoutSec 3 -Uri "http://127.0.0.1:$port/health").StatusCode -eq 200 } catch { return $false } }

function Assert-Safe {
  if (-not (Test-Path (Join-Path $App 'music_server.py'))) { Fail "Music Stream is not installed yet. Double-click install.cmd first, then try again." }
  $uf = Join-Path $App 'users.json'
  if (-not ((Test-Path $uf) -and ((Get-Content $uf -Raw) -match '"role"\s*:\s*"admin"'))) {
    Fail "Not safe yet: there is no admin account.`nOpen http://127.0.0.1:$(Get-Port)/setup on THIS computer, create the admin, then run this again." }
  if ((Get-EnvVal 'MUSIC_OPEN') -match '^(1|true|yes|on)$') {
    Fail "Not safe: MUSIC_OPEN is on in $App\music.env (anyone could use it without logging in).`nChange it to MUSIC_OPEN=0, then run this again." }
  $port = Get-Port
  if (-not (Test-Health $port)) {
    Say "Starting Music Stream first..."; & powershell -NoProfile -ExecutionPolicy Bypass -File (Join-Path $Dir 'ms.ps1') start | Out-Null
    if (-not (Test-Health $port)) { Fail "Music Stream did not start. Double-click the 'Music Stream' shortcut, then try again." } }
  return $port
}
function Get-Cloudflared {
  New-Item -ItemType Directory -Force -Path $Pub | Out-Null
  if (Test-Path $Cf) { return }
  $g = Get-Command cloudflared -ErrorAction SilentlyContinue
  if ($g) { Copy-Item $g.Source $Cf; return }
  Say "Downloading cloudflared (Cloudflare's free tunnel program, about 60 MB)..."
  $arch = if ($env:PROCESSOR_ARCHITECTURE -eq 'ARM64') { 'arm64' } elseif ([Environment]::Is64BitOperatingSystem) { 'amd64' } else { '386' }
  $u = "https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-windows-$arch.exe"
  if ($DryRun) { Say "[dry-run] download $u -> $Cf"; return }
  & curl.exe -fsSL --retry 3 -o $Cf $u; if ($LASTEXITCODE -ne 0 -or -not (Test-Path $Cf)) { Fail "Could not download cloudflared. Check the internet connection and try again." }
}
function Stop-Mine { foreach ($p in Get-Mine) { try { Stop-Process -Id $p.ProcessId -Force; Wait-Process -Id $p.ProcessId -Timeout 10 -ErrorAction SilentlyContinue } catch {} } }
function Set-Task($argLine) {
  $a = New-ScheduledTaskAction -Execute 'powershell.exe' -Argument "-NoProfile -WindowStyle Hidden -ExecutionPolicy Bypass $argLine"
  $t = New-ScheduledTaskTrigger -AtLogOn -User "$env:USERDOMAIN\$env:USERNAME"
  $s = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -ExecutionTimeLimit ([TimeSpan]::Zero) -RestartCount 3 -RestartInterval (New-TimeSpan -Minutes 1)
  Register-ScheduledTask -TaskName $TaskName -Action $a -Trigger $t -Settings $s -Description 'Starts the Music Stream public link at logon (created by Make Music Stream public).' -Force | Out-Null
}

function Start-Quick {
  $port = Assert-Safe; Get-Cloudflared
  Stop-Mine
  Get-ChildItem $Pub -Filter 'quick*.log' -ErrorAction SilentlyContinue | Remove-Item -Force -ErrorAction SilentlyContinue
  $log = Join-Path $Pub ('quick-' + (Get-Date -Format 'yyyyMMdd-HHmmss') + '.log')   # new file each run, so an old link is never re-read
  Say "Opening an instant public link (takes about 10-30 seconds)..." 'Cyan'
  Start-Process -FilePath $Cf -ArgumentList @('tunnel', '--no-autoupdate', '--protocol', 'http2', '--logfile', "`"$log`"", '--url', "http://127.0.0.1:$port") -WindowStyle Hidden | Out-Null
  $url = $null
  for ($i = 0; $i -lt 90 -and -not $url; $i++) { Start-Sleep -Milliseconds 700
    if (Test-Path $log) { $m = Select-String -Path $log -Pattern 'https://[a-z0-9-]+\.trycloudflare\.com' | Select-Object -First 1; if ($m) { $url = $m.Matches[0].Value } } }
  if (-not $url) { Stop-Mine; Fail "Could not open a link. Your network may block Cloudflare (outbound port 7844). Details: $log" }
  $ok = $false
  for ($i = 0; $i -lt 30 -and -not $ok; $i++) { Start-Sleep 2; try { $r = Invoke-WebRequest -UseBasicParsing -TimeoutSec 8 "$url/health"; $ok = $r.StatusCode -eq 200 } catch {} }
  if (-not $ok -and -not (Select-String -Path $log -Pattern 'Registered tunnel connection' -Quiet)) { Stop-Mine
    Fail "Cloudflare gave a link but this computer could not connect to it. Your network probably blocks Cloudflare tunnels`n(outbound port 7844). Try another network (for example a phone hotspot), or see docs\MAKE_PUBLIC.md. Details: $log" }
  Set-Content $Mode 'quick'
  Set-Content $LinkFile @("Your Music Stream public link (temporary):", $url, "", "It changes every time the computer or the link restarts.", "Check it any time: double-click 'Make Music Stream public' and choose S (status).", "Turn it off: double-click 'Stop public link'.")
  if ($AutoStart) { Set-Task "-File `"$PSCommandPath`" quick -NoOpen"; Say "It will also start by itself when you log in (the address will be new each time; see $LinkFile)." }
  Say ""; Say "PUBLIC LINK: $url" 'Green'
  if (-not $ok) { Say "(Cloudflare is still warming up; if the page does not load, wait a minute and refresh.)" 'Yellow' }
  Say "Saved in: $LinkFile"; Say "Sign in with your Music Stream account. Share the link only with people you trust."
  if (-not $NoOpen) { Start-Process $url }
}

function Start-Permanent {
  $port = Assert-Safe; Get-Cloudflared
  Say ""; Say "Permanent address - you need (both free/cheap):" 'Cyan'
  Say "  1. A free Cloudflare account (https://dash.cloudflare.com/sign-up)"
  Say "  2. A domain name added to that account (for example music.yourname.com)"
  if (-not $Hostname) { $Hostname = (Read-Host "Type the address you want (for example music.yourname.com)").Trim().ToLower() }
  if ($Hostname -notmatch '^[a-z0-9]([a-z0-9-]*[a-z0-9])?(\.[a-z0-9]([a-z0-9-]*[a-z0-9])?)+$') { Fail "That doesn't look like a web address: '$Hostname'" }
  if ($TunnelName -notmatch '^[A-Za-z0-9_-]{1,60}$') { Fail "Tunnel name may only use letters, numbers, - and _." }
  $home_cf = Join-Path $env:USERPROFILE '.cloudflared'; $cert = Join-Path $home_cf 'cert.pem'
  function Run($argv) { Say ("> cloudflared " + ($argv -join ' ')) 'DarkGray'; if ($DryRun) { return '' }; $o = & $Cf @argv 2>&1 | Out-String; if ($LASTEXITCODE -ne 0) { throw $o }; return $o }
  if (-not (Test-Path $cert)) {
    Say "Step 1: a browser window opens. Log in to Cloudflare and click your domain, then 'Authorize'." 'Yellow'
    Run @('tunnel', 'login') | Out-Null
  } else { Say "Step 1: already logged in to Cloudflare (found $cert)." }
  Say "Step 2: creating (or re-using) the tunnel '$TunnelName'..."
  $id = $null
  if (-not $DryRun) { $j = & $Cf tunnel list --output json 2>$null | Out-String; try { $t = ($j | ConvertFrom-Json) | Where-Object { $_.name -eq $TunnelName } | Select-Object -First 1; if ($t) { $id = $t.id } } catch {} }
  if ($id -and -not (Test-Path (Join-Path $home_cf "$id.json"))) {
    Say "The tunnel '$TunnelName' exists but its key file is not on this computer (for example after a wipe)." 'Yellow'
    $a = if ($Yes) { 'y' } else { Read-Host "Delete it and create it again? Your address stays the same. [Y/n]" }
    if ($a -match '^[nN]') { Fail "Stopped. Copy $id.json from your backup into $home_cf, or choose a new tunnel name." }
    Run @('tunnel', 'cleanup', $TunnelName) | Out-Null; Run @('tunnel', 'delete', '-f', $TunnelName) | Out-Null; $id = $null }
  if (-not $id) {
    $o = Run @('tunnel', 'create', $TunnelName)
    if ($o -match '([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})') { $id = $matches[1] } elseif ($DryRun) { $id = '<tunnel-id>' } else { Fail "Could not read the new tunnel id.`n$o" } }
  Say "Step 3: pointing $Hostname at this computer..."
  Run @('tunnel', 'route', 'dns', '--overwrite-dns', $TunnelName, $Hostname) | Out-Null
  $creds = Join-Path $home_cf "$id.json"
  $yml = @("tunnel: $id", "credentials-file: $creds", "protocol: http2", "ingress:", "  - hostname: $Hostname", "    service: http://127.0.0.1:$port", "  - service: http_status:404")
  if ($DryRun) { Say "[dry-run] would write $Cfg :" ; $yml | ForEach-Object { Say "    $_" 'DarkGray' } } else { New-Item -ItemType Directory -Force $Pub | Out-Null; Set-Content -Encoding ASCII $Cfg $yml }
  Say "Step 4: starting it now and at every logon..."
  if ($DryRun) { Say "[dry-run] would start: cloudflared tunnel --no-autoupdate --config `"$Cfg`" run; and register task '$TaskName'"; return }
  Stop-Mine
  Start-Process -FilePath $Cf -ArgumentList @('tunnel', '--no-autoupdate', '--logfile', "`"$(Join-Path $Pub 'permanent.log')`"", '--config', "`"$Cfg`"", 'run') -WindowStyle Hidden | Out-Null
  Set-Task "-File `"$PSCommandPath`" startpermanent"
  Set-Content $Mode 'permanent'
  Set-Content $LinkFile @("Your Music Stream permanent address:", "https://$Hostname", "", "It keeps working after restarts. Turn it off: double-click 'Stop public link'.")
  Say ""; Say "PERMANENT ADDRESS: https://$Hostname (can take 1-2 minutes to start working)" 'Green'
  if (-not $NoOpen) { Start-Process "https://$Hostname" }
}

switch ($Cmd.ToLower()) {
  'quick' { Start-Quick }
  'permanent' { Start-Permanent }
  'startpermanent' { if (Test-Path $Cfg) { $null = Assert-Safe; Stop-Mine; Start-Process -FilePath $Cf -ArgumentList @('tunnel', '--no-autoupdate', '--logfile', "`"$(Join-Path $Pub 'permanent.log')`"", '--config', "`"$Cfg`"", 'run') -WindowStyle Hidden } }
  'status' {
    $m = @(Get-Mine); $mode = if (Test-Path $Mode) { (Get-Content $Mode -Raw).Trim() } else { 'none' }
    if ($m.Count) { Say "Public link is ON ($mode)." 'Green'; if (Test-Path $LinkFile) { Get-Content $LinkFile | Select-Object -First 2 | Select-Object -Last 1 | ForEach-Object { Say "Address: $_" } } }
    else { Say "Public link is OFF. Music Stream is only on this computer." }
    if (Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue) { Say "Starts by itself at logon: yes" } else { Say "Starts by itself at logon: no" }
  }
  'off' {
    Stop-Mine
    if (Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue) { Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false }
    Remove-Item $LinkFile, $Mode -ErrorAction SilentlyContinue
    Say "Public link is OFF. Music Stream still works on this computer (http://127.0.0.1:$(Get-Port))." 'Green'
    if (Test-Path $Cfg) { Say "Your permanent address settings are kept; choose B again to turn it back on." }
  }
  'menu' {
    Say "Make Music Stream public" 'Cyan'; Say ""
    Say "  A  Instant link right now - no account needed. The link changes when the computer restarts."
    Say "  B  Permanent address of your own (needs a free Cloudflare account and a domain name)."
    Say "  S  Show status"
    Say "  O  Turn the public link off"
    Say "  Q  Quit"
    $c = (Read-Host "Choose A, B, S, O or Q").Trim().ToUpper()
    switch ($c) {
      'A' { $r = (Read-Host "Start the instant link by itself every time you log in? [y/N]").Trim(); if ($r -match '^[yY]') { $AutoStart = $true }; Start-Quick }
      'B' { Start-Permanent }
      'S' { & $PSCommandPath status -Dir $Dir }
      'O' { & $PSCommandPath off -Dir $Dir }
      default { Say "Nothing changed." }
    }
  }
  default { Say "usage: public.ps1 [quick|permanent|status|off]"; exit 2 }
}
exit 0
