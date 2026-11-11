# Deploy on Linux / Raspberry Pi / Docker / OpenWrt

## One-command install (Debian/Ubuntu/Fedora/Arch/Alpine, Raspberry Pi, OpenWrt)

```sh
cd music-stream
sh install.sh --port 8121 --lan          # add --yes to skip prompts, --autostart for a systemd user unit
./start.sh                               # nohup python music_server.py >> server.log; pid in server.pid
curl -s http://127.0.0.1:8121/health     # -> ok
```

`install.sh` does the following:
- installs python3 (3.9 or newer), plus optional ffmpeg and nodejs, using the OS package manager
- creates `.venv` where the platform allows it, and installs `yt-dlp[default]` into it
- adds only the **missing** keys to `music.env` (mode 600): `MUSIC_PORT`, `MUSIC_BIND` (`0.0.0.0` with `--lan`, otherwise `127.0.0.1`), `YTDLP_PY`, `YTDLP_AUTO_UPDATE=0`, `FFMPEG`, `YTDLP_JS_RUNTIME` (node, deno or none)

It's safe to run again.

Then create the first admin. Open `http://<host>:8121/setup` from the LAN, or run:
```sh
python3 ms_users.py create-admin "$PWD" admin /path/to/pwfile && shred -u /path/to/pwfile
```

## Auto-start

- **systemd (user unit):** `install.sh --autostart` renders `deploy/systemd/music-stream.service` into `~/.config/systemd/user/` and enables it. The unit has `Restart=on-failure`, `RestartSec=10`, `Nice=5` and `MemoryMax=400M`. To keep it running after logout: `loginctl enable-linger $USER`.
  ```sh
  systemctl --user status music-stream; journalctl --user -u music-stream -f
  ```
- **OpenWrt (procd):** `install.sh --autostart` installs `deploy/openwrt/music-stream.init` as `/etc/init.d/music-stream`.
- **Manual watchdog alternative:** a cron line `* * * * * pgrep -f music_server.py >/dev/null || (cd /opt/music-stream && ./start.sh)`.

## Docker

```sh
docker build -t music-stream .                                   # ffmpeg + node (~250 MB)
docker build --build-arg WITH_FFMPEG=0 -t music-stream:lite .
docker run -d --name ms -p 8121:8121 -v ms-data:/data music-stream
```

`music.env` lives in the `/data` volume, and the server creates `MUSIC_KEY` on first start.

> **Known gap:** the Dockerfile `COPY` line doesn't include **`ms_users.py`**. `music_server.py` imports it at start, so the image as written **fails to start**. It also doesn't persist `users.json`, `sessions.json` or `user_data/` in `/data`. Before using Docker:
> - add `ms_users.py` to the COPY line
> - symlink `users.json`, `sessions.json` and `user_data` into `/data`

## Named Cloudflare tunnel (fixed hostname)

```sh
cloudflared tunnel login                                  # browser; writes ~/.cloudflared/cert.pem (account-level secret)
cloudflared tunnel create my-music                        # writes ~/.cloudflared/<id>.json (tunnel secret)
cloudflared tunnel route dns my-music music.example.org   # the zone must be in your Cloudflare account
cat > ~/.cloudflared/config.yml <<'YML'
tunnel: <id>
credentials-file: /home/<you>/.cloudflared/<id>.json
protocol: http2
ingress:
  - hostname: music.example.org
    service: http://127.0.0.1:8121
  - service: http_status:404
YML
cloudflared tunnel run my-music     # supervise with systemd or a watchdog
```

Keep `MUSIC_OPEN=0`. Tunnel visitors then need an account (or the key). Never run the **same** tunnel name on two machines.

## Reverse proxy instead of a tunnel
`_trust_reason` withholds LAN trust from any request with `X-Forwarded-*` / `Forwarded` / `X-Real-IP` headers, so a local proxy never accidentally makes the internet "LAN". Set `MUSIC_ORIGINS` if the public hostname differs from the `Host` header the proxy sends.
