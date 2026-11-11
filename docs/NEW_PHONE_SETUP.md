# Music Stream: set up on a new phone

*Written 11 Nov 2026 from the live phone setup (Android, Termux). No secrets are written here.*

The music site **https://music.example.com** runs entirely on **one Android phone**, inside the **Termux** app.
A Cloudflare "tunnel" called **my-music-tunnel** connects that phone to the web address.
Whichever phone runs that tunnel *is* the website.

## The setup at a glance

| Part | Where it lives on the phone |
|---|---|
| Website address | https://music.example.com → tunnel `my-music-tunnel` → phone port 8121 |
| Music Stream program | `~/music-stream` (5.3 GB; 5.1 GB of that is a song cache that refills by itself and is not backed up) |
| Settings, accounts, passwords | `~/music-stream/music.env`, `users.json`, `sessions.json` (secret) |
| Each person's likes and history | `~/music-stream/user_data/` |
| Tunnel keys | `~/.cloudflared/` (3 files: `config.yml`, `<tunnel-id>.json`, `cert.pem`) (secret) |
| Auto-start after a reboot | `~/.termux/boot/` (3 scripts: `music-stream`, `cloudflared`, `agh`) |
| Watchdog (restarts anything that stopped) | `~/wd.sh`, run **every minute** by the phone's scheduler (cron) |
| Weekly backup | `~/ms-backup.sh`, every **Sunday 3:30 AM**, saved to `~/ms-backups/` |
| Restore | `~/ms-restore.sh` (one command) |
| Admin unlock | `ms-recover` command, "Unlock Music Stream" widget |
| Extras (optional) | AdGuard ad-blocker and Tailscale in `~/agh/` |

---

## 1. What you need

1. **A phone**: Android 10 or newer, 64-bit (almost every phone since 2019), 6 GB RAM or more. You need **at least 8 GB free** storage. The program and apps take about 1.5 GB, and the song cache grows up to the limit set in `music.env` (`CACHE_MAX_GB`).
2. **These apps from F-Droid** (https://f-droid.org), *not* the Play Store. Install them all from the same place:
   - **Termux**: runs the server.
   - **Termux:Boot**: starts it by itself after a reboot.
   - **Termux:Widget**: gives you the one-tap "Unlock Music Stream" button.
   - **Termux:API** (recommended).
3. **A charger and home Wi-Fi.** The phone stays plugged in all the time.
4. **The newest backup file**, named like `ms-backup-20261110-2254.tar.gz` (see section 2).
5. **A PC and a USB cable** to move the backup file.

## 2. Backup

**Which script:** `~/ms-backup.sh`. It runs by itself **every Sunday at 3:30 AM** and keeps the newest 4 copies in `~/ms-backups/` on the phone. The newest one right now is from **10 Nov 2026, 10:54 PM** (4.1 MB).

**Make one right now** (always do this before moving phones):

1. Open **Termux** on the current phone.
2. Type `bash ~/ms-backup.sh` and press Enter.
3. Wait for the line `backup ok: …/ms-backups/ms-backup-DATE.tar.gz`.

**What is inside:**
- the program
- `music.env`, user accounts and sign-ins
- everyone's likes and history
- the tunnel keys
- the auto-start scripts, the watchdog and the schedule
- the AdGuard settings

**What is not inside:**
- the song cache (it refills by itself)
- the dancer models (add `--with-assets` to include them, about 180 MB)
- the AdGuard and Tailscale programs
- the `ms-recover` command and widget (step 3.10 recreates them)

**Getting it off the phone: this is NOT automatic.** The backup stays on the phone unless you copy it.
As of 10 Nov there are copies on the desktop in `C:\Users\<you>\MusicStreamBackups\`, on a second PC in `Documents\MusicStreamBackups\`, and in the bot's private storage.
Copy a new one **once a month and after adding users**.

**Simplest way, from the desktop (<desktop-pc>, same Wi-Fi):** open PowerShell and paste:

```
scp -P 8022 -i C:\Users\<you>\.ssh\id_ed25519_phone <termux-user>@<phone-ip>:ms-backups/ms-backup-*.tar.gz C:\Users\<you>\MusicStreamBackups\
```

**Using a USB cable instead:**

1. In Termux, type `termux-setup-storage` and tap **Allow**. You only do this once; it is not done yet on the current phone.
2. Type `cp ~/ms-backups/ms-backup-*.tar.gz ~/storage/downloads/`
3. Plug the phone into the PC and copy the file from the phone's **Download** folder to the PC.
4. Delete it from Download again: `rm ~/storage/downloads/ms-backup-*.tar.gz`

> The backup file holds every password and the tunnel keys. Treat it like a house key. Never send it by WhatsApp, email or a shared Google Drive folder.

## 3. Fresh install on the new phone

1. Install **F-Droid**, then from it install **Termux**, **Termux:Boot**, **Termux:Widget** and **Termux:API**.
2. Open **Termux:Boot** once, then close it. This switches on auto-start.
3. **Battery optimisation off:**
   - Go to Settings → Apps → **Termux** → Battery → **Unrestricted**.
   - Do the same for **Termux:Boot**.
   - On a Samsung, also go to Settings → Battery → Background usage limits → **Never sleeping apps** → add Termux.
4. Open **Termux**, type `termux-setup-storage` and tap **Allow**.
5. Copy the backup file into the new phone's **Download** folder (USB cable). Then type this in Termux:
   ```
   cp ~/storage/downloads/ms-backup-*.tar.gz ~/ && rm ~/storage/downloads/ms-backup-*.tar.gz
   ```
   Keep only **one** backup file in `~` so the next command picks the right one.
6. **Stop the old phone now** (section 4, step 4). The restore starts the tunnel at the end.
7. **Restore with one command:**
   ```
   tar xzf ~/ms-backup-*.tar.gz ./system/ms-restore.sh -O > ~/ms-restore.sh && bash ~/ms-restore.sh ~/ms-backup-*.tar.gz
   ```
   It takes 5 to 15 minutes. It does these things:
   - installs python, nodejs, ffmpeg, cloudflared, cron, termux-api, openssh, curl and yt-dlp
   - puts back the files, accounts and tunnel keys
   - sets up auto-start and the schedule: watchdog every minute, backup on Sundays, visuals update on Mondays at 4 AM
   - starts the server

   At the end you must see **ALL CHECKS PASSED** and **Music Stream is running**.
8. **Keep it awake:** pull down the notification bar → Termux → **Acquire wakelock**.
9. **AdGuard (only if you use it):** type `sh ~/agh/update.sh`.
10. **Unlock button.** The backup doesn't include it, so paste these lines in Termux:
    ```
    mkdir -p ~/bin ~/.shortcuts
    printf '#!/data/data/com.termux/files/usr/bin/sh\ncd "$HOME/music-stream" && exec python ms_users.py recover "$HOME/music-stream" "$@"\n' > ~/bin/ms-recover
    chmod 700 ~/bin/ms-recover && cp ~/bin/ms-recover ~/.shortcuts/"Unlock Music Stream"
    grep -q 'HOME/bin' ~/.bashrc 2>/dev/null || echo 'export PATH="$HOME/bin:$PATH"' >> ~/.bashrc
    ```
    Then long-press the home screen → Widgets → **Termux:Widget** → place it. It shows "Unlock Music Stream".
11. **Android 15 or newer:** if devices on the home Wi-Fi can't reach the phone, go to Settings → Apps → Termux → Permissions and allow **Nearby devices / Local network**.
12. **Reboot test:** restart the phone, unlock it once, wait 2 minutes, and open the site. It should work without touching anything.

## 4. Moving the tunnel (my-music-tunnel)

The tunnel is just 3 files in `~/.cloudflared/`:

- `config.yml`: says "music.example.com → this phone, port 8121".
- `<tunnel-id>.json`: the tunnel's own key.
- `cert.pem`: the Cloudflare account login. It can create or delete tunnels, so it is the **most sensitive** file.

The backup carries all three, and step 3.7 puts them in place. **You don't have to change anything at Cloudflare.** The address follows whichever phone runs the tunnel.

If you ever copy them by hand instead, follow these steps:

1. Copy the whole `.cloudflared` folder into the new phone's home folder.
2. Type `chmod -R go-rwx ~/.cloudflared && mkdir -p ~/cf`
3. Start the tunnel with `cloudflared tunnel run my-music-tunnel`. After a restore, the watchdog does this for you.
4. **Stop the old phone first, properly.** `pkill cloudflared` alone is **not enough**: the watchdog restarts the tunnel within 1 minute, and Termux:Boot restarts it after a reboot. Pick one of these:
   - **Easiest:** go to Settings → Apps → Termux → **Force stop**, then **switch the old phone off** (or put it in airplane mode).
   - **If the old phone must stay on:** type this in its Termux:
     ```
     crontab -l > ~/crontab.saved && crontab -r
     mv ~/.termux/boot ~/.termux/boot.off
     pkill -f music-stream/run.sh; pkill -f music_server.py; pkill cloudflared
     ```
     To make it live again later, type `crontab ~/crontab.saved; mv ~/.termux/boot.off ~/.termux/boot; bash ~/wd.sh`.
   - **Check:** `pgrep -af cloudflared` shows nothing on the old phone.

## 5. Two phones: does it cause problems?

> **Now automatic (11 Nov 2026):** a backup device (the PC now, or an old phone) can take over the link by itself only while this phone is down, with accounts, likes and playlists copied every 5 minutes. See [FAILOVER.md](FAILOVER.md). The warnings below are about running two *main* servers by hand. The backup also gives you a fresh off-phone copy of your data.


**Yes, if both run the same tunnel at the same time.** Cloudflare accepts both and sends each visitor, sometimes even each click, to *either* phone.
Each phone keeps its **own** copy of accounts, passwords, sign-ins, likes and history, and the two copies **never sync**. You would see:

- people randomly signed out
- a password change that "works" only half the time
- likes and history disappearing and coming back
- songs stopping mid-play

**Two phones with different tunnels and different addresses are fine.**

**Recommended: one live phone, one cold spare.**

**Switch-over order (always in this order):**

1. Make a fresh backup on the old phone (section 2).
2. Copy it off the phone.
3. **Stop the old phone completely** (section 4, step 4).
4. Check that the site is down. It shows a Cloudflare error.
5. Restore and start the new phone (section 3).
6. Check it (section 6).

To go back, do the same steps the other way round. Expect about 15 to 20 minutes of downtime.

**Keeping a cold spare:**

1. Do steps 1 to 4 of section 3 on the spare once.
2. Also type `pkg install -y python` there.
3. **Don't run a full restore** on the spare while the main phone is live, because a full restore starts the tunnel.
4. **Once a month**, copy the newest backup to the spare and *test* it there. Test mode installs nothing and starts nothing:
   ```
   tar xzf ~/ms-backup-*.tar.gz ./system/ms-restore.sh -O > ~/ms-restore.sh
   bash ~/ms-restore.sh ~/ms-backup-*.tar.gz --test ~/restore-test
   ```
   You should see **ALL CHECKS PASSED**. Then delete the test copy with `rm -rf ~/restore-test`. Don't do practice runs on the live phone.
5. On the day you need the spare, follow the switch-over order above.

**Optional: a second always-on phone as a test copy.**
This needs its **own** tunnel and address, for example `test.music.example.com`, and someone comfortable with Termux:

1. On the test phone, do the restore with **Wi-Fi and mobile data off**, so it can't join the live tunnel.
2. Run `pkill cloudflared`, then `sed -i 's/my-music-tunnel/my-music-test/g' ~/wd.sh ~/.termux/boot/cloudflared`.
3. Delete the live tunnel's key: `rm ~/.cloudflared/*.json`.
4. Turn the network back on and type:
   - `cloudflared tunnel create my-music-test`
   - `cloudflared tunnel route dns my-music-test test.music.example.com`
5. Edit `~/.cloudflared/config.yml` so that `tunnel:` is the new tunnel, `credentials-file:` is the new json file, and `hostname:` is `test.music.example.com`.
6. Run `bash ~/wd.sh`.

Its accounts drift apart from the real ones, so use it only for testing.

## 6. Checking it works

1. On the phone, type `curl -s http://127.0.0.1:8121/health` in Termux. It should show **ok**.
2. On another phone using **mobile data** (not home Wi-Fi), open **https://music.example.com**. You should see the sign-in page.
3. Log in with your normal account.
4. Search for a song, play it, and drag to the middle to check that skipping works.
5. On the old phone, `pgrep -af cloudflared` must show **nothing**, so only one phone is live.
6. Do the reboot test (step 3.12).

## 7. Locked out of the admin?

- **At home it never locks:**
  - Admin sign-in from the phone itself or from the home Wi-Fi (`MUSIC_TRUST_LAN` in `music.env`) is never locked out.
  - From outside, 10 wrong tries for one name from one device means a 15-minute wait.
- **Phone browser:** open **http://127.0.0.1:8121/recover** on the phone itself. It refuses anyone coming from the internet.
- **Termux:** type `ms-recover`, or tap the **Unlock Music Stream** widget. It clears the lockouts, switches the admin back on and asks for a new password (typing stays hidden).
  - If step 3.10 isn't done yet, use `cd ~/music-stream && python ms_users.py recover ~/music-stream`
- **Desktop copy (port 8121 on the PC only, not the phone):** double-click `C:\Users\<you>\music-stream-8121\ms-recover.cmd`.

## 8. Troubleshooting

| Problem | What to do |
|---|---|
| **The link doesn't open** (error 502, 530 or 1033) | Android probably closed Termux. Open Termux, type `bash ~/wd.sh`, and wait 1 minute. From the desktop you can right-click `C:\Users\<you>\recover_phone.ps1` → Run with PowerShell (needs Wireless debugging on). If it still fails, make sure the battery setting is Unrestricted, that no second phone is running the tunnel, and look at `tail ~/cf/tunnel.log`. |
| **The site opens but songs fail** | YouTube changed something. yt-dlp updates itself each time the server starts (and undoes a bad update). Look at `tail ~/music-stream/ms-update.log`. Restart the server with `pkill -f music_server.py`: it comes back by itself in about 5 seconds. Also check the phone has internet and free space (`df -h ~`). |
| **The phone rebooted** | Unlock it once and wait 2 minutes; Termux:Boot starts everything. If nothing starts, open Termux:Boot once, then Termux, and type `bash ~/wd.sh`. |
| **Forgot the admin password / locked out** | See section 7. |
| **Phone hot or full** | Keep it on the charger in a cool place. The song cache (`~/music-stream/cache`) is safe to shrink; it refills. |
