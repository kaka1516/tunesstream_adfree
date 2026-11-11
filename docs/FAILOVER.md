# Backup server (automatic failover)

*failover-20261111. Built and drilled on 11 Nov 2026 (IST).*

The phone stays the **main server**. A **backup** device on the same Wi-Fi (now: the Windows PC) keeps a fresh copy of the app and everyone's accounts, likes, playlists and settings. It takes over **https://music.example.com by itself only when the main phone's link is down**, and hands it back when the phone is OK again. While the phone is fine, the backup serves nobody, so normal use isn't affected.

## The easy version

### Make a device the backup (3 steps)

1. **On the main phone**, open Termux and type `ms-standby-pair`.
   It shows a 6-letter code and stays open for 15 minutes.
2. **On the backup device** (same Wi-Fi):
   - **Windows PC:** open the address it shows (like `http://<phone-ip>:8125/abc123`) in a browser. Download **setup-standby.cmd** and double-click it. If Windows warns you, click *More info*, then *Run anyway*.
   - **Old Android phone:** install Termux from F-Droid, open it, and paste the line it shows: `curl -fsS http://<phone-ip>:8125/<code>/sh | sh`. Also install the **Termux:Boot** app and open it once, so the backup starts after a reboot.
   - **Linux or Raspberry Pi:** paste the same line into a terminal.
3. Wait for **Done**. It takes about 3 to 5 minutes the first time, because it copies about 200 MB of visuals.

### Check it

| Where | How | You should see |
|---|---|---|
| Windows | double-click **Music Stream backup - status** on the desktop | `Main server : OK` and `Backup : ready` |
| Phone or Linux | type `ms-standby status` | the same |
| Any browser on the backup device | open `http://127.0.0.1:8121/standby` | a status page that refreshes itself |
| In the app | look at the bottom of the screen | a small amber **"Running on backup server · changes paused"** banner appears only while the backup is serving |

### Turn it off

| Where | How |
|---|---|
| Windows | double-click **Music Stream backup - turn off** on the desktop. To turn it back on, double-click `standby-on.cmd` in the Music Stream folder. |
| Phone or Linux | `ms-standby off`. To turn it back on: `ms-standby on`. |
| Stop a backup device from copying anything (on the main phone) | `ms-standby-pair remove-all` |

## What works on the backup

| Works normally | Paused (until the main phone is back) |
|---|---|
| Signing in with your usual username and password | Changing passwords or names |
| Staying signed in: existing sign-ins are copied every 5 minutes | Adding, removing or changing users (admin page) |
| Search, playing songs and videos, radio, lyrics, downloads | Saving likes, playlists and settings to your account |

- **Likes and settings aren't lost.** If you like a song or change a setting on the backup, it's kept on your device and saved to your account when the main phone is back. This is the player's normal sync retry.
- **Signing in through the backup.** A sign-in made while the backup is serving works there. When the main phone is back, you may be asked to sign in once more.
- **Old key links** (`?k=…`) don't work on the backup, because it has its own key.

## How it works

```
                      ┌──────────── main phone (Termux) ─────────────┐
visitors ─> Cloudflare ─tunnel my-music-tunnel─> cloudflared ─> :8121 music_server.py
               ▲                                    ▲  sshd :8022 (key-only)
               │ (only while the phone's link is    │  standby key may ONLY run ms-export.sh (read-only)
               │  down)                             │
               └─ cloudflared (same tunnel) <─ backup PC :8121 ms_standby.py  <─ every 5 min: data, every 30 min: code
```

**1. Copies, main phone to backup only, never the other way.** The backup's ssh key is added to the phone's `~/.ssh/authorized_keys` as `restrict,command="sh …/scripts/standby/ms-export.sh"`. With that key, the backup can only ask for:

| Request | Gets | How often |
|---|---|---|
| `version` | a fingerprint of each code part + app version (`ms-v81`) | every 30 min |
| `core vendor skins vizdemo assets` | that part of the code as tar.gz (no backups, caches, logs or `music.env`) | only when its fingerprint changed |
| `data` | `users.json`, `sessions.json`, `user_data/`, `lcache/plays/plays.json` | every 5 min |
| `creds` | the tunnel's `config.yml` and credentials json (**not** `cert.pem`, so it can't manage the Cloudflare account) | once, or when missing |
| `status` | `server ok/down` and `tunnel ready/running/stopped` (from cloudflared's `/ready`) | only while deciding to take over or hand back |

- Data files are replaced atomically. The server re-reads them on the next request, so no restart is needed.
- New code restarts only the backup's own 8121 server, and never while it's serving.
- The song cache is never copied; the backup fetches from YouTube itself.
- `music.env` is never copied. The backup keeps its own settings and key.

**2. Backup mode.** `ms_standby.py` runs the normal `music_server.py` unchanged, plus a few additions:

- **Paused writes:** `POST /api/state`, `/api/users`, `/api/auth/password|name|signout|reset-settings|setup|recover` return **503** with "Backup server: changes are paused…". Sign-in, sign-out and the device list still work.
- **Banner:** a small banner is added to the player page.
- **`/api/server-role`:** returns `{"role":"standby"}`. On the main server the same path returns 401 or 404.
- **`/standby`:** a status page, open only from the backup device itself or the home LAN.
- **No Telegram bot.**

The main phone never runs this file.

**3. The watchdog on the backup.** It checks every 20 seconds (Windows: Scheduled Task **MusicStreamStandby**, every minute, 3 checks; Linux/Termux: cron, every minute).

| Backup link off | Backup link on |
|---|---|
| It checks `https://music.example.com/health`. | It checks the phone on the LAN (`http://<phone-ip>:8121/health`) and over ssh (`status`). |
| After **3 failures in a row** (about 60 s), it asks the phone over ssh. If the phone's own tunnel reports *ready*, it doesn't take over (it's probably an internet problem). Otherwise, or if the phone doesn't answer, it starts its own cloudflared for the **same tunnel** (`--config ~/.ms-standby/cf/standby.yml`, metrics on 127.0.0.1:20249). | When the phone's server is OK and its tunnel is running **for 60 s**, it stops its cloudflared. |

**Why not just keep two connectors running?** Cloudflare spreads visitors across all connectors of a tunnel. It has no "use this one only if the other is down" setting on the free plan; Load Balancer is a paid add-on. So the backup's connector exists only while the phone's link is down. Note that for the ~60 s handback window, both connectors are up and some requests can land on either server. Both have the same accounts, so that's harmless.

**Files on the backup:**

| Where | What |
|---|---|
| `%USERPROFILE%\.ms-standby\` (Windows) or `~/.ms-standby/` (Linux/Termux), owner-only | `conf.json`/`conf`, `key` (the restricted key), `known_hosts`, `cf/` (tunnel credentials, owner-only), `state.json`, `status.json`, `events.log`, `cf.log` |
| app folder (PC: `C:\Users\<you>\music-stream-8121`) | `standby.on` marker. `run.ps1` starts `ms_standby.py` instead of `music_server.py` while it exists; the original was kept as `run.ps1.bak-standby-20261111`. |
| Windows | Scheduled Task `MusicStreamStandby` → `wscript tick.vbs` → `ms-standby.ps1 tick` (hidden, no password stored) |

**Scripts:**

| Script | Runs on | Does |
|---|---|---|
| `scripts/standby/ms-export.sh` | main | the only thing the backup key can run (read-only) |
| `scripts/standby/ms-standby-pair.py` (`ms-standby-pair`) | main | pairing code + 15-min LAN page on :8125. `list`, `remove-all` |
| `scripts/standby/ms-standby.ps1` | Windows backup | `status`, `sync`, `off`, `on`, `tick`, `takeover`, `release` |
| `scripts/standby/setup-standby.ps1`, `install-task.ps1` | Windows backup | setup (run by setup-standby.cmd). Safe to run again. |
| `scripts/standby/ms-standby.sh` (`ms-standby`) | Linux/Termux backup | `setup`, `status`, `sync`, `off`, `on`, `tick`, `takeover`, `release` |
| `ms_standby.py` | backup | backup-mode server |

## Off-phone backup: solved

The backup keeps a copy of accounts, sessions, likes, playlists, history and settings that's **at most 5 minutes old**. If the phone dies, that copy is on the PC in `C:\Users\<you>\music-stream-8121` (`users.json`, `sessions.json`, `user_data\`). That's much fresher than the weekly `ms-backup.sh` file, which stays on the phone. To make the PC the new **main** server permanently:

1. Run `ms-standby.ps1 off`.
2. Set up a tunnel on it as described in NEW_PHONE_SETUP.md section 4.

## Drill (11 Nov 2026, IST)

Only the phone's cloudflared was stopped. The phone's server kept running, and wd.sh was paused for the drill and restored afterwards.

| Time (IST) | Event |
|---|---|
| 18:40:37 | phone tunnel stopped. The public link went down (Cloudflare error). |
| 18:41:22 | the backup started its connector (**45 s**). From 18:41:24 the link was served by the PC. |
| 18:41:30 | on the backup: signing in worked; a song played (first 256 KB in 2.9 s, fetched fresh from YouTube); saving settings returned 503 "paused"; the banner was shown. |
| 18:41:34 | phone tunnel started again; watchdog restored |
| 18:41:44 | the backup saw that the phone was OK |
| 18:42:44 | the backup stopped its connector (60 s rule). The link was back on the phone only. |
| 18:45:49 | on the phone: signing in, playing and saving all worked |

A temporary account `drilltest` was used and deleted afterwards.

## Troubleshooting

| Problem | What to do |
|---|---|
| Status says `NOT ready (server is running in normal mode)` | It fixes itself within a minute. On Windows, PowerShell only reads `run.ps1` when the loop starts, so the watchdog restarts the 8121 loop. |
| `Backup : NOT ready (backup server not running)` | Windows: check `server.log` in the app folder. Termux: `sh ~/.ms-standby/run-standby.sh`. |
| `code copy failed` / `data copy failed` in events | The phone isn't reachable on <phone-ip>:8022. Check that sshd is running on the phone (wd.sh restarts it) and that both devices are on the same Wi-Fi. |
| The phone's LAN address changed | Edit `master` in `.ms-standby\conf.json` (Windows) or `MASTER=` in `~/.ms-standby/conf`, or pair again. |
| The backup took over but you'd like it to stop now | `ms-standby.ps1 release` / `ms-standby release`. Then fix the phone; the backup takes over again after about 60 s if the phone is still down. |
| See what happened | `events.log` in `.ms-standby` |
