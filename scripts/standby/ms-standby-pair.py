#!/usr/bin/env python3
"""Music Stream failover-20261111 - run on the MAIN server:  ms-standby-pair
Makes a one-time pairing code so another device on the same Wi-Fi can become the backup server.

  * creates a new ssh key that may ONLY run scripts/standby/ms-export.sh (read-only copies), and
    adds it to ~/.ssh/authorized_keys marked "ms-standby"
  * serves, for 15 minutes on this Wi-Fi only (port 8125), a page at http://<this-ip>:8125/<CODE> with
      - setup-standby.cmd   (Windows: download, double-click)
      - a one-line command  (Linux / old phone in Termux: paste)
  * then stops. If nobody used the code, the key is removed again.
Other commands:  ms-standby-pair list | remove-all
"""
import base64, http.server, json, os, re, secrets, socket, socketserver, subprocess, sys, tempfile, threading, time
from pathlib import Path

HOME = Path.home(); ROOT = Path(__file__).resolve().parents[2]
AK = HOME / ".ssh" / "authorized_keys"
EXPORT = ROOT / "scripts" / "standby" / "ms-export.sh"
PAIR_PORT = int(os.environ.get("MS_PAIR_PORT", "8125")); TTL = 15 * 60

def lan_ip():
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try: s.connect(("1.1.1.1", 53)); return s.getsockname()[0]
    finally: s.close()
def ssh_port():
    for f in (Path(os.environ.get("PREFIX", "/usr")) / "etc/ssh/sshd_config", Path("/etc/ssh/sshd_config")):
        try:
            m = re.search(r"(?m)^\s*Port\s+(\d+)", f.read_text())
            if m: return m.group(1)
        except Exception: pass
    return "8022" if "com.termux" in os.environ.get("PREFIX", "") else "22"
def env_port():
    try:
        m = re.search(r"(?m)^MUSIC_PORT=(\d+)", (ROOT / "music.env").read_text()); return m.group(1) if m else "8121"
    except Exception: return "8121"
def public_url():
    try:
        m = re.search(r"hostname:\s*\"?([^\"\s]+)", (HOME / ".cloudflared" / "config.yml").read_text()); return "https://" + m.group(1)
    except Exception: return ""

def ak_lines():
    try: return AK.read_text().splitlines()
    except FileNotFoundError: return []
def ak_write(lines):
    AK.parent.mkdir(mode=0o700, exist_ok=True)
    t = AK.with_name(AK.name + ".tmp"); t.write_text("\n".join(lines) + "\n"); os.chmod(t, 0o600); os.replace(t, AK)

if len(sys.argv) > 1 and sys.argv[1] in ("list", "remove-all"):
    ls = ak_lines(); mine = [l for l in ls if " ms-standby-" in l]
    if sys.argv[1] == "list":
        print("\n".join(l.rsplit(" ", 1)[-1] for l in mine) or "no backup devices paired")
    else:
        ak_write([l for l in ls if " ms-standby-" not in l]); print(f"removed {len(mine)} backup key(s); those devices can no longer copy from here")
    sys.exit(0)

if not EXPORT.is_file(): sys.exit(f"missing {EXPORT}")
code = "".join(secrets.choice("abcdefghjkmnpqrstuvwxyz23456789") for _ in range(6))
label = f"ms-standby-{time.strftime('%Y%m%d')}-{code}"
tmp = Path(tempfile.mkdtemp(prefix="mspair")); os.chmod(tmp, 0o700)
subprocess.run(["ssh-keygen", "-q", "-t", "ed25519", "-N", "", "-C", label, "-f", str(tmp / "k")], check=True)
priv = (tmp / "k").read_text(); pub = (tmp / "k.pub").read_text().strip()
for f in tmp.iterdir(): f.unlink()
tmp.rmdir()
line = f'restrict,command="sh {EXPORT}" {pub}'
ak_write(ak_lines() + [line])

ip = lan_ip(); conf = {"master": ip, "sshPort": ssh_port(), "sshUser": os.environ.get("USER") or subprocess.run(["id", "-un"], capture_output=True, text=True).stdout.strip(),
                       "masterPort": env_port(), "public": public_url(), "port": env_port()}
TPL = ROOT / "scripts" / "standby"
def win_cmd():
    t = (TPL / "bootstrap-win.cmd.tpl").read_text()
    return t.replace("@CONF@", json.dumps(conf)).replace("@KEY@", priv.strip()).replace("\r\n", "\n").replace("\n", "\r\n").encode()
def unix_sh():
    t = (TPL / "bootstrap.sh.tpl").read_text()
    c = "".join(f"{k}='{v}'\n" for k, v in (("MASTER", conf["master"]), ("SSHPORT", conf["sshPort"]), ("SSHUSER", conf["sshUser"]), ("MPORT", conf["masterPort"]), ("PUBLIC", conf["public"]), ("PORT", conf["port"])))
    return t.replace("@CONF@", c).replace("@KEY@", priv.strip()).encode()
used = {"n": 0}; bad = {"n": 0}; deadline = time.time() + TTL
PAGE = f"""<!doctype html><meta charset=utf-8><meta name=viewport content="width=device-width,initial-scale=1"><title>Music Stream backup pairing</title>
<style>body{{font:16px/1.5 system-ui,sans-serif;max-width:640px;margin:20px auto;padding:0 14px;background:#111;color:#eee}}a.b{{display:inline-block;background:#ff4f2b;color:#fff;padding:12px 18px;border-radius:10px;text-decoration:none;font-weight:700}}code{{display:block;background:#222;padding:10px;border-radius:8px;word-break:break-all;user-select:all}}</style>
<h2>Make this device the Music Stream backup</h2>
<h3>Windows PC</h3><p><a class=b href="/{code}/setup-standby.cmd" download>Download setup-standby.cmd</a></p><p>Then double-click it (if Windows warns, click <b>More info → Run anyway</b>). It takes a few minutes.</p>
<h3>Linux, Raspberry Pi or an old Android phone (Termux)</h3><p>Paste this and press Enter:</p><code>curl -fsS http://{ip}:{PAIR_PORT}/{code}/sh | sh</code>
<p style="color:#999;font-size:14px">This page stops working 15 minutes after it was made.</p>"""
class H(http.server.BaseHTTPRequestHandler):
    def log_message(self, *a): pass
    def _send(self, body, ctype, name=None):
        self.send_response(200); self.send_header("Content-Type", ctype); self.send_header("Cache-Control", "no-store")
        if name: self.send_header("Content-Disposition", f'attachment; filename="{name}"')
        self.send_header("Content-Length", str(len(body))); self.end_headers(); self.wfile.write(body)
    def do_GET(self):
        p = self.path.split("?")[0].rstrip("/")
        if time.time() > deadline: self.send_error(410); return
        if p == f"/{code}": return self._send(PAGE.encode(), "text/html; charset=utf-8")
        if p == f"/{code}/setup-standby.cmd": used["n"] += 1; print(f"  {time.strftime('%H:%M:%S')} Windows setup downloaded by {self.client_address[0]}", flush=True); return self._send(win_cmd(), "application/octet-stream", "setup-standby.cmd")
        if p == f"/{code}/sh": used["n"] += 1; print(f"  {time.strftime('%H:%M:%S')} Linux/Termux setup downloaded by {self.client_address[0]}", flush=True); return self._send(unix_sh(), "text/plain; charset=utf-8")
        bad["n"] += 1
        if bad["n"] > 30: os._exit(3)
        self.send_error(404)
class S(socketserver.ThreadingMixIn, http.server.HTTPServer): daemon_threads = True; allow_reuse_address = True
srv = S(("0.0.0.0", PAIR_PORT), H)
print(f"\nPairing code: {code}   (works for 15 minutes, on this Wi-Fi only)\n")
print(f"  Windows PC : open  http://{ip}:{PAIR_PORT}/{code}  in a browser, download setup-standby.cmd, double-click it")
print(f"  Linux / old phone (Termux):  curl -fsS http://{ip}:{PAIR_PORT}/{code}/sh | sh\n")
print("Leave this open until the other device says Done. Press Ctrl+C to stop early.", flush=True)
threading.Thread(target=srv.serve_forever, daemon=True).start()
try:
    while time.time() < deadline: time.sleep(2)
except KeyboardInterrupt: pass
srv.shutdown(); priv = ""
if not used["n"]:
    ak_write([l for l in ak_lines() if label not in l]); print("Nobody used the code; its key was removed.")
else: print(f"Pairing closed. The backup key is kept (remove with: ms-standby-pair remove-all).")
