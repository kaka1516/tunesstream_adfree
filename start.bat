@echo off
cd /d "%~dp0"
REM ms-v75: yt-dlp is only upgraded when asked:  start.bat update   (or: start.bat update tunnel)
if /i "%~1"=="update" powershell -NoProfile -ExecutionPolicy Bypass -File scripts\update-ytdlp.ps1
python -m yt_dlp --version > ytdlp_version.txt 2>&1
start "" /b python music_server.py
if /i "%~1"=="tunnel" start "" /b python scripts\music_tunnel.py
if /i "%~2"=="tunnel" start "" /b python scripts\music_tunnel.py
