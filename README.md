# Music Stream (ms-v79)

Self-hosted YouTube-audio player: a small Python server (`music_server.py`, stdlib HTTP + yt-dlp) and a browser
player (`player.html`, PWA). The **server** only resolves and relays audio; the **browser** (phone/PC) decodes audio,
draws the visualizers, runs the games and renders the Live2D/VRM characters.

## Install in one step

**Windows 10/11:** download the code (green **Code → Download ZIP** on GitHub, or `git clone`), unzip it, and
**double-click `install.cmd`**. That's it. It:
- installs into `%LOCALAPPDATA%\MusicStream` for your user only (no admin rights, nothing system-wide),
- uses your Python / ffmpeg / Node if you have them, otherwise downloads private copies,
- writes a fresh `music.env` with a random secret key (never shown),
- starts the server on **http://127.0.0.1:8125** and opens the page where you create the **admin** account,
- puts **Music Stream** (start + open) and **Stop Music Stream** shortcuts on your desktop.

Run `install.cmd` again any time to update the code; your accounts, settings and key are kept.
Uninstall: `%LOCALAPPDATA%\MusicStream\Uninstall Music Stream.cmd`.

**Linux / Raspberry Pi / Android (Termux)**, one pasted line inside the unzipped/cloned folder:
```sh
sh install.sh --yes --start
```
or, straight from a **public** GitHub repo :
```sh
curl -fsSL https://raw.githubusercontent.com/kaka1516/tunesstream_adfree/main/get.sh | sh
```
Then open **http://127.0.0.1:8125/setup** on that device to create the admin account. Stop with `./stop.sh`, start with `./start.sh`.

Installing never opens your server to the internet. Going public is a separate, deliberate step (next section).

Secrets are **never** in this repo: `music.env`, `users.json`, `sessions.json`, `user_data/`, tunnel credentials,
`cert.pem` and ssh keys are git-ignored. Start from `music.env.example` if you configure by hand.

## Make it public (use it from anywhere)

After installing, it only works at home. To get an https address you can open from anywhere:
- **Windows:** double-click **Make Music Stream public** on the desktop. Choose **A** (instant link, no account, 30 seconds)
  or **B** (your own permanent address; needs a free Cloudflare account and a domain). Turn off: **Stop public link**.
- **Linux / Raspberry Pi / phone (Termux):** type `ms-public`, then choose **A** or **B**. Turn off: `ms-public off`.

It refuses to go public until an admin account exists and the login is switched on. Full plain-English guide:
[docs/MAKE_PUBLIC.md](docs/MAKE_PUBLIC.md).

## If your device is wiped

1. Install again in one step (above).
2. If you have a backup, copy `users.json`, `sessions.json`, `user_data/` and `music.env` back into the app folder.
   If you don't, create a new admin at `http://127.0.0.1:8125/setup`.
3. Run **Make Music Stream public** / `ms-public`. Choose **A** for an instant link right now, or **B** with the **same address**
   as before to get your permanent address back. The tool re-links the tunnel for you.

Stuck? Use choice **A**, which always works without an account, and read "Stuck? What to do" in [docs/MAKE_PUBLIC.md](docs/MAKE_PUBLIC.md).

## Install (advanced options)
| Platform | Command | Notes |
|---|---|---|
| Linux / Raspberry Pi | `sh install.sh` | apt/dnf/pacman/apk; makes `.venv`; asks before each package step (`--yes` to skip prompts) |
| Android (Termux) | `sh install.sh` | `pkg install python nodejs-lts ffmpeg`; pip `--user` |
| OpenWrt (musl) | `sh install.sh --no-node` | opkg `python3 python3-pip`; **ffmpeg skipped by default** |
| Windows 10/11 | `powershell -ExecutionPolicy Bypass -File install.ps1` | winget Python / ffmpeg / Node (asks first) |
| Docker | `docker build -t music-stream . && docker run -d -p 8125:8121 -v ms-data:/data music-stream` | `--build-arg WITH_FFMPEG=0` for a lite image |

Options: `--no-ffmpeg` (`--with-ffmpeg` to force it on OpenWrt), `--no-node`, `--port N` (default 8125), `--lan` (bind 0.0.0.0; default 127.0.0.1),
`--autostart` (opt-in, see below), `--print-autostart` (only shows the rendered template, installs nothing), `--update-ytdlp`.
Re-running is safe: existing `music.env` values (port, bind, `YTDLP_AUTO_UPDATE`, …) are kept, never overwritten. The installer never starts the server and never prints your key;
`MUSIC_KEY` is created in `music.env` on first start. Open `http://<host>:<port>/?k=<MUSIC_KEY>`.

Start: `./start.sh` (Linux/Termux/OpenWrt; refuses to start a second copy while `server.pid` is alive), `start.bat` or `scripts\start.ps1` (Windows). On a phone or any machine with more than one usable core the server starts up to 3 worker processes behind the same public port (`MUSIC_WORKERS=auto`; set `MUSIC_WORKERS=1` for the old single process).

## Updating yt-dlp (explicit)
YouTube changes break extractors; the fix is a newer yt-dlp. Fresh installs set `YTDLP_AUTO_UPDATE=0`, so nothing
changes your packages behind your back. Update when playback breaks:
`scripts/update-ytdlp.sh [--pre]` / `scripts\update-ytdlp.ps1 [-Pre]`, or `./start.sh --update-ytdlp`, or the in-app
yt-dlp update button (re-imports without a restart). Older installs without the key keep the previous behaviour
(automatic background update on boot, hourly heal, daily nightly) until you set `YTDLP_AUTO_UPDATE=0`.

## Autostart (templates, opt-in)
| Platform | Template | Installed by |
|---|---|---|
| OpenWrt | `deploy/openwrt/music-stream.init` (procd) | `install.sh --autostart` → `/etc/init.d/music-stream enable` |
| Linux / Pi | `deploy/systemd/music-stream.service` (user unit) | `install.sh --autostart` → `systemctl --user enable` |
| Termux | `deploy/termux/music-stream-boot.sh` | `install.sh --autostart` → `~/.termux/boot/` (Termux:Boot app) |
| Windows | `deploy/windows/register-task.ps1` (per-user logon task) | `install.ps1 -Autostart` |

## Third-party avatar assets
Licence of Music Stream's own code: **not yet chosen by the owner (unspecified)**. No licence is granted for the original code until one is
chosen; it is credited in `THIRD_PARTY_NOTICES.md`. Third-party code keeps its own licence (`THIRD_PARTY_NOTICES.md`, `licenses/`). Most character models are **optional assets under their own, mostly non-FOSS terms**. Only the
7 CC0 VRM characters form a strictly FOSS build. See `docs/ASSET_LICENSES.md`.
- VRM characters dance with an **original procedural dancer** (`vendor/ms/vrm-dance.js`) driven by the audio analyser. No motion
  files are needed.
- The pixiv VRoid VRMA motion pack and the Runa Inoue VRM were **withdrawn in ms-v77** (licence terms; see `docs/GAME_CREDITS.md`).
  They are not served, not in the Docker image, and not to be committed. Before publishing or building, run
  `sh scripts/check-restricted-assets.sh`.

## Live streams
Live and upcoming YouTube streams (yt-dlp `live_status` `is_live` / `is_upcoming`) can't be played: the audio paths need a finite
file. Search, radio, mixes and playlists drop them. A queued one returns HTTP 409 `live_unsupported`; the player shows
"Live stream — not supported here, skipping" and moves on. Recordings of past streams and concerts (`was_live`, `not_live`) play
normally. The decision never relies on the title.

## What runs where / limits
| Need | Server | Client (browser) |
|---|---|---|
| Python ≥ 3.9 + yt-dlp | required | – |
| JS runtime for yt-dlp (node/deno) | strongly recommended; `YTDLP_JS_RUNTIME=none` works for many but not all videos | – |
| ffmpeg | optional. Without it: `/stream` (any request) and `/dl` serve YouTube's original audio file directly (normally **m4a/AAC**, seekable, Range supported) instead of an MP3 transcode; `/dl` saves `<id>.m4a` | – |
| unidecode / syncedlyrics / Pillow | optional (Devanagari dedupe quality / synced lyrics / webp textures) | – |
| Audio decode, visualizers, Live2D/VRM characters, games | – | modern Chrome/Edge/Firefox/Safari; characters need WebGL; phones get reduced resolution/particles/fps |

No-ffmpeg limitations (honest): no MP3 anywhere — downloads are `.m4a` (AAC), which modern phones/PCs/players handle but
some old car stereos / MP3-only devices do not; if YouTube offers no m4a for a video the server falls back to its best
audio, usually **webm/Opus**, which older iOS Safari and some desktop players cannot play; the player's "hi" quality also
requests Opus. Whole files are fetched by the server before serving (no live transcoding), so first byte can take a few
seconds on slow links. Verified on the build box with ffmpeg forced off (`uat/ms-v75/noffmpeg_direct.json`); not verified
on a device without ffmpeg installed.

Small routers: the server is light (one Python process, ~40–80 MB RSS idle) but yt-dlp resolves are CPU-bound
(seconds on MIPS/ARMv7) and ffmpeg transcoding is not realistic on most routers — keep ffmpeg off there.
Nothing heavy (models, visuals, transcription) runs on the server. Not verified on real OpenWrt/Termux/Windows/Pi
devices from this build machine; see `uat/ms-v75/FULL_CHECK.md` for what was actually run.

Port note: the second PC install uses 8121 (8120 there belongs to another app).

Credits/licences: `docs/GAME_CREDITS.md`, `docs/VISUALS_CREDITS.md`.

## Licences and notices
See `THIRD_PARTY_NOTICES.md` for provenance, the licence texts in `licenses/`, and **release blockers B1–B4**. The project's own licence is unspecified.

## Tests (non-browser; run from the repo root; nothing gets installed)
| What | Command |
|---|---|
| Build strings, diagnostics, SW, layout | `node uat/ms-v79/nonbrowser_v79.test.js` |
| Amahane render order with the real Core 06 (reproduces the v78 shim bug) | `node uat/ms-v79/render_order_shim.test.js` |
| Playback progress monitor (real player code, fake media element) | `node uat/ms-v79/progress_monitor.test.js` |
| Character picker order (19 core) | `node uat/ms-v77/picker_order.test.js` |
| Procedural VRM dancer | `node uat/ms-v77/vrm_dance.test.mjs` |
| Live-stream filter (needs the server on :8130 and `music.env`) | `python3 uat/ms-v77/live_filter.test.py` |
| Restricted-assets guard | `sh scripts/check-restricted-assets.sh` |
These tests do not replace real-browser checks. `uat/ms-v79/FULL_CHECK.md` records what was actually seen in a browser.

## Changed files, deploy and rollback (box build, port 8130)
| Build | Files | Backups |
|---|---|---|
| ms-v76 | player.html, assets/chars/live2d-cubism5.js, docs | `player.pre-v76.html`, `sw.pre-v76.js`, `uat/ms-v76/` |
| ms-v77 | music_server.py (live filter, `/api/playable`), player.html, vendor/ms/vrm-dance.js (new), avatar-vrm*.js, packaging guards | `music_server.pre-v77.py`, `player.pre-v77.html`, `uat/ms-v77/backup/` |
| ms-v78 | cubism.es.js (render order), live2d-cubism5.js, player.html (Check stage closes sheets), sw.js | `uat/ms-v78/backup/` |
| ms-v79 | live2d-cubism5.js (shim removed, runtime counters), cubism.es.js (own-property guard), player.html (progress monitor, honest state, Cubism 5 diagnostics row), sw.js, vrm-dance.js (header comment), viz-demo/v71 and uat_v71_harness (query string) | `uat/ms-v79/backup/` |
| licence pass | THIRD_PARTY_NOTICES.md, licenses/, LICENSE files under vendor/ and assets/chars/lib/, docs | `uat/ms-v78/backup/*.pre-compliance.md` |

**Deploy:** static files are served directly. Bump `APP_BUILD`/`MSV` in player.html and `V` in sw.js together. Restart the server only when
`music_server.py` changed, and only on port 8130:
`MUSIC_PORT=8130 MUSIC_BIND=0.0.0.0 python3 music_server.py >> server.log 2>&1 &` (use `.venv/bin/python` instead if a venv exists; this box has none)
The environment variable overrides `MUSIC_PORT` in music.env. There is no autostart, so after a box reboot the server must be started again.

**Rollback:** copy a build's backups over the live files, for example `cp uat/ms-v79/backup/player.pre-v79.html player.html`, and likewise
`sw.pre-v79.js` → `sw.js`, `live2d-cubism5.pre-v79.js` → `assets/chars/live2d-cubism5.js`, `cubism.es.pre-v79.js` → `assets/chars/lib/cubism5/cubism.es.js`.
Clients pick up the change on reload.

**Withdrawn assets:** the VRMA/Runa files live in `<private-folder-outside-the-repo>/` (with SHA256SUMS). Their terms do not allow putting them back in the web root.
