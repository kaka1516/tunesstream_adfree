# Deploy on Android (Termux)

**Step-by-step for a person:** [NEW_PHONE_SETUP.md](NEW_PHONE_SETUP.md). It covers what you need, backup, fresh install, moving the tunnel, two phones, checks, lockout recovery and troubleshooting.

This page is the technical summary of the **live** phone layout, so it can be rebuilt by hand or by an agent.

## Requirements
- Android 10 or newer, aarch64.
- **F-Droid** builds of Termux, Termux:Boot, Termux:Widget and Termux:API. Don't mix them with Play Store builds, because the signatures differ.
- Termux packages: `python nodejs ffmpeg cloudflared cronie termux-api openssh curl` (the live phone also has git). Then `python -m pip install -U "yt-dlp[default]"`.
- Battery for Termux and Termux:Boot set to Unrestricted. On Samsung, add Termux to "Never sleeping apps". Keep a wakelock (every boot script calls `termux-wake-lock`).
- Python 3.13.13, node v24.17.0, cloudflared 2026.6.1 on the live phone.

## Layout (live)

```
~/music-stream/                 code + state (see ARCHITECTURE.md "Where state lives")
  run.sh                        supervisor loop (starts ytdlp_update.sh in background, then python music_server.py)
  ytdlp_update.sh               safe yt-dlp updater (12 h min gap, smoke test, rollback)
  scripts/viz-update.sh         weekly visuals update
~/.termux/boot/{agh,cloudflared,music-stream}   Termux:Boot scripts
~/wd.sh                         watchdog (cron every minute)
~/.cloudflared/{config.yml,<id>.json,cert.pem}  named tunnel my-music-tunnel (secret)
~/cf/tunnel.log                 tunnel log
~/agh/                          AdGuard Home + userspace Tailscale (optional)
~/ms-backup.sh, ~/ms-restore.sh, ~/ms-backups/  backup / restore (Sunday 03:30)
~/bin/ms-recover, ~/.shortcuts/"Unlock Music Stream"  admin unlock (not in the backup)
~/MUSIC_STREAM_SETUP.md         the new-phone guide
```

## Fast paths

- **From a backup (recommended):**
  ```sh
  tar xzf ms-backup-*.tar.gz ./system/ms-restore.sh -O > ~/ms-restore.sh && bash ~/ms-restore.sh ~/ms-backup-*.tar.gz
  ```
  This installs the packages, restores the files, tunnel keys, boot scripts, wd.sh and crontab, then starts everything and health-checks `127.0.0.1:8121`. **Stop the old phone first.**
- **From scratch (no backup):**
  1. `sh install.sh --port 8121 --lan --autostart`. This installs a simpler `~/.termux/boot/music-stream.sh` that runs `start.sh`.
  2. Start once so `MUSIC_KEY` is generated.
  3. Create the admin at `http://127.0.0.1:8121/setup` in the phone's browser.
  4. Optionally copy `run.sh`, `wd.sh` to get the live-style supervision.
  5. Set up a named tunnel (DEPLOY_LINUX.md, "Named tunnel") on a **new** hostname.

## Operating rules for the phone
- **No heavy tests on the phone.** On 10 Nov a test run used up the memory and Android killed Termux, and the site was down. Test on the box; on the phone run only `/health` and light curl checks.
- **Restart the server only by killing `python music_server.py`.** `run.sh` brings it back; cloudflared stays up.
- **Copy backups off the phone** (scp from the desktop; see NEW_PHONE_SETUP.md, section 2). It isn't automatic.
- **Android 15 or newer:** grant Termux the local-network permission, or LAN clients can't connect.
