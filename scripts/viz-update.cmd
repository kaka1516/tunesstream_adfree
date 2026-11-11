@echo off
REM Low-priority visuals updater for the 8121 copy. Does not touch 8120 or C:\music-stream.
cd /d "%~dp0.."
C:\Windows\System32\cmd.exe /c start /b /wait /belownormal C:\Python313\python.exe "%~dp0viz-update.py" %*
