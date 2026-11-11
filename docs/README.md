# Music Stream — documentation index

*Documentation for Music Stream (service worker `ms-v81`).*

Music Stream is a self-hosted, ad-free music player. One Python process (`music_server.py`) does search, recommendations, lyrics and audio/video streaming through **yt-dlp**. Browsers get a single-page player (`player.html`) that installs as a PWA. The **live server is an Android phone running Termux**. It's published at **https://music.example.com** through the named Cloudflare tunnel **my-music-tunnel**. The Windows desktop runs a second copy on port 8121 for the home LAN and Tailscale.

| File | Read it when you want to… |
|---|---|
| [ARCHITECTURE.md](ARCHITECTURE.md) | understand the parts, the request flows (search, 206 streaming, video, login/sync) and where every piece of state lives |
| [CONFIG.md](CONFIG.md) | look up any `music.env` setting, its default and what it does |
| [DEPLOY_ANDROID.md](DEPLOY_ANDROID.md) | run it on a phone (Termux). The step-by-step new-phone guide is [NEW_PHONE_SETUP.md](NEW_PHONE_SETUP.md) |
| [DEPLOY_WINDOWS.md](DEPLOY_WINDOWS.md) | run it on Windows 10/11 |
| [DEPLOY_LINUX.md](DEPLOY_LINUX.md) | run it on Linux, a Raspberry Pi, Docker or OpenWrt |
| [FAILOVER.md](FAILOVER.md) | set up, check or switch off the **automatic backup server** (a PC or old phone takes over the link only while the main phone is down) |
| [UPDATES.md](UPDATES.md) | ship a change (box → phone/desktop), roll it back, and see how yt-dlp, visuals and the PWA update themselves |
| [TROUBLESHOOTING.md](TROUBLESHOOTING.md) | fix a symptom (bot-check, stuck songs, AV1-only video, tunnel down, Termux killed, lockout, slow search…) |
| [MAKE_PUBLIC.md](MAKE_PUBLIC.md) | put it on the internet (instant link or your own address), and what to do after a device wipe |
| [SECURITY.md](SECURITY.md) | review auth, roles, lockouts, recovery and which files are secret |

**Superseded docs:**
- [TUNNEL.md](TUNNEL.md) describes the old quick tunnel and says the named tunnel is "not set up". Use DEPLOY_LINUX.md ("Named tunnel") instead.
- `RESTORE.md` / `README.md` in the backup kit (kept privately) are older. Use NEW_PHONE_SETUP.md instead: the kit tells you to `pkill cloudflared` on the old phone, but that isn't enough because the watchdog restarts it.

**Other docs in this folder** (feature specs and credits, still current for their topic):
- YTDLP.md
- VISUAL_DIRECTION.md, VISUALS_CREDITS.md, VIZ_ADV_CREDITS.md
- ASSET_LICENSES.md
- AVATAR_SLOT.md, LIVE2D_ADAPTER.md
- GROOVE_BRAWL.md, DISCO_BRAWLER_SPEC.md, GAME_CREDITS.md
- FAMLANG_HOOK_PATCH.md
- RAINMETER_IDEAS.md, TERMUX_COLD_START_RESEARCH.md

## The 30-second picture

```
browser / PWA ──https──> Cloudflare edge ──tunnel my-music-tunnel──> cloudflared (phone) ──> 127.0.0.1:8121 music_server.py
                                                                                        ├─ yt-dlp (+ node / yt-dlp-ejs) ─> YouTube
home Wi-Fi / Tailscale ─────────────────────────────────────────────> phone:8121 or desktop:8121 (keyless when MUSIC_TRUST_LAN=1)
```

