# Configuration

All settings live in **`music.env`** next to `music_server.py`, one `NAME=value` per line, `#` for comments. The file is read **once at start**, so a change needs a server restart.

> **Edit music.env in place.** Change or add single lines; never overwrite or regenerate the whole file. It holds the key, and other workers rely on its exact contents. Never print it, paste it or commit it.

**Priority:** `MUSIC_PORT` from the process environment beats the file. For `MUSIC_OPEN`, `MUSIC_TRUST_LAN`, `MUSIC_CF_TEAM`, `MUSIC_CF_AUD` and `MUSIC_ORIGINS`, the file wins and the environment is used only when the key isn't in the file. Every other key is read from the file only.

Booleans accept `1/true/yes/on` (case-insensitive); anything else is off.

## Server (`music_server.py`)

| Key | Default in code | Live phone | Live desktop | Meaning |
|---|---|---|---|---|
| `MUSIC_KEY` | generated (`token_urlsafe(12)`) and appended on first start | set (secret) | set (secret) | Shared owner key. `?k=<key>` (or the `ms_auth` cookie made from it) grants access and owner actions. **Secret.** |
| `MUSIC_USERS` | empty | unset | unset | Extra per-person keys, `name:key,name2:key2` (legacy; accounts replace this). **Secret.** |
| `MUSIC_PORT` | `8120` | 8121 | 8121 | Listen port. Always set 8121 for this project; 8120 belongs to the other service. |
| `MUSIC_BIND` | `0.0.0.0` | 0.0.0.0 | 0.0.0.0 | Listen address. `127.0.0.1` = this machine only (installers write that unless `--lan`). |
| `MUSIC_OPEN` | `0` | 0 | 0 | 1 = no auth at all, for anyone, including tunnel visitors. Keep 0. |
| `MUSIC_TRUST_LAN` | `0` | 1 | 1 | 1 = LAN/Tailscale/loopback peers without proxy headers are keyless, admin sign-in from there is never locked, and LAN sign-in skips the request rate limiter. |
| `MUSIC_CF_TEAM` / `MUSIC_CF_AUD` | empty | unset | unset | Optional Cloudflare Access: with both set, tunnel requests carrying a valid `Cf-Access-Jwt-Assertion` (RS256, team certs, `aud`) are keyless. |
| `MUSIC_ORIGINS` | empty | unset | unset | Extra allowed `Origin` hosts for browser POSTs (comma list). |
| `MUSIC_BOT_TOKEN` | unset | unset | unset | Turns on the built-in Telegram bot (`tg_loop`). Must be a **dedicated** bot token. **Secret.** |
| `MUSIC_ALLOWED_CHATS` | empty | — | present | Telegram chat ids allowed to command the bot. |
| `YTDLP_PY` | the running Python | set | set | Python that runs `-m yt_dlp` (installers point it at `.venv`). |
| `YTDLP_JS_RUNTIME` | `node` | node | set | JS runtime for YouTube challenges (`node`, `deno`, `bun`, or `none`). Needed together with yt-dlp-ejs. |
| `YTDLP_AUTO_UPDATE` | `1` | unset (= 1) | unset (= 1) | 1 = the server upgrades yt-dlp in the background on boot, runs the hourly smoke heal, and runs a nightly update. 0 = never upgrades by itself (it still smoke-tests and reports). Installers write 0. |
| `YTDLP_DAILY_DELAY` | `180` | — | — | Seconds after start before the daily update job begins. |
| `YTDLP_SMOKE_ID` | `jNQXAC9IVRw` | — | — | Short public video used for the smoke test. |
| `YTDLP_SMOKE_SEC` | `3600` | — | — | Smoke-test interval in seconds. |
| `YTDLP_VISIONOS` | `1` | — | — | Try the yt-dlp `visionos` player client first (auto-off for 30 min when it keeps failing). |
| `SEARCH_FAST` | `1` | unset (= 1) | — | Direct InnerTube search first, with yt-dlp as the fallback. |
| `SEARCH_DISK_TTL` | `21600` | — | — | Disk search cache lifetime in seconds (6 h). |
| `FFMPEG` / `FFPLAY` | `ffmpeg` / `ffplay` | FFMPEG set | both set | Paths. Without ffmpeg, `/dl` serves the original m4a/webm and the mp3 fallback stream is off. |
| `CACHE_MAX_GB` | `5` | 5 | set | Upper limit of the song/video byte cache (`cache/`). |
| `BLOB_DISK_TTL` | `2592000` | — | — | How long a fully cached song stays valid on disk, in seconds (30 days). |
| `MAX_FETCH` | `8` | — | — | Parallel 1 MB upstream chunk fetches (all listeners together). |
| `MAX_ACTIVE_DL` | `4` | — | — | Parallel blobs being downloaded. |
| `MAX_FFMPEG` | `2` | — | — | Parallel ffmpeg transcodes. |
| `FLAT_MAX` | `2` | — | — | Parallel flat-playlist (mix/radio) lookups. |
| `LASTFM_KEY` | unset | — | — | Optional free Last.fm key for `/api/similar` (otherwise ListenBrainz). |

"—" means the key isn't in that machine's file, so the default applies. Phone keys present: `MUSIC_PORT MUSIC_BIND YTDLP_PY FFMPEG YTDLP_JS_RUNTIME MUSIC_KEY MUSIC_OPEN CACHE_MAX_GB MUSIC_TRUST_LAN`. Desktop keys present: the same plus `FFPLAY` and `MUSIC_ALLOWED_CHATS`.

## Hard-coded tunables (change in code, not env)

| Constant | Value | Where |
|---|---|---|
| Sign-in lockout | 10 per user+IP; non-LAN 30 per IP (/64) and 30 per user; 15 min window | `ms_users.py FAIL_*` |
| Sessions | keep 1 year, otherwise 12 h idle; 50 per user | `KEEP_TTL`, `SHORT_TTL`, `MAX_SESS_PER_USER` |
| Passwords | 8–256 chars, PBKDF2-SHA256 310k iterations | `PW_MIN`, `PW_MAX`, `PBKDF2_ITERS` |
| Request rate limits | 180 / 120 heavy / 60 POST per min per client; 900 per min per IP | `_RL_*` in music_server.py |
| Radio cache | 2 h | `RADIO_TTL` |
| Language bias | te 0.40, hi 0.35, en 0.25 | `LANG_BIAS` |

## Script and launcher variables

| Name | Used by | Meaning |
|---|---|---|
| `MS_UPDATE_YTDLP=1` / `--update-ytdlp` | `start.sh` | Upgrade yt-dlp before starting (otherwise the launchers don't touch packages). |
| `PYTHON` | `start.sh`, `update-ytdlp.sh` | Python to use if `YTDLP_PY` isn't set. |
| `CLOUDFLARED`, `PORT` | `scripts/music_tunnel.py` | Quick-tunnel helper (legacy). |
| `MUSIC_STREAM_ROOT` | `scripts/viz-update.sh` | Project folder for the visuals updater. |
| `install.sh` flags | `--yes --no-ffmpeg --with-ffmpeg --no-node --port N --lan --autostart --print-autostart --update-ytdlp` | One-command installer for Linux, Pi, Termux and OpenWrt. |
| `install.ps1` flags | `-Yes -NoFfmpeg -NoNode -Port 8121 -Lan -Autostart -UpdateYtDlp` | Windows installer. |
| `ms-backup.sh --with-assets` | phone | Include the dancer models (about 180 MB) in the backup. |
| `ms-restore.sh <file> [--test DIR]` | phone | Restore; `--test` installs nothing and starts nothing. |
| `viz-update.py --once / --dry-run / --off / --on / --limit / --max-bytes` | all | Visuals updater controls. |
| `python ms_users.py create-admin <dir> <user> <password_file> [--must-change]` | CLI | Create an admin (the password comes from a file, never argv). |
| `python ms_users.py recover <dir> [user] [--password-file F]` | CLI (`ms-recover`) | Unlock the admin, turn it on, set a new password. |

## Per-user flags (users.json, set from the admin page)

- `role`: `admin` | `user`
- `disabled`
- `adult_viz` (18+ visuals tier)
- `mcp` (must change password at next sign-in)
- `name` (display name)
