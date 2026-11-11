# Music Stream Windows installer (called by install.cmd). Per-user, no admin rights, never prints secrets.
# Layout: %LOCALAPPDATA%\MusicStream\{app (code + music.env + your data), venv, runtime\{python,ffmpeg,deno}, ms.ps1, *.cmd}
param(
  [int]$Port = 8125,
  [string]$Dir = (Join-Path $env:LOCALAPPDATA 'MusicStream'),
  [switch]$Lan,
  [switch]$Quiet,
  [switch]$NoStart,
  [switch]$NoShortcuts,
  [string]$AdminUser = '',
  [string]$AdminPasswordFile = ''
)
$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
$Src = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
$App = Join-Path $Dir 'app'; $Rt = Join-Path $Dir 'runtime'; $Venv = Join-Path $Dir 'venv'
$Blocked = @(8120, 8121)   # ports reserved for other Music Stream copies on this machine; never used by this installer
function Step($m) { Write-Host ""; Write-Host "==> $m" -ForegroundColor Cyan }
function Ok($m) { Write-Host "    $m" -ForegroundColor Green }
function Warn($m) { Write-Host "    $m" -ForegroundColor Yellow }
function Get-File($url, $out) {
  if (Get-Command curl.exe -ErrorAction SilentlyContinue) { & curl.exe -fsSL --retry 3 -o $out $url; if ($LASTEXITCODE -ne 0) { throw "download failed: $url" } }
  else { Invoke-WebRequest -UseBasicParsing -Uri $url -OutFile $out }
}
function Expand-Zip($zip, $dest) {
  New-Item -ItemType Directory -Force -Path $dest | Out-Null
  if (Get-Command tar.exe -ErrorAction SilentlyContinue) { & tar.exe -xf $zip -C $dest; if ($LASTEXITCODE -eq 0) { return } }
  Expand-Archive -Force -Path $zip -DestinationPath $dest
}
function Test-PortFree($p) {
  if ($Blocked -contains $p) { return $false }
  try { $l = [Net.Sockets.TcpListener]::new([Net.IPAddress]::Loopback, $p); $l.Start(); $l.Stop() } catch { return $false }
  try { $l = [Net.Sockets.TcpListener]::new([Net.IPAddress]::Any, $p); $l.Start(); $l.Stop() } catch { return $false }
  return $true
}
function Read-Env($f) { $h = @{}; if (Test-Path $f) { foreach ($l in Get-Content $f) { if ($l -match '^\s*([A-Za-z_][A-Za-z0-9_]*)\s*=(.*)$') { $h[$matches[1]] = $matches[2].Trim() } } }; return $h }
function Set-EnvKey($f, $k, $v) {
  $lines = @(); if (Test-Path $f) { $lines = @(Get-Content $f) }
  $done = $false
  for ($i = 0; $i -lt $lines.Count; $i++) { if ($lines[$i] -match "^\s*$k\s*=") { $lines[$i] = "$k=$v"; $done = $true } }
  if (-not $done) { $lines += "$k=$v" }
  [IO.File]::WriteAllLines($f, [string[]]$lines)
}
function New-Key { $b = New-Object byte[] 24; [Security.Cryptography.RandomNumberGenerator]::Create().GetBytes($b); return ([Convert]::ToBase64String($b)).TrimEnd('=').Replace('+','-').Replace('/','_') }

Write-Host "Music Stream installer" -ForegroundColor White
Write-Host "Install folder: $Dir"
if ($Blocked -contains $Port) { throw "Port $Port is reserved; pick another (default 8125)." }
New-Item -ItemType Directory -Force -Path $Dir, $App, $Rt | Out-Null

# ---- 0. stop an older copy of THIS install (only processes running $App\music_server.py) ----
$ctl = Join-Path $Src 'scripts\windows\ms.ps1'
if (Test-Path (Join-Path $Dir 'ms.ps1')) { & powershell -NoProfile -ExecutionPolicy Bypass -File (Join-Path $Dir 'ms.ps1') stop -Quiet | Out-Null }

# ---- 1. copy the app (code only; your music.env, accounts and caches in $App are kept) ----
Step "Copying the app"
if ((Resolve-Path $Src).Path.TrimEnd('\') -ne (Resolve-Path $App).Path.TrimEnd('\')) {
  & robocopy.exe $Src $App /E /NFL /NDL /NJH /NJS /NP /R:1 /W:1 /XD .git .venv venv runtime cache lcache user_data uat __pycache__ /XF music.env users.json sessions.json *.log *.pid | Out-Null
  if ($LASTEXITCODE -ge 8) { throw "copy failed (robocopy $LASTEXITCODE)" }
}
Copy-Item -Force $ctl (Join-Path $Dir 'ms.ps1')
Ok "app in $App"

# ---- 2. Python 3.9+ (use yours if present, else a private copy) ----
Step "Python"
$py = $null
foreach ($c in @('python', 'python3')) {
  $g = Get-Command $c -ErrorAction SilentlyContinue
  if ($g -and $g.Source -notlike '*\WindowsApps\*') { try { $v = & $g.Source -c "import sys;print(int(sys.version_info>=(3,9)))" 2>$null; if ($v -eq '1') { $py = $g.Source; break } } catch {} }
}
if (-not $py -and (Get-Command py -ErrorAction SilentlyContinue)) { try { $p = & py -3 -c "import sys;print(sys.executable if sys.version_info>=(3,9) else '')" 2>$null; if ($p -and (Test-Path $p)) { $py = $p } } catch {} }
$priv = Join-Path $Rt 'python\tools\python.exe'
if (-not $py -and (Test-Path $priv)) { $py = $priv }
if (-not $py) {
  Warn "No Python found: downloading a private Python 3.12 (about 15 MB)..."
  $z = Join-Path $env:TEMP 'ms-python.zip'; Get-File 'https://www.nuget.org/api/v2/package/python/3.12.8' $z
  Expand-Zip $z (Join-Path $Rt 'python'); Remove-Item $z -Force; $py = $priv
}
Ok "using $py"

# ---- 3. venv + yt-dlp ----
Step "Installing yt-dlp (first time takes a minute)"
$vpy = Join-Path $Venv 'Scripts\python.exe'
if (-not (Test-Path $vpy)) { & $py -m venv $Venv; if ($LASTEXITCODE -ne 0) { throw "could not create venv" } }
& $vpy -m pip install -q --disable-pip-version-check -U pip 2>$null | Out-Null
& $vpy -m pip install -q --disable-pip-version-check -U "yt-dlp[default]" unidecode syncedlyrics
if ($LASTEXITCODE -ne 0) { & $vpy -m pip install -q --disable-pip-version-check -U yt-dlp; if ($LASTEXITCODE -ne 0) { throw "pip install yt-dlp failed (check the internet connection)" } }
Ok ("yt-dlp " + (& $vpy -m yt_dlp --version))

# ---- 4. ffmpeg ----
Step "ffmpeg"
$ff = $null; $g = Get-Command ffmpeg -ErrorAction SilentlyContinue; if ($g) { $ff = $g.Source }
$pff = Join-Path $Rt 'ffmpeg\ffmpeg.exe'
if (-not $ff -and (Test-Path $pff)) { $ff = $pff }
if (-not $ff) {
  Warn "No ffmpeg found: downloading a private copy (about 140 MB)..."
  $z = Join-Path $env:TEMP 'ms-ffmpeg.zip'; $x = Join-Path $env:TEMP 'ms-ffmpeg-x'
  Get-File 'https://github.com/yt-dlp/FFmpeg-Builds/releases/download/latest/ffmpeg-master-latest-win64-gpl.zip' $z
  Expand-Zip $z $x; New-Item -ItemType Directory -Force -Path (Join-Path $Rt 'ffmpeg') | Out-Null
  Get-ChildItem $x -Recurse -Include ffmpeg.exe, ffprobe.exe | Copy-Item -Destination (Join-Path $Rt 'ffmpeg') -Force
  Remove-Item $z, $x -Recurse -Force; $ff = $pff
}
Ok "using $ff"

# ---- 5. JavaScript runtime for YouTube (node or deno) ----
Step "JavaScript runtime"
$js = $null; $g = Get-Command node -ErrorAction SilentlyContinue
if ($g) { $js = "node:" + $g.Source } else {
  $g = Get-Command deno -ErrorAction SilentlyContinue; $pd = Join-Path $Rt 'deno\deno.exe'
  if ($g) { $js = "deno:" + $g.Source } elseif (Test-Path $pd) { $js = "deno:$pd" } else {
    Warn "No Node.js/Deno found: downloading a private Deno (about 40 MB)..."
    $z = Join-Path $env:TEMP 'ms-deno.zip'; Get-File 'https://github.com/denoland/deno/releases/latest/download/deno-x86_64-pc-windows-msvc.zip' $z
    Expand-Zip $z (Join-Path $Rt 'deno'); Remove-Item $z -Force; $js = "deno:$pd"
  }
}
Ok "using $js"

# ---- 6. music.env (created once with a random key; existing values kept) ----
Step "Settings"
$envf = Join-Path $App 'music.env'; $fresh = -not (Test-Path $envf)
$cur = Read-Env $envf
if ($cur.ContainsKey('MUSIC_PORT') -and -not $PSBoundParameters.ContainsKey('Port')) { $Port = [int]$cur['MUSIC_PORT'] }
if ($Blocked -contains $Port) { $Port = 8125 }
if (-not (Test-PortFree $Port)) {
  $p0 = $Port; for ($p = 8125; $p -lt 8200; $p++) { if (Test-PortFree $p) { $Port = $p; break } }
  if ($Port -eq $p0) { throw "no free port between 8125 and 8199" }; Warn "port $p0 is busy; using $Port"
}
if ($fresh) { New-Item -ItemType File -Path $envf | Out-Null }
Set-EnvKey $envf 'MUSIC_PORT' $Port
if ($fresh -or $Lan) { Set-EnvKey $envf 'MUSIC_BIND' ($(if ($Lan) { '0.0.0.0' } else { '127.0.0.1' })) }
Set-EnvKey $envf 'YTDLP_PY' $vpy
Set-EnvKey $envf 'FFMPEG' $ff
Set-EnvKey $envf 'YTDLP_JS_RUNTIME' $js
if (-not $cur.ContainsKey('YTDLP_AUTO_UPDATE')) { Set-EnvKey $envf 'YTDLP_AUTO_UPDATE' '0' }
if (-not $cur.ContainsKey('CACHE_MAX_GB')) { Set-EnvKey $envf 'CACHE_MAX_GB' '5' }
if (-not $cur.ContainsKey('MUSIC_KEY')) { Set-EnvKey $envf 'MUSIC_KEY' (New-Key) }
try { & icacls.exe $envf /inheritance:r /grant:r "$($env:USERDOMAIN)\$($env:USERNAME):F" | Out-Null } catch {}
Ok "music.env ready (port $Port; key generated and kept private)"

# ---- 7. control scripts + shortcuts ----
$startCmd = Join-Path $Dir 'Start Music Stream.cmd'; $stopCmd = Join-Path $Dir 'Stop Music Stream.cmd'
Set-Content -Encoding ASCII $startCmd "@echo off`r`npowershell -NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File `"%~dp0ms.ps1`" start -Open"
Set-Content -Encoding ASCII $stopCmd "@echo off`r`npowershell -NoProfile -ExecutionPolicy Bypass -File `"%~dp0ms.ps1`" stop`r`nping -n 3 127.0.0.1 >nul"
Set-Content -Encoding ASCII (Join-Path $Dir 'Uninstall Music Stream.cmd') "@echo off`r`npowershell -NoProfile -ExecutionPolicy Bypass -File `"%~dp0ms.ps1`" uninstall`r`npause"
if (-not $NoShortcuts) {
  Step "Desktop shortcuts"
  $ws = New-Object -ComObject WScript.Shell; $desk = [Environment]::GetFolderPath('Desktop')
  $ico = Join-Path $App 'favicon.ico'
  foreach ($s in @(@('Music Stream', $startCmd), @('Stop Music Stream', $stopCmd))) {
    $l = $ws.CreateShortcut((Join-Path $desk ($s[0] + '.lnk'))); $l.TargetPath = $s[1]; $l.WorkingDirectory = $Dir; $l.WindowStyle = 7
    if (Test-Path $ico) { $l.IconLocation = $ico }; $l.Save()
  }
  Ok "'Music Stream' and 'Stop Music Stream' are on your desktop"
}

# ---- 8. start + health check ----
if ($NoStart) { Write-Host "`nInstalled. Start it with the 'Music Stream' desktop shortcut."; exit 0 }
Step "Starting the server"
& powershell -NoProfile -ExecutionPolicy Bypass -File (Join-Path $Dir 'ms.ps1') start
if ($LASTEXITCODE -ne 0) { throw "the server did not start; see $App\server.err.log" }
$url = "http://127.0.0.1:$Port"

# ---- 9. first admin account ----
$hasUsers = (Test-Path (Join-Path $App 'users.json')) -and ((Get-Content (Join-Path $App 'users.json') -Raw) -match '"role"\s*:\s*"admin"')
if (-not $hasUsers -and $AdminUser -and $AdminPasswordFile) {
  Step "Creating admin account '$AdminUser'"
  & $vpy (Join-Path $App 'ms_users.py') create-admin $App $AdminUser $AdminPasswordFile
  if ($LASTEXITCODE -ne 0) { throw "could not create the admin account" }
  $hasUsers = $true
}
Write-Host ""
Write-Host "Music Stream is running: $url" -ForegroundColor Green
if (-not $hasUsers) {
  Write-Host "First run: create your admin account at $url/setup (only works from this computer; the Music Stream shortcut opens it too)." -ForegroundColor Yellow
  if (-not $Quiet) { Start-Process "$url/setup" }
} elseif (-not $Quiet) { Start-Process "$url/" }
Write-Host "Start: double-click 'Music Stream' on the desktop.  Stop: double-click 'Stop Music Stream'."
Write-Host "Folder: $Dir   Logs: $App\server.log"
exit 0
