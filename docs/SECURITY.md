# Security

## Ways in (in the order the server checks them)

| Mechanism | Grants | Notes |
|---|---|---|
| `MUSIC_OPEN=1` | everything, for everyone | Off on all machines. Never turn it on with a tunnel. |
| **Network trust** (`MUSIC_TRUST_LAN=1`) | keyless use from loopback, private IPv4 or Tailscale 100.64/10 peers **without** proxy/tunnel headers | Never applies to Cloudflare or Funnel traffic. On by default on the phone and desktop. |
| **Cloudflare Access JWT** (`MUSIC_CF_TEAM` + `MUSIC_CF_AUD`) | keyless use through the tunnel with a valid RS256 JWT (team certs, `aud`, `iss`, `exp`, `nbf`) | Not configured. |
| **Account session** `ms_sess` | the signed-in user (role `user` or `admin`) | 256-bit random token; only its SHA-256 is stored in `sessions.json`. HttpOnly, SameSite=Lax, Secure over HTTPS. Lasts 1 year with "keep", otherwise 12 h idle; sliding; at most 50 per user; dropped on password change (`pwv`). |
| **Owner key** `MUSIC_KEY` (`?k=`, or the `ms_auth` cookie made from it) and `MUSIC_USERS` keys | full access; the owner key also grants owner actions | Legacy. Constant-time compare. The key is never needed in URLs once the cookie is set. |

**Roles:**
- `admin`: users page and `/api/users`; owner actions (`/api/admin/*`, server playback `/cmd`, `/pc/*`)
- `user`: listening, their own state

**Per-user flags:**
- `disabled`
- `adult_viz` (18+ tier)
- `mcp` (must change password; such a session can't unlock 18+ assets)

**First admin:** created at `/setup` (local client only, never via the tunnel) or with `python ms_users.py create-admin` (password from a file).

**Passwords:** PBKDF2-HMAC-SHA256, 310,000 iterations, 16-byte salt per user, 8–256 chars, constant-time compare, a dummy hash for unknown users (timing). Nothing logs or returns passwords, hashes or tokens.

**CSRF:** browser POSTs must have a same-origin `Origin` (Host / X-Forwarded-Host / `MUSIC_ORIGINS`); cookies are SameSite=Lax.

**Headers on every response:**
- `Referrer-Policy: no-referrer`
- `X-Content-Type-Options: nosniff`
- `X-Frame-Options: SAMEORIGIN`
- `Cache-Control: no-store` unless it's a static asset

## Lockouts and recovery
- **Sign-in failures** (15-min window):
  - 10 per username + IP for everyone
  - from outside the LAN, also 30 per IP (IPv6 grouped by /64) and 30 per username
- **An admin is never locked** on the server device or the home LAN (with `MUSIC_TRUST_LAN=1`), so the owner can always get in at home.
- **Recovery, all local:**
  - `http://127.0.0.1:8121/recover` (loopback + no proxy headers; 403 through the tunnel, verified)
  - `ms-recover` / the "Unlock Music Stream" Termux widget (`python ms_users.py recover`)
  - `ms-recover.cmd` on the desktop copy

  Each one clears every lockout, turns the admin on and sets a new password (hidden input). It writes `unlock_at` so a running server drops in-memory lockouts.

## Sensitive files (never print, paste, commit or send)

| File | Why |
|---|---|
| `~/.cloudflared/cert.pem` | **Cloudflare account login**: can create or delete tunnels and DNS routes in the account |
| `~/.cloudflared/<tunnel-id>.json` | Tunnel credentials: anyone with it can serve **music.example.com** |
| `music.env` | `MUSIC_KEY` (full access) and any tokens |
| `users.json`, `sessions.json` | password hashes and session-token hashes |
| `user_data/` | each person's history and settings (private) |
| `~/ms-backups/*.tar.gz` and every copy (desktop `MusicStreamBackups`, a second PC, box `<backup folder>`) | contains **all of the above** |
| `~/agh/AdGuardHome.yaml`, `~/agh/ts/` (Tailscale state) | AdGuard admin credentials, tailnet identity |
| `~/ms-termux/tg.env`, `~/music-stream/tg*` | legacy Telegram bot credentials |
| `C:\Users\<you>\.ssh\id_ed25519_phone` | SSH key into the phone |

The backup tarballs are mode 600 and the folders 700. Copy them only by USB, LAN or scp, never by chat or email.

## Open items found while writing these docs (11 Nov 2026)

1. ~~Tailscale Funnel exposed the server publicly on `:8443`, with a shared, LAN-classed lockout key.~~ **Fixed 11 Nov 2026, 15:18 IST:** Funnel switched off (`tailscale funnel --https=8443 off`). It stays off after a reboot, and nothing re-enables it. The Cloudflare tunnel is the only public path.
2. **Userspace Tailscale makes tailnet devices look like loopback** on the phone. Any device on your tailnet can open `/recover` and gets "never locked" admin sign-in. It's limited to your own tailnet; this is how userspace mode is expected to behave but hasn't been tested.
3. **Music key in server.log:** **resolved for current logs.** On 11 Nov, the phone's `server.log`, `run.log`, `ms-update.log`, `tun.log` and `~/cf/tunnel.log` contained the key **0 times**, and the box logs and the desktop logs (`server.log`, `run.log`, `ytdlp_update.log`) were also 0. Two remaining exposures:
   - The legacy quick-tunnel script (`~/ms-termux/tun.sh`, `~/music-stream/tun.sh`) used to send `link/?k=<KEY>` to Telegram, so **old Telegram messages still contain the key**. Rotate `MUSIC_KEY` if that chat isn't private.
   - Built-in Telegram bot replies (`/search`, `/dl`, `/stream`) would include `?k=KEY` links if `MUSIC_BOT_TOKEN` were ever set.
4. **AdGuard web UI listens on 0.0.0.0:3000** (LAN-reachable) and on the tailnet (serve :443). It's protected by AdGuard's own login.
5. **`deploy/windows/register-task.ps1` would overwrite the 8120 service's `MusicStream` task** on the desktop (same name, `-Force`).
6. **No HSTS or CSP headers;** HTTPS is enforced only by Cloudflare. That's acceptable for a personal service, and noted.

## 18+ tier rules
- Served only to a signed-in user whose `adult_viz` flag an admin turned on. Everyone else gets **404**.
- `private, no-store`, and never cached by the service worker. The per-device toggle `msAdultViz` isn't synced.
- Catalogs may contain only items that are clearly adult and licensed. `viz-update.py` skips unclear, franchise or swimwear models.
