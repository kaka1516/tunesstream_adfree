@echo off
REM Double-click to put Music Stream on the internet (A = instant link, B = your own permanent address).
REM Needs Music Stream installed first (install.cmd) and an admin account.
setlocal
set "PS=%LOCALAPPDATA%\MusicStream\public.ps1"
if not exist "%PS%" set "PS=%~dp0scripts\windows\public.ps1"
powershell -NoProfile -ExecutionPolicy Bypass -File "%PS%" %*
if "%~1"=="" pause
