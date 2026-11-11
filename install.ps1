# Music Stream one-command installer for Windows 10/11 (ms-v75).
#   powershell -ExecutionPolicy Bypass -File install.ps1 [-Yes] [-NoFfmpeg] [-NoNode] [-Port 8121] [-Lan] [-Autostart] [-UpdateYtDlp]
# Installs Python / optional ffmpeg / optional Node via winget (asks first unless -Yes), creates .venv, installs yt-dlp,
# writes missing music.env keys. Does not start the server, does not register autostart unless -Autostart, never prints the key.
param([switch]$Yes, [switch]$NoFfmpeg, [switch]$NoNode, [int]$Port = 8121, [switch]$Lan, [switch]$Autostart, [switch]$UpdateYtDlp)
$ErrorActionPreference = 'Stop'
Set-Location $PSScriptRoot
function Ask($what) { if ($Yes) { return $true }; return (Read-Host "$what [y/N]") -match '^[yY]' }
function HaveCmd($c) { return [bool](Get-Command $c -ErrorAction SilentlyContinue) }
$winget = HaveCmd 'winget'
$pkgs = @(); if (-not (HaveCmd 'python')) { $pkgs += 'Python.Python.3.12' }
if (-not $NoFfmpeg -and -not (HaveCmd 'ffmpeg')) { $pkgs += 'Gyan.FFmpeg' }
if (-not $NoNode -and -not (HaveCmd 'node')) { $pkgs += 'OpenJS.NodeJS.LTS' }
foreach ($p in $pkgs) {
  if ($winget -and (Ask "Install $p with winget?")) { winget install -e --id $p --accept-package-agreements --accept-source-agreements }
  elseif (-not $winget) { Write-Warning "winget not found: install $p manually" }
}
$env:Path = [Environment]::GetEnvironmentVariable('Path','Machine') + ';' + [Environment]::GetEnvironmentVariable('Path','User')
if (-not (HaveCmd 'python')) { throw 'Python 3.9+ is required (open a new terminal after installing it).' }
python -m venv .venv
$vpy = Join-Path $PSScriptRoot '.venv\Scripts\python.exe'
& $vpy -m pip install -U pip | Out-Null
& $vpy -m pip install 'yt-dlp[default]' unidecode syncedlyrics
if (-not (Test-Path music.env)) { New-Item music.env -ItemType File | Out-Null }
$envText = Get-Content music.env -Raw -ErrorAction SilentlyContinue; if ($null -eq $envText) { $envText = '' }
function AddKey($k, $v) { if ($envText -notmatch "(?m)^$k=") { Add-Content music.env "$k=$v"; $script:envText += "`n$k=$v" } }
AddKey 'MUSIC_PORT' $Port; AddKey 'MUSIC_BIND' ($(if ($Lan) { '0.0.0.0' } else { '127.0.0.1' })); AddKey 'YTDLP_PY' $vpy; AddKey 'YTDLP_AUTO_UPDATE' '0'
$ff = Get-Command ffmpeg -ErrorAction SilentlyContinue
if ($ff) { AddKey 'FFMPEG' $ff.Source } else { Write-Host 'No ffmpeg: direct playback works; mp3 download and the transcoded fallback stream are disabled.' }
if (HaveCmd 'node') { AddKey 'YTDLP_JS_RUNTIME' 'node' } else { AddKey 'YTDLP_JS_RUNTIME' 'none'; Write-Warning 'No Node.js: yt-dlp may fail on some YouTube videos.' }
if ($UpdateYtDlp) { & (Join-Path $PSScriptRoot 'scripts\update-ytdlp.ps1') }
if ($Autostart) { & (Join-Path $PSScriptRoot 'deploy\windows\register-task.ps1') -Dir $PSScriptRoot } else { Write-Host 'Autostart not changed (pass -Autostart to register a per-user logon task).' }
Write-Host "Done. Start: .\scripts\start.ps1   Open: http://127.0.0.1:$Port/?k=<MUSIC_KEY from music.env, created on first start>"
