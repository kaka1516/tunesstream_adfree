> **Superseded (11 Nov 2026):** this page describes the old quick tunnel. The live setup is the named Cloudflare tunnel `my-music-tunnel` → https://music.example.com. See [DEPLOY_LINUX.md](DEPLOY_LINUX.md) and [README.md](README.md).

# Remote access (FOSS)

## Quick tunnel (default, no account)
`./start.sh --tunnel` (Linux/Termux), `start.bat tunnel` or `scripts\start.ps1 -Tunnel` (Windows). Needs the open-source `cloudflared` binary on PATH (or `CLOUDFLARED=` path).
`scripts/music_tunnel.py` runs `cloudflared tunnel --url http://127.0.0.1:$PORT`, writes the `https://*.trycloudflare.com` URL to `public_url.txt`, and restarts if it exits.
The URL **changes on every restart** — fine for testing.

## Named tunnel (optional, later)
A fixed hostname (better for an installed PWA on multiple devices) needs a Cloudflare account and `cloudflared tunnel login`. Not required and not set up — only when asked.

## Access keys
- `MUSIC_KEY` (in `music.env`): shared key; open as `/?k=<key>`.
- Optional `MUSIC_USERS=name:key,name2:key2` for per-person keys.
- Client profiles: add `&u=<name>` for separate history/taste.
Never commit `music.env`; the tunnel URL is public, the key is not.
