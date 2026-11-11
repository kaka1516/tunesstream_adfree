# Updates: how a change gets from the box to the phone and desktop

## The pipeline used today

```
box <private-workspace> (write patch + tests, run on a box test server :8140)
   │ CopyFromBox
   ▼
desktop C:\Users\<you>\audit\<bundle>\          (also the Windows apply.cmd lives here)
   │ scp -P 8022 -i C:\Users\<you>\.ssh\id_ed25519_phone   (host alias [<phone-ip>]:8022, user <termux-user>)
   ▼
phone ~/msaudit/<bundle>/  ──sh apply.sh / deploy_server.sh──>  ~/music-stream  ──one batched restart──> live
```

Helper: `powershell -File C:\Users\<you>\sec\prun.ps1 <script.sh>` copies a shell script to the phone, runs it with `sh`, then deletes it. Use it for anything with quotes, because nested quoting over ssh from PowerShell breaks.

## Patch scripts: conventions
- **Python patchers** (`patch_*.py <file>`):
  - find an exact anchor string in the *current* file and insert or replace code
  - add a **marker** comment such as `# lock64-20261111` (tag + date)
  - are **idempotent**: if the marker is already there, they do nothing
  - fail loudly if the anchor is missing, rather than guessing
  - Other workers patch the same files, so **re-read the live file right before patching**, never patch from an old copy, and keep their markers (`enhance-20261111`, `vizadv`, `adult-viz-20261111`, `play4/5`, …).
- **Apply scripts** (`apply.sh`, `deploy_server.sh`) follow the same steps:
  1. Copy the targets into a temp dir.
  2. Run the patchers on the copies.
  3. `python -m py_compile`.
  4. `grep` for every expected marker.
  5. Back up the live file once: `<file>.bak-<tag>-YYYYMMDD` (for example `ms_users.py.bak-lock64-20261111`, `music_server.py.bak-bundle2-20261111`).
  6. Atomically `mv` the patched copy over the live file.

  They **never restart anything**; each prints its own rollback line. Older backups are named `*.pre-vNN.*`.
- **Front-end files** (`player.html`, `sw.js`, `vendor/…`) are served from disk on every request, so they go live **without a server restart**. Python files (`music_server.py`, `ms_users.py`, `famlang.py`) need a restart.
- **Windows:** `apply.cmd` does the same with `C:\Python313\python.exe`, with the root at `C:\Users\<you>\music-stream-8121`.

## Batched restart with health check and rollback (phone)
Restart the phone server **once** per batch (for example, `deploy_server.sh` followed by `sh ~/viz18/apply.sh` in the same window). The template is `<private-workspace>`:

1. **Busy check:** wait while anyone is streaming. The signals are `sessions.json`, `lcache/plays/plays.json` or `server.log` written in the last 150 s, or established connections on :8121. Retry for up to about 20 min.
2. Apply, then `py_compile` both files. If that fails, restore the `.bak` and stop.
3. `kill` the `python music_server.py` pid(s). `run.sh` relaunches within 5 s, and **cloudflared isn't touched**.
4. Poll `http://127.0.0.1:8121/health` every 2 s. Success means **200 within 80 s from a new pid**.
5. If it doesn't come up in time, restore the `.bak` files, kill again, and wait for health ("ROLLED BACK, old code running").
6. Run light checks only:
   - `/health` 200
   - `/recover` 200 locally and 403 with a `CF-Connecting-IP` header
   - marker counts
   - `cloudflared` and `run.sh` each running once
   - one `/audio` Range request (206) and one search through the tunnel

Never run test suites on the phone.

**Desktop 8121:** run `apply.cmd`, then stop the pid listening on 8121 (check that it isn't 11888). `run.ps1` relaunches it after a `pip install -U yt-dlp` (so expect 10–30 s), then poll `/health`.

## yt-dlp auto-update (three mechanisms; know which one ran)

| Where | Mechanism | Safety |
|---|---|---|
| Phone | `ytdlp_update.sh`, started in the background by `run.sh` on each server start, at most once every 12 h (stamp `.ytdlp_update.stamp`, lock dir) | Records the working `yt-dlp/urllib3/requests` versions, upgrades with a 5-min cap, smoke-tests a real lookup and a search, rolls back if broken. Log: `ms-update.log` |
| Phone and desktop | Inside the server, when `YTDLP_AUTO_UPDATE=1` (the default; unset on both): `ensure_ytdlp` upgrades on boot, `ytdlp_watch` runs a smoke test every hour (`YTDLP_SMOKE_SEC`) and heals by `pip install -U` (then `--pre` once) if broken, and `ytdlp_daily` runs nightly | Writes `ytdlp_update.json`, `ytdlp_heal.txt`. The player shows a toast for up to 1 h after a heal (`/api/ytdlp`) |
| Desktop | `run.ps1` runs `pip install -U "yt-dlp[default]"` before **every** server start | No smoke test or rollback |
| Manual | `POST /api/admin/update-ytdlp` (admin or owner key); `scripts/update-ytdlp.sh` / `.ps1` | — |

`yt-dlp[default]` pulls in **yt-dlp-ejs**, the JS challenge solver, which runs on `node`. A running server keeps the yt-dlp it imported until it restarts. The in-process module is reloaded by the heal path, but a restart is the reliable way.

## Visuals weekly update
`scripts/viz-update.py` runs Monday 04:00 IST:
- phone: cron, plus the `wd.sh` hook as a backup
- desktop: scheduled task `MusicStream8121_VizUpdate`

How it works:
- allowlisted sources only, licence checked per item
- limits of 50 MB of network and 1 GB on disk
- temp dir → validate → atomic merge, keeping the last-good catalog
- **no restart:** the player picks up `clips.json` / `rev.js` on its next open
- turn it off with `viz-update.py --off` (creates `assets/viz/update/disabled`)
- butterchurn presets are no longer fetched (Trippy was removed 2026-11-11; allowlist entries removed, source off)

## How the PWA picks up changes
- **The page (`/`)** is fetched **network-first** by the service worker on every navigation, and the server sends `Cache-Control: no-store`. Opening the app, or a full reload, always gets the newest `player.html`. The cached copy (`/shell`) is used only when offline.
- **`sw.js`** is re-checked by the browser on navigation. A changed file installs, calls `skipWaiting()` and activates straight away. `activate` deletes old `ms-*` caches (keeping the offline shell), and pages can ask the active worker to `clients.claim()` (`ms-claim`).
- **Bump `const V='ms-vNN'` in `sw.js`** whenever cached assets change (skins, vendor, `/assets/` JS/JSON, `/game.js`). Assets under `/vendor/` and `/assets/` are cached for 30 days, so **change their URL** when you change them (`enhance.js?v=20261111c` style).
- **An already-open tab keeps the old code until it's reloaded or reopened.** The player doesn't poll for a new build or auto-reload. "Without a manual refresh" holds for the next app open, not for a tab that's left open.
- **Offline songs** (`off` cache) and the 18+ pack are never touched by updates; the 18+ pack is never cached.
