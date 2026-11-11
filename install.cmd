@echo off
REM Music Stream - one-click installer for Windows 10/11. Just double-click this file.
REM Installs into %LOCALAPPDATA%\MusicStream (no admin rights needed), starts the server on http://127.0.0.1:8125
REM and opens the first-run page where you create the admin account. Re-run any time to update (your data is kept).
REM Options (for scripted installs): install.cmd -Quiet [-Port 8125] [-Lan] [-AdminUser NAME -AdminPasswordFile FILE] [-NoStart] [-NoShortcuts]
setlocal
cd /d "%~dp0"
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\windows\setup.ps1" %*
set RC=%ERRORLEVEL%
if "%~1"=="" pause
exit /b %RC%
