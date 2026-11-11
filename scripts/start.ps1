# Windows: start server (+ optional quick tunnel). Usage: .\scripts\start.ps1 [-Tunnel] [-UpdateYtDlp]
# ms-v75: yt-dlp is only upgraded with -UpdateYtDlp; a plain start never changes installed packages.
param([switch]$Tunnel, [switch]$UpdateYtDlp)
Set-Location (Split-Path $PSScriptRoot -Parent)
if ($UpdateYtDlp) { & (Join-Path $PSScriptRoot 'update-ytdlp.ps1') }
try { python -m yt_dlp --version 2>&1 | Out-File ytdlp_version.txt } catch { Write-Warning "yt-dlp not importable: $_ (run install.ps1)" }
Start-Process python -ArgumentList "music_server.py" -WindowStyle Hidden
if ($Tunnel) { Start-Process python -ArgumentList "scripts\music_tunnel.py" -WindowStyle Hidden }
