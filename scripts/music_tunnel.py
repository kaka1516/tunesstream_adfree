#!/usr/bin/env python3
"""FOSS quick tunnel: runs `cloudflared tunnel --url http://127.0.0.1:$PORT` (no login/account),
writes the trycloudflare URL to public_url.txt next to music_server.py, restarts on exit."""
import os, re, subprocess, time, pathlib
ROOT = pathlib.Path(__file__).resolve().parent.parent
PORT = os.environ.get("PORT", "8120"); CF = os.environ.get("CLOUDFLARED", "cloudflared")
OUT = ROOT / "public_url.txt"
while True:
    try:
        p = subprocess.Popen([CF, "tunnel", "--no-autoupdate", "--url", f"http://127.0.0.1:{PORT}"], stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
        for line in p.stdout:
            m = re.search(r"https://[a-z0-9-]+\.trycloudflare\.com", line)
            if m: OUT.write_text(m.group(0)); print("public:", m.group(0), flush=True)
        p.wait()
    except FileNotFoundError:
        print("cloudflared not found: https://github.com/cloudflare/cloudflared/releases", flush=True); time.sleep(60)
    if OUT.exists(): OUT.unlink()
    time.sleep(5)
