# yt-dlp updates (ad-free pipe)

SponsorBlock skips use the live community API — no repo pull needed for segment lists.

YouTube **extractor** breakage is fixed by updating **yt-dlp**, not an ad-blocker list.

## Updates (ms-v75)
- Launchers (`start.sh`, `start.bat`, `scripts/start.ps1`) **no longer** upgrade yt-dlp unless asked: `./start.sh --update-ytdlp`, `start.bat update`, `start.ps1 -UpdateYtDlp`.
- Explicit updater: `scripts/update-ytdlp.sh [--pre]` / `scripts\update-ytdlp.ps1 [-Pre]` (uses `YTDLP_PY`; venv-aware; no `--break-system-packages`).
- Server: `YTDLP_AUTO_UPDATE` in `music.env`. `1`/missing = previous behaviour (background upgrade on boot, hourly smoke heal, daily nightly). `0` = never upgrades by itself; the hourly smoke still runs read-only and reports "extractor looks broken" so you can update. `install.sh`/`install.ps1` write `0` for new installs and keep any value you already set.
- Importing `music_server` (tests/tools) starts no background jobs; they start only when the server runs.
- The in-app yt-dlp update action stays available (explicit, user-triggered).

## Weekly habit (optional)
If you leave the server running for days without a restart, either restart weekly so auto-update runs, or occasionally: `python3 -m pip install -U yt-dlp`. Long-lived processes keep the in-memory yt-dlp until restart.

## Smoke heal (ad-free path)
Every hour (override `YTDLP_SMOKE_SEC`) the server resolves a short public video with `bestaudio`. Ads are never injected into this pipe — a failure means the **extractor** broke.

On fail: `pip install -U yt-dlp`, re-smoke; if still bad, `pip install -U --pre yt-dlp` once. Logs `extractor update pulled` and writes `ytdlp_heal.txt`. Client may toast that message for ~1h after heal (`/api/ytdlp`).

This is not ban-evasion and not a browser adblocker — it only keeps FOSS yt-dlp current.
