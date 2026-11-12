#!/usr/bin/env python3
"""Music Stream BACKUP (standby) server - failover-20261111.

Runs the normal music_server.py, unchanged, with four small differences:
  1. Changes are paused: likes/playlists/settings sync (POST /api/state), password and name changes,
     user admin, sign-out-other-devices and /recover answer 503 "Backup server, changes paused".
     The player keeps such changes on the device and sends them to the main server when it is back
     (its normal sync retry), so nothing typed on the backup is lost.
     Sign-in, sign-out, playback, search, lyrics, downloads and history all work.
  2. The player shows a small "Running on backup server" banner.
  3. GET /api/server-role -> {"role":"standby", ...}  (the main server has no such path).
  4. GET /standby (home network / this device only) -> a plain status page
     "Main server: OK / Backup: ready".
The main server never runs this file; it is only started by the standby scripts
(scripts/standby/ms-standby.sh or ms-standby.ps1).
"""
import json, os, sys, time, urllib.parse
from pathlib import Path

ROOT = Path(__file__).resolve().parent
os.chdir(ROOT)
sys.path.insert(0, str(ROOT))
os.environ["MUSIC_STANDBY"] = "1"

import music_server as M  # import is side-effect free (ms-v75): no threads until __main__
import ms_users as U

STATE_DIR = Path(os.environ.get("MS_STANDBY_DIR") or (Path.home() / ".ms-standby"))
STATUS = STATE_DIR / "status.json"

# ---------------------------------------------------------------- 1. pause changes
_ALLOW_POST = {"/api/auth/login", "/api/auth/logout", "/api/auth/sessions"}  # sessions POST only lists devices
_MSG = "Backup server: changes are paused until the main server is back. Your likes and settings stay on this device and are saved then."
_orig_post = U.handle_post
def _standby_post(handler, path, user, trusted):
    if path in _ALLOW_POST:
        return _orig_post(handler, path, user, trusted)
    try:  # drain the body so keep-alive stays in sync
        n = min(int(handler.headers.get("Content-Length", 0) or 0), 4 * 1024 * 1024)
        if n > 0: handler.rfile.read(n)
    except Exception: pass
    return U._json(handler, 503, {"error": _MSG, "standby": True})
U.handle_post = _standby_post

# ---------------------------------------------------------------- 2. banner
_BANNER = b"""<div id=msStandby hidden role=status style="position:fixed;z-index:2147483000;left:50%;bottom:calc(8px + env(safe-area-inset-bottom,0px));transform:translateX(-50%);max-width:calc(100vw - 20px);padding:6px 12px;border-radius:999px;background:rgba(120,72,0,.92);color:#fff;font:600 12.5px/1.3 Inter,system-ui,sans-serif;box-shadow:0 6px 20px #0008;pointer-events:auto;white-space:nowrap;overflow:hidden;text-overflow:ellipsis" title="The main server is down. Music plays normally; changes are saved when it is back.">&#9888; Running on backup server &middot; changes paused<button type=button aria-label="Hide" style="margin-left:8px;background:none;border:0;color:#fff;font:inherit;cursor:pointer;padding:0 2px">&#10005;</button></div>
<script>/* failover-20261111 */(function(){var b=document.getElementById('msStandby');if(!b)return;b.querySelector('button').onclick=function(){b.hidden=true;try{sessionStorage.msStandbyHide='1'}catch(e){}};
function chk(){fetch('/api/server-role',{cache:'no-store',credentials:'same-origin'}).then(function(r){return r.ok?r.json():null}).then(function(j){var on=!!(j&&j.role==='standby');var hid=false;try{hid=sessionStorage.msStandbyHide==='1'}catch(e){}b.hidden=!on||hid;window.__msStandby=on}).catch(function(){b.hidden=true})}
function pos(){try{var m=document.getElementById('mini'),y=8;if(m){var r=m.getBoundingClientRect();if(r.height>0&&getComputedStyle(m).display!=='none'&&r.top<innerHeight)y=Math.max(8,innerHeight-r.top+6)}b.style.bottom=y+'px'}catch(e){}}
chk();pos();addEventListener('resize',pos);setInterval(pos,3000);setInterval(chk,60000)})()</script>
"""
_pg = {"m": None, "b": b""}
_orig_page = M._page
def _standby_page():
    raw = _orig_page()
    if _pg["m"] is not raw:
        i = raw.rfind(b"</body>")
        _pg.update(m=raw, b=(raw[:i] + _BANNER + raw[i:]) if i >= 0 else raw + _BANNER)
    return _pg["b"]
M._page = _standby_page

# ---------------------------------------------------------------- 3 + 4. role + status page
def _status():
    try: return json.loads(STATUS.read_text(encoding="utf-8"))
    except Exception: return {}

def _local_only(h):
    try:
        if any(k.lower().startswith(("cf-", "x-forwarded", "x-real-ip", "forwarded", "via", "tailscale")) for k in h.headers.keys()): return False
        return bool(M._is_local_client(h))
    except Exception: return False

def _ago(ts):
    if not ts: return "never"
    s = int(time.time() - float(ts))
    return f"{s} s ago" if s < 120 else (f"{s // 60} min ago" if s < 7200 else f"{s // 3600} h ago")

def _page_status(st):
    E = lambda x: str(x).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    main_ok = st.get("master_ok"); active = st.get("active")
    rows = [
        ("Main server", "OK" if main_ok else ("DOWN" if main_ok is False else "unknown"), "ok" if main_ok else "bad"),
        ("Backup", "SERVING the public link now" if active else ("off (switched off)" if st.get("off") else "ready (waiting, not serving)"), "warn" if active else ("bad" if st.get("off") else "ok")),
        ("Public link", st.get("public", "?"), "ok" if st.get("public_ok") else "warn"),
        ("Last data copy from main", _ago(st.get("last_sync")), "ok" if st.get("last_sync") and time.time() - st["last_sync"] < 1800 else "warn"),
        ("Code version (main / backup)", f"{st.get('master_ver', '?')} / {st.get('my_ver', '?')}", "ok" if st.get("master_ver") == st.get("my_ver") else "warn"),
        ("Last check", _ago(st.get("ts")), "ok"),
    ]
    tr = "".join(f"<tr><th>{E(a)}</th><td class={c}>{E(b)}</td></tr>" for a, b, c in rows)
    ev = "".join(f"<li>{E(x)}</li>" for x in (st.get("events") or [])[-8:][::-1])
    return f"""<!doctype html><meta charset=utf-8><meta name=viewport content="width=device-width,initial-scale=1"><meta http-equiv=refresh content=20>
<title>Music Stream backup</title><style>body{{font:15px/1.4 system-ui,sans-serif;background:#111;color:#eee;margin:0;padding:18px;max-width:640px}}
table{{border-collapse:collapse;width:100%}}th,td{{text-align:left;padding:8px;border-bottom:1px solid #333}}th{{color:#aaa;font-weight:500;width:48%}}
.ok{{color:#7ee08f;font-weight:700}}.bad{{color:#ff7b7b;font-weight:700}}.warn{{color:#ffc65c;font-weight:700}}li{{color:#bbb;font-size:13px}}</style>
<h2>Music Stream &middot; backup server</h2><table>{tr}</table><h3>Recent events</h3><ul>{ev or '<li>none</li>'}</ul>
<p style="color:#888;font-size:13px">Refreshes every 20 s. Switch off: run standby-off on this machine.</p>"""

_orig_get = M.H.do_GET
def _standby_get(self):
    p = urllib.parse.urlparse(self.path).path
    if p == "/api/server-role":
        st = _status()
        return self.send(200, json.dumps({"role": "standby", "active": bool(st.get("active")), "last_sync": st.get("last_sync")}), "application/json")
    if p in ("/standby", "/standby.json"):
        if not _local_only(self): return self.send(403, "home network only", "text/plain")
        st = _status()
        if p.endswith(".json"): return self.send(200, json.dumps(st), "application/json")
        return self.send(200, _page_status(st), "text/html; charset=utf-8")
    return _orig_get(self)
M.H.do_GET = _standby_get

if __name__ == "__main__":
    print(f"{time.strftime('%Y-%m-%d %H:%M:%S')} STANDBY mode: changes paused, banner on (failover-20261111)", flush=True)
    M.ensure_ytdlp(background=True); M.ytdlp_watch(); M.ytdlp_daily()
    # no Telegram bot on the backup (it would answer twice)
    class _Srv(M.ThreadingHTTPServer):  # backlog-20261112: same listen queue + quiet busy/hang-up errors as the main server
        request_queue_size = max(16, int(os.environ.get("MUSIC_BACKLOG") or M.cfg.get("MUSIC_BACKLOG", "128") or 128))
        def handle_error(self, request, client_address):
            e = sys.exc_info()[1]
            if isinstance(e, (getattr(M, "ExtractBusy", ()), BrokenPipeError, ConnectionResetError, ConnectionAbortedError)): return
            return super().handle_error(request, client_address)
    _Srv((M.cfg.get("MUSIC_BIND", "0.0.0.0"), M.PORT), M.H).serve_forever()
