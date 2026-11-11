# Deploy on Windows 10/11

## Easiest: one click
Double-click **`install.cmd`** in the project folder. It installs everything for your user into
`%LOCALAPPDATA%\MusicStream`, starts the server on http://127.0.0.1:8125, opens the admin setup page and adds
**Music Stream** / **Stop Music Stream** desktop shortcuts. Re-run it to update; your data is kept.
Scripted: `install.cmd -Quiet -AdminUser admin -AdminPasswordFile C:\path\pw.txt` (delete the file afterwards).
Control: `powershell -File %LOCALAPPDATA%\MusicStream\ms.ps1 start|stop|restart|status`.

## Manual / advanced setup


> **Don't run `deploy\windows\register-task.ps1`** there. It registers a task called `MusicStream` with `-Force` and would **overwrite the other service's task**. Use the Startup-folder method below, or rename the task first (for example `MusicStream8121`).

## Fresh install

1. Copy the project folder, for example to `C:\Users\<you>\music-stream-8121`. Don't copy `music.env`, `users.json`, `sessions.json` or `cache\` from another machine unless you are *moving* that machine. See SECURITY.md.
2. Open PowerShell in that folder and run:
   ```powershell
   powershell -ExecutionPolicy Bypass -File install.ps1 -Port 8121 -Lan
   ```
   This does the following:
   - offers to install Python 3.12, FFmpeg (Gyan) and Node LTS with `winget`
   - creates `.venv` and installs `yt-dlp[default]` (which includes yt-dlp-ejs), `unidecode` and `syncedlyrics`
   - adds any **missing** keys to `music.env` (`MUSIC_PORT`, `MUSIC_BIND`, `YTDLP_PY`, `YTDLP_AUTO_UPDATE=0`, `FFMPEG`, `YTDLP_JS_RUNTIME`)

   It doesn't start anything and never prints the key.
3. Optional settings (edit single lines in `music.env`, see CONFIG.md):
   - `MUSIC_TRUST_LAN=1` for keyless home use
   - `CACHE_MAX_GB`
4. Start it:
   - `.\scripts\start.ps1`, or
   - `start.bat`
   - Add `-UpdateYtDlp` / `start.bat update` to upgrade yt-dlp first.

   On first start the server appends `MUSIC_KEY` to `music.env`.
5. Open `http://127.0.0.1:8121/setup` **on that PC** to create the first admin. `/setup` only works from the PC itself or the LAN. Or use the CLI with a password file:
   ```powershell
   python ms_users.py create-admin . admin C:\path\pw.txt
   ```
   Delete the password file afterwards.
6. Firewall, from an admin PowerShell:
   ```powershell
   New-NetFirewallRule -DisplayName "Music Stream 8121" -Direction Inbound -Protocol TCP -LocalPort 8121 -Action Allow -Profile Private
   ```

## Auto-start and supervision (how the live desktop does it)

| Piece | Content |
|---|---|
| `%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup\MusicStream8121.cmd` | `powershell -NoProfile -WindowStyle Hidden -ExecutionPolicy Bypass -File "C:\Users\<you>\music-stream-8121\boot.ps1"` |
| `boot.ps1` | Starts `run.ps1` hidden unless one is already running. The line that started the 8121 quick tunnel (`tun.ps1`) is commented out (sec-20261110). |
| `run.ps1` | Endless loop: `pip install -U "yt-dlp[default]"`, write `ytdlp_version.txt`, run `python music_server.py` (output to `server.log`), log the exit in `run.log`, wait 5 s, repeat. |
| Scheduled task `MusicStream8121_VizUpdate` | Weekly, Monday 04:00: `C:\Python313\python.exe …\scripts\viz-update.py` |
| `ms-recover.cmd` | Double-click to unlock the admin on this copy. |

**To restart only the 8121 server:** find the process listening on 8121 and stop it. `run.ps1` relaunches it in about 5 s, after a pip check.
```powershell
$p=(Get-NetTCPConnection -LocalPort 8121 -State Listen).OwningProcess; Stop-Process -Id $p
```
Check the pid first: it must not be 11888, which is the 8120 service.

**Health check:**
```powershell
(Invoke-WebRequest -UseBasicParsing http://127.0.0.1:8121/health).Content
```
It should print `ok`.

## Optional public access from Windows
- Don't use quick tunnels (`*.trycloudflare.com`). They were switched off because they're public with no auth beyond the key.
- Use a **named** tunnel on a different hostname (see DEPLOY_LINUX.md, "Named tunnel"), or Tailscale.

## Moving the desktop copy to a new PC
Use `export_desktop.ps1` / `restore_desktop.ps1` from the backup kit (kept privately), or copy the folder minus `cache\` and `lcache\`, then run `install.ps1` on the new PC.
