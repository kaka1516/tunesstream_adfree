"""Ad-free YouTube/YTM audio service: web UI + HTTP stream + download + local headless playback + Telegram.
Audio is fetched with yt-dlp (no ad segments) and transcoded by ffmpeg. Separate from V10/OKI on purpose."""
import os, sys
from pathlib import Path as _PathForCluster
# cluster-20261113: the public-port process stays a slim TCP front (no yt-dlp) when MUSIC_WORKERS>1.
if __name__ == "__main__" and not os.environ.get("MUSIC_WORKER_ID"):
    sys.path.insert(0, str(_PathForCluster(__file__).resolve().parent))
    import ms_cluster
    if ms_cluster.should_supervise():
        raise SystemExit(ms_cluster.run_supervisor(script=str(_PathForCluster(__file__).resolve())))
import urllib.error, re, json, secrets, subprocess, threading, time, urllib.parse, urllib.request, html
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
from pathlib import Path
ROOT = Path(__file__).parent
ENV = ROOT / "music.env"
def load_env():
    d = {}
    if ENV.exists():
        for l in ENV.read_text().splitlines():
            if "=" in l and not l.startswith("#"):
                k, v = l.split("=", 1); d[k.strip()] = v.strip()
    return d
cfg = load_env()
if "MUSIC_KEY" not in cfg:
    cfg["MUSIC_KEY"] = secrets.token_urlsafe(12)
    with open(ENV, "a") as f: f.write(f"MUSIC_KEY={cfg['MUSIC_KEY']}\n")
KEY = cfg["MUSIC_KEY"]; PORT = int((__import__("os").environ.get("MUSIC_PORT") or cfg.get("MUSIC_PORT", "8125")))
USERS = {u.split(":",1)[1].strip(): u.split(":",1)[0].strip() for u in cfg.get("MUSIC_USERS","").split(",") if ":" in u}  # optional per-user keys: name:key,name2:key2
OPEN = str(cfg.get("MUSIC_OPEN", os.environ.get("MUSIC_OPEN", "0"))).strip().lower() in ("1", "true", "yes", "on")
def _keyok(k):
    """Real key check only (no OPEN / network trust). sec-20261110"""
    return secrets.compare_digest(k or "", KEY) or any(secrets.compare_digest(k or "", x) for x in USERS)
def _authok(k):
    if OPEN: return True
    if getattr(_REQ, "trusted", False): return True  # sec-20261110: set per request in H.guard()
    return _keyok(k)
# --- sec-20261110: trusted-network + Cloudflare Access auth -------------------------------------------
# MUSIC_TRUST_LAN=1: a request is keyless-OK when its TCP peer is private LAN / Tailscale (or loopback) AND it
# carries no proxy/tunnel header (so Funnel / cloudflared / any reverse proxy never inherits LAN trust).
# Cloudflare tunnel requests (Cf-* headers) are keyless-OK only with a valid Cf-Access-Jwt-Assertion
# (RS256, team certs, aud=MUSIC_CF_AUD). Without MUSIC_CF_TEAM+MUSIC_CF_AUD they need the key. Key always works.
import ipaddress as _ipa, base64 as _b64, hashlib as _hsl
def _flag(name, default="0"):
    return str(cfg.get(name, os.environ.get(name, default))).strip().lower() in ("1", "true", "yes", "on")
TRUST_LAN = _flag("MUSIC_TRUST_LAN")
CF_TEAM = re.sub(r"[^A-Za-z0-9-]", "", str(cfg.get("MUSIC_CF_TEAM", os.environ.get("MUSIC_CF_TEAM", ""))).strip().replace(".cloudflareaccess.com", ""))
CF_AUD = str(cfg.get("MUSIC_CF_AUD", os.environ.get("MUSIC_CF_AUD", ""))).strip()
_REQ = threading.local()
_TRUST_NETS = tuple(_ipa.ip_network(x) for x in ("192.168.0.0/16", "10.0.0.0/8", "172.16.0.0/12", "100.64.0.0/10"))
_PROXY_HDRS = ("Cf-Connecting-IP", "X-Forwarded-For", "Tailscale-Funnel-Request", "Cf-Ray", "Cf-Visitor",
               "Cf-Access-Jwt-Assertion", "X-Real-IP", "Forwarded", "X-Forwarded-Host", "X-Forwarded-Proto",
               "Tailscale-User-Login", "Tailscale-Headers-Info")
_CF_HDRS = ("Cf-Ray", "Cf-Connecting-IP", "Cf-Visitor", "Cf-Access-Jwt-Assertion")
def _hdr(handler, name):
    try: return (handler.headers.get(name) or "").strip()
    except Exception: return ""
def _peer_trusted_ip(peer):
    peer = (peer or "").strip()
    if peer.startswith("::ffff:"): peer = peer[7:]
    try: ip = _ipa.ip_address(peer)
    except ValueError: return None
    if ip.is_loopback: return "loopback"
    if ip.version == 4 and any(ip in n for n in _TRUST_NETS): return "lan"
    return None
def _b64u(x):
    x = x.encode() if isinstance(x, str) else x
    return _b64.urlsafe_b64decode(x + b"=" * (-len(x) % 4))
_CFK = {"keys": {}, "ts": 0.0, "try": 0.0}
_CF_OK = {}
def _cf_keys(force=False):
    now = time.time()
    if CF_TEAM and (force or now - _CFK["ts"] > 3600) and now - _CFK["try"] > 30:
        _CFK["try"] = now
        try:
            j = json.loads(urllib.request.urlopen(f"https://{CF_TEAM}.cloudflareaccess.com/cdn-cgi/access/certs", timeout=8).read())
            ks = {}
            for kk in j.get("keys", []):
                if kk.get("kty") == "RSA" and kk.get("kid"):
                    ks[kk["kid"]] = (int.from_bytes(_b64u(kk["n"]), "big"), int.from_bytes(_b64u(kk["e"]), "big"))
            if ks: _CFK.update(keys=ks, ts=now)
        except Exception as e:
            print(f"cf access certs fetch failed: {type(e).__name__}", flush=True)
    return _CFK["keys"]
_SHA256_DI = bytes.fromhex("3031300d060960864801650304020105000420")
def _rs256_ok(signing_input, sig, n, e):
    """RSASSA-PKCS1-v1_5 / SHA-256 verify (pure python, no deps)."""
    kl = (n.bit_length() + 7) // 8
    if len(sig) != kl or kl < 256: return False
    m = pow(int.from_bytes(sig, "big"), e, n).to_bytes(kl, "big")
    t = _SHA256_DI + _hsl.sha256(signing_input).digest()
    want = b"\x00\x01" + b"\xff" * (kl - len(t) - 3) + b"\x00" + t
    return secrets.compare_digest(m, want)
def cf_access_ok(token, now=None, keys=None, team=None, aud=None):
    team = CF_TEAM if team is None else team; aud = CF_AUD if aud is None else aud
    if not (team and aud and token) or len(token) > 8192: return False
    now = time.time() if now is None else now
    hit = _CF_OK.get(token)
    if hit and hit > now and keys is None: return True
    try:
        h64, p64, s64 = token.split(".")
        hd = json.loads(_b64u(h64)); cl = json.loads(_b64u(p64)); sig = _b64u(s64)
        if hd.get("alg") != "RS256": return False
        ks = keys if keys is not None else _cf_keys()
        if hd.get("kid") not in ks and keys is None: ks = _cf_keys(force=True)
        kp = ks.get(hd.get("kid"))
        if not kp or not _rs256_ok(f"{h64}.{p64}".encode(), sig, *kp): return False
        a = cl.get("aud"); a = a if isinstance(a, list) else [a]
        if aud not in a: return False
        if cl.get("iss") != f"https://{team}.cloudflareaccess.com": return False
        exp = float(cl.get("exp") or 0)
        if exp < now - 30 or float(cl.get("nbf") or 0) > now + 60: return False
        if keys is None:
            if len(_CF_OK) > 500: _CF_OK.clear()
            _CF_OK[token] = min(exp, now + 300)
        return True
    except Exception:
        return False
def _trust_reason(handler):
    """Why this request may skip the key, or None. Pure function of peer + headers."""
    cf = any(_hdr(handler, x) for x in _CF_HDRS)
    if cf:
        return "cf-access" if (CF_TEAM and CF_AUD and cf_access_ok(_hdr(handler, "Cf-Access-Jwt-Assertion"))) else None
    if not TRUST_LAN: return None
    if any(_hdr(handler, x) for x in _PROXY_HDRS): return None
    try: peer = handler.client_address[0] if handler.client_address else ""
    except Exception: peer = ""
    return _peer_trusted_ip(peer)
def _req_https(handler):
    if _hdr(handler, "X-Forwarded-Proto").lower() == "https" or _hdr(handler, "Tailscale-Funnel-Request"): return True
    if '"https"' in _hdr(handler, "Cf-Visitor").replace(" ", ""): return True
    return "proto=https" in _hdr(handler, "Forwarded").lower()
# --- end sec-20261110 ---------------------------------------------------------------------------------
# --- login-20261110: username/password accounts (ms_users.py) -----------------------------------------
import sys as _sys
if str(ROOT) not in _sys.path: _sys.path.insert(0, str(ROOT))
import ms_users as _MSU
def _is_local_client(handler):
    """LAN / Tailscale / loopback TCP peer with no proxy or tunnel header. Independent of MUSIC_TRUST_LAN.
    Used for first-run admin setup, which must never be reachable through Cloudflare / Funnel."""
    if any(_hdr(handler, x) for x in _PROXY_HDRS + _CF_HDRS): return False
    try: peer = handler.client_address[0] if handler.client_address else ""
    except Exception: peer = ""
    return _peer_trusted_ip(peer) is not None
_MSU.init(ROOT, is_local=_is_local_client, ipkey=lambda h: _public_ip_key(h), https=lambda h: _req_https(h),
          origins=str(cfg.get("MUSIC_ORIGINS", os.environ.get("MUSIC_ORIGINS", ""))))
_AUTH_PATHS = ("/login", "/setup", "/users", "/api/auth/me", "/api/users", "/api/state")  # login-state-20261110
_AUTH_PATHS = _AUTH_PATHS + ("/recover",)  # recover-20261111 (server3-20261111)
_MSU.HOOKS["lan_trusted"] = lambda h: bool(TRUST_LAN and _is_local_client(h))  # recover-20261111: home LAN counts as trusted only when MUSIC_TRUST_LAN is on
def _rc_local(h):  # recover-20261111: this device, no tunnel/proxy header
    try: return _MSU._loopback_only(h)
    except Exception: return False
_MSU.HOOKS["keyauth"] = lambda h: bool(_presented_key(h) and _keyok(_presented_key(h))) or _auth_cookie_ok(h)  # login-key-setup-20261110
# --- end login-20261110 --------------------------------------------------------------------------------
# ms-v75: JS runtime for yt-dlp's YouTube challenge solver is configurable (node | deno | bun | none). Default unchanged: node.
_JSRT = str(cfg.get("YTDLP_JS_RUNTIME", "node")).strip() or "node"
YTDLP = [cfg.get("YTDLP_PY", __import__("sys").executable), "-m", "yt_dlp"] + ([] if _JSRT.lower() == "none" else ["--js-runtimes", _JSRT])
FFMPEG = cfg.get("FFMPEG", "ffmpeg"); FFPLAY = cfg.get("FFPLAY", "ffplay")
# ms-v75 portability: ffmpeg is optional (only /stream + /dl mp3 transcodes need it); direct /audio passthrough works without it.
def _have_ffmpeg():
    import shutil
    return bool(shutil.which(FFMPEG) or (os.path.isfile(FFMPEG) and os.access(FFMPEG, os.X_OK)))
HAVE_FFMPEG = _have_ffmpeg()
# ms-v75: YTDLP_AUTO_UPDATE=0 stops the server from pip-upgrading yt-dlp by itself (boot, hourly heal, daily nightly).
# Default stays "1" so existing installs behave exactly as before; new install.sh/install.ps1 write 0 and offer an explicit updater.
YT_AUTO = str(cfg.get("YTDLP_AUTO_UPDATE", "1")).strip().lower() not in ("0", "off", "false", "no")
URLFILE = ROOT / "public_url.txt"
NOFLAGS = 0x08000000 if os.name == "nt" else 0  # CREATE_NO_WINDOW (Windows only; non-zero raises ValueError on POSIX)

def ensure_ytdlp(background=True, pre=False, force=False):
    if not (YT_AUTO or force):
        print("yt-dlp auto-update off (YTDLP_AUTO_UPDATE=0); use scripts/update-ytdlp.sh|.ps1 or the in-app update button", flush=True)
        return None
    """Keep yt-dlp current so YouTube extractor breaks heal on restart (SponsorBlock uses live API separately).
    pre=True tries PyPI pre-releases after a failed stable heal (optional)."""
    def run():
        import sys
        py = cfg.get("YTDLP_PY", sys.executable)
        try:
            before = subprocess.run([py, "-m", "yt_dlp", "--version"], capture_output=True, text=True, timeout=30, creationflags=NOFLAGS).stdout.strip()
        except Exception as e:
            before = f"? ({e})"
        try:
            def _pip(extra=()):
                cmd = [py, "-m", "pip", "install", "-U", *extra, "yt-dlp[default]"]  # ejs-20261111: [default] pulls yt-dlp-ejs
                if pre and "--pre" not in cmd: cmd.insert(-1, "--pre")
                return subprocess.run(cmd, capture_output=True, text=True, timeout=180, creationflags=NOFLAGS)
            r = _pip(("--pre",) if pre else ())
            # PEP 668 / managed envs: retry --user then --break-system-packages (server/Termux only; never fails boot)
            err = (r.stderr or r.stdout or "")
            if r.returncode and ("externally-managed" in err or "break-system-packages" in err):
                r = _pip((("--pre",) if pre else ()) + ("--user",))
                err = (r.stderr or r.stdout or "")
            if r.returncode and ("externally-managed" in err or "break-system-packages" in err):
                r = _pip((("--pre",) if pre else ()) + ("--break-system-packages",))
            after = subprocess.run([py, "-m", "yt_dlp", "--version"], capture_output=True, text=True, timeout=30, creationflags=NOFLAGS).stdout.strip()
            note = f"yt-dlp {before} -> {after}" + (" (pre)" if pre else "") + (" (updated)" if after and after != before else " (already current or unchanged)")
            if r.returncode:
                note += f" pip_rc={r.returncode} {(r.stderr or r.stdout or '')[-200:]}"
            print(note, flush=True)
            _ytdlp_state["ver"] = after or before
            try:
                (ROOT / "ytdlp_version.txt").write_text(f"{after or before}\n{note}\n")
            except Exception:
                pass
            return after or before
        except Exception as e:
            print(f"yt-dlp auto-update skipped: {e}", flush=True)
            return None
    if background:
        threading.Thread(target=run, daemon=True, name="ytdlp-update").start()
        return None
    return run()

_ytdlp_state = {"ok": True, "ver": "", "heal": "", "heal_ts": 0}
_SMOKE_VID = cfg.get("YTDLP_SMOKE_ID", "jNQXAC9IVRw")  # short stable public video

def ytdlp_smoke(vid=None):
    """Resolve bestaudio URL via yt-dlp subprocess; ads are never in this pipe — failure means extractor rot."""
    vid = vid or _SMOKE_VID
    if not re.match(r"^[A-Za-z0-9_-]{11}$", vid or ""):
        vid = _SMOKE_VID
    try:
        u = subprocess.run(YTDLP + ["-f", "bestaudio/bestaudio*", "-g", "--no-warnings", f"https://www.youtube.com/watch?v={vid}"],
                           capture_output=True, text=True, timeout=90, creationflags=NOFLAGS)
        lines = [x for x in (u.stdout or "").splitlines() if x.strip().startswith("http")]
        return bool(u.returncode == 0 and lines), (u.stderr or u.stdout or "")[-400:]
    except Exception as e:
        return False, str(e)

def _ytdlp_heal_note(msg):
    _ytdlp_state["heal"] = msg
    _ytdlp_state["heal_ts"] = time.time()
    print(msg, flush=True)
    try:
        (ROOT / "ytdlp_heal.txt").write_text(f"{int(_ytdlp_state['heal_ts'])}\n{msg}\n")
    except Exception:
        pass

# ---- v65: self-heal for YouTube changes — on-demand + daily yt-dlp nightly update, in-process re-import ----
_YU_LOCK = threading.Lock()
_YU_FILE = ROOT / "ytdlp_update.json"
try: _yu = json.loads(_YU_FILE.read_text())
except Exception: _yu = {}
def _ytdlp_cli_ver(py):
    try: return subprocess.run([py, "-m", "yt_dlp", "--version"], capture_output=True, text=True, timeout=30, creationflags=NOFLAGS).stdout.strip()
    except Exception as e: return f"? ({e})"
def ytdlp_status():
    try:
        import yt_dlp as _y; mod = _y.version.__version__; ch = getattr(_y.version, "CHANNEL", "") or ""
    except Exception as e: mod, ch = f"? ({e})"[:80], ""
    return {"ver": _ytdlp_state.get("ver") or mod, "module": mod, "channel": ch, "ok": _ytdlp_state.get("ok", True), "heal": _ytdlp_state.get("heal", ""),
            "last_update_ts": _yu.get("ts", 0), "last_note": _yu.get("note", ""), "last_reason": _yu.get("reason", ""), "busy": _YU_LOCK.locked(), "auto": "daily" if YT_AUTO else "off", "ffmpeg": HAVE_FFMPEG}
def ytdlp_update_nightly(reason="manual"):
    """Try yt-dlp's own updater (-U --update-to nightly: works for standalone/zip installs); pip installs refuse that,
    so fall back to pip -U --pre (PyPI publishes nightly builds as pre-releases). Then re-import the module in-process and smoke-test."""
    import sys, importlib
    if not _YU_LOCK.acquire(blocking=False): return dict(ytdlp_status(), ok=False, busy=True, note="update already running")
    try:
        py = cfg.get("YTDLP_PY", sys.executable); t0 = time.time(); before = _ytdlp_cli_ver(py); how = ""
        try:
            r = subprocess.run([py, "-m", "yt_dlp", "-U", "--update-to", "nightly"], capture_output=True, text=True, timeout=180, creationflags=NOFLAGS)
            out = (r.stdout or "") + (r.stderr or ""); how = "self-update"
            need_pip = r.returncode != 0 or "pip" in out.lower() or "not supported" in out.lower()
        except Exception as e: out, need_pip = str(e), True
        pip_rc = None
        if need_pip:
            how = "pip --pre (nightly)"
            def _pip(extra=()):
                return subprocess.run([py, "-m", "pip", "install", "-U", "--pre", *extra, "yt-dlp[default]"], capture_output=True, text=True, timeout=300, creationflags=NOFLAGS)
            p = _pip(); err = (p.stderr or p.stdout or "")
            if p.returncode and ("externally-managed" in err or "break-system-packages" in err): p = _pip(("--user",)); err = (p.stderr or p.stdout or "")
            if p.returncode and ("externally-managed" in err or "break-system-packages" in err): p = _pip(("--break-system-packages",)); err = (p.stderr or p.stdout or "")
            pip_rc = p.returncode
        after = _ytdlp_cli_ver(py)
        # re-import in-process so the running server uses the new extractors without a restart
        reimported = False
        try:
            try:  # ytfix-20261110: undo yt-dlp's urllib3 patch first, or the re-import wraps it twice and every lookup fails
                import urllib3.util.url as _u3
                while type(getattr(_u3, "_PERCENT_RE", None)).__name__ == "Urllib3PercentREOverride": _u3._PERCENT_RE = _u3._PERCENT_RE.re
            except Exception: pass
            for m in [m for m in list(sys.modules) if m == "yt_dlp" or m.startswith("yt_dlp.")]: del sys.modules[m]
            importlib.invalidate_caches(); import yt_dlp as _y; mod = _y.version.__version__; ch = getattr(_y.version, "CHANNEL", ""); reimported = True
        except Exception as e: mod, ch = f"? ({e})"[:80], ""
        try: ok, serr = ytdlp_smoke()
        except Exception as e: ok, serr = False, str(e)
        _ytdlp_state["ok"] = ok; _ytdlp_state["ver"] = after or mod
        note = f"yt-dlp {before} -> {after} via {how}" + (" (updated)" if after and after != before else " (already current)") + ("" if pip_rc in (None, 0) else f" pip_rc={pip_rc}")
        _yu.update({"ts": int(time.time()), "note": note, "reason": reason, "before": before, "after": after, "module": mod, "channel": ch, "smoke_ok": ok, "secs": round(time.time() - t0, 1)})
        try: _YU_FILE.write_text(json.dumps(_yu)); (ROOT / "ytdlp_version.txt").write_text(f"{after}\n{note}\n")
        except Exception: pass
        print(note, flush=True)
        return {"ok": bool(after) and not after.startswith("?"), "before": before, "after": after, "module": mod, "channel": ch, "reimported": reimported, "smoke_ok": ok,
                "smoke_err": (serr or "")[:160] if not ok else "", "how": how, "note": note, "ts": _yu["ts"], "secs": _yu["secs"]}
    finally:
        _YU_LOCK.release()
def ytdlp_daily():
    def loop():
        time.sleep(int(cfg.get("YTDLP_DAILY_DELAY", "180")))
        while True:
            try:
                if YT_AUTO and time.time() - float(_yu.get("ts", 0) or 0) >= 86400: ytdlp_update_nightly("daily")
            except Exception as e: print(f"yt-dlp daily update error: {e}", flush=True)
            time.sleep(1800)
    threading.Thread(target=loop, daemon=True, name="ytdlp-daily").start()

def ytdlp_watch(interval=None):
    """Periodic smoke resolve; on fail force pip -U (then optional --pre) and log extractor update pulled."""
    interval = int(interval or cfg.get("YTDLP_SMOKE_SEC", "3600") or 3600)
    def loop():
        time.sleep(60)
        while True:
            try:
                ok, err = ytdlp_smoke()
                _ytdlp_state["ok"] = ok
                if ok:
                    print("yt-dlp smoke OK", flush=True)
                else:
                    print(f"yt-dlp smoke FAIL: {err}", flush=True)
                    if not YT_AUTO:
                        _ytdlp_state["ok"] = False
                        _ytdlp_heal_note("extractor looks broken; auto-update is off - run scripts/update-ytdlp (or the in-app update) then restart")
                        time.sleep(max(300, interval)); continue
                    ensure_ytdlp(background=False)
                    ok2, _ = ytdlp_smoke()
                    if not ok2:
                        ensure_ytdlp(background=False, pre=True)
                        ok2, _ = ytdlp_smoke()
                    _ytdlp_state["ok"] = ok2
                    _ytdlp_heal_note("extractor update pulled" if ok2 else "extractor still broken after update — restart or check network")
            except Exception as e:
                print(f"yt-dlp watch error: {e}", flush=True)
            time.sleep(max(300, interval))
    threading.Thread(target=loop, daemon=True, name="ytdlp-watch").start()


state = {"proc": None, "title": None}
def public_url():
    return URLFILE.read_text().strip() if URLFILE.exists() else f"http://127.0.0.1:{PORT}"
_scache = {}  # play2-20261110
_sf_lk = threading.Lock(); _sf = {}
def _single(key, fn):
    """Singleflight: concurrent identical calls (e.g. prefetch + play, double-tap search) share one yt-dlp run."""
    with _sf_lk:
        ent = _sf.get(key)
        if ent is None: ent = _sf[key] = [threading.Event(), None, None]; lead = True
        else: lead = False
    if not lead:
        ent[0].wait(90)
        if ent[2] is not None: raise ent[2]
        return ent[1]
    try: ent[1] = fn(); return ent[1]
    except Exception as e: ent[2] = e; raise
    finally:
        with _sf_lk: _sf.pop(key, None)
        ent[0].set()
# ---- ms-v77: live / upcoming streams are unsupported ----
# The player's audio paths (/audio blob, /stream mp3) need a finite media file; a live HLS manifest fails with
# MEDIA_ERR_SRC_NOT_SUPPORTED (code 4). The decision uses yt-dlp's own fields (live_status / is_live) and, for URLs already in
# the disk cache, the delivered stream type (HLS live manifest). Titles are never used, so "24/7", "radio" or "LIVE concert"
# recordings stay playable. live_status was_live / post_live / not_live = recording = allowed.
_LIVE_BAD = ("is_live", "is_upcoming")
_LIVE = {}  # id -> (live_status, ts)
LIVE_TTL = 1800  # a stream that ends becomes was_live; re-check after 30 min
class LiveUnsupported(RuntimeError):
    def __init__(self, status="is_live"): super().__init__(f"live_unsupported:{status}"); self.status = status
def _live_status(e):
    if not isinstance(e, dict): return ""
    st = e.get("live_status") or ""
    if not st and e.get("is_live") is True: st = "is_live"
    return st
def _live_note(vid, st):
    if not vid or not st: return
    if st in _LIVE_BAD:
        if len(_LIVE) > 5000: _LIVE.clear()
        _LIVE[vid] = (st, time.time())
    else: _LIVE.pop(vid, None)
def live_known(vid):
    c = _LIVE.get(vid)
    return c[0] if c and time.time() - c[1] < LIVE_TTL else ""
def _live_url(u): return bool(u) and ("/manifest/hls_playlist/" in u or "/yt_live_broadcast/" in u)
_UPCOMING_ERR = re.compile(r"live event will begin|premieres? in|is_upcoming|this live event", re.I)
def live_check(vid, timeout=10):
    """Cheap metadata-only probe (no format selection). Returns live_status ('' if unknown)."""
    k = live_known(vid)
    if k: return k
    import yt_dlp
    res = {}
    def go():
        try:
            with yt_dlp.YoutubeDL({"quiet": True, "no_warnings": True, "skip_download": True, "noplaylist": True}) as ydl:
                res["i"] = ydl.extract_info(f"https://www.youtube.com/watch?v={vid}", download=False, process=False)
        except Exception as e: res["e"] = str(e)
    th = threading.Thread(target=go, daemon=True); th.start(); th.join(timeout)
    st = _live_status(res.get("i")) or ("is_upcoming" if _UPCOMING_ERR.search(res.get("e", "")) else "")
    _live_note(vid, st); return st
def _thumb(e):
    th = e.get("thumbnails") or []
    return th[-1]["url"] if th and th[-1].get("url") else ""
# --- speed-20261110: search results on disk (6h) so a restart doesn't make every search cold again ---
_SDIR = ROOT / "lcache" / "search"; _SDIR.mkdir(parents=True, exist_ok=True)
SEARCH_DISK_TTL = int(cfg.get("SEARCH_DISK_TTL", "21600"))
def _sdisk_path(key):
    import hashlib as _h
    return _SDIR / (_h.sha1(repr(key).encode("utf-8")).hexdigest() + ".json")
def _sdisk_get(key):
    try:
        f = _sdisk_path(key)
        if f.exists() and time.time() - f.stat().st_mtime < SEARCH_DISK_TTL: return json.loads(f.read_text(encoding="utf-8"))
    except Exception: pass
    return None
def _sdisk_put(key, res):
    try:
        f = _sdisk_path(key); t = f.with_suffix(".tmp"); t.write_text(json.dumps(res), encoding="utf-8"); os.replace(t, f)
        if secrets.randbelow(40) == 0:
            for o in _SDIR.glob("*.json"):
                if time.time() - o.stat().st_mtime > SEARCH_DISK_TTL: o.unlink()
    except Exception: pass
# --- search-fast-20261111: InnerTube JSON search first (1 request, no HTML scrape); yt-dlp stays the fallback ---
_ITV = "2.20241111.01.00"
def _it_txt(o):
    if not isinstance(o, dict): return ""
    if "simpleText" in o: return o["simpleText"] or ""
    return "".join(r.get("text", "") for r in (o.get("runs") or []))
def _it_dur(s):
    try:
        p = [int(x) for x in s.split(":")]; v = 0
        for x in p: v = v * 60 + x
        return v
    except Exception: return None
def _it_items(j):
    secs = (((j.get("contents") or {}).get("twoColumnSearchResultsRenderer") or {}).get("primaryContents") or {}).get("sectionListRenderer", {}).get("contents") or []
    for s in secs:
        for it in (s.get("itemSectionRenderer") or {}).get("contents") or []: yield it
# lat-20261111: YouTube search over a reused HTTPS connection (no new TLS handshake per search) with gzip
# (a full browser User-Agent is what makes YouTube compress: ~70 KB instead of ~650 KB per search). Falls back to a fresh connection.
import http.client as _hc, gzip as _gz, queue as _qu
_YTI_POOL = _qu.LifoQueue(maxsize=2)
_YTI_UA = "Mozilla/5.0 (Linux; Android 10; K) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Mobile Safari/537.36"
def _yti_post(path, body, timeout):
    hdr = {"Content-Type": "application/json", "User-Agent": _YTI_UA, "Accept-Encoding": "gzip", "X-YouTube-Client-Name": "1", "X-YouTube-Client-Version": _ITV}
    for attempt in (0, 1):
        c = None
        while attempt == 0:
            try: c, _ts = _YTI_POOL.get_nowait()
            except Exception: c = None; break
            if time.time() - _ts < 45: break  # an idle socket can be dropped silently by NAT/Wi-Fi: never reuse an old one
            try: c.close()
            except Exception: pass
            c = None
        fresh = c is None
        if fresh: c = _hc.HTTPSConnection("www.youtube.com", timeout=timeout)
        try:
            if c.sock is not None: c.sock.settimeout(timeout)
            c.request("POST", path, body=body, headers=hdr); r = c.getresponse(); d = r.read()
            if r.status >= 400: c.close(); raise urllib.error.HTTPError("https://www.youtube.com" + path, r.status, r.reason, r.headers, None)
            if (r.getheader("Content-Encoding") or "").lower() == "gzip": d = _gz.decompress(d)
            if (r.getheader("Connection") or "").lower() != "close":
                try: _YTI_POOL.put_nowait((c, time.time()))
                except Exception: c.close()
            else: c.close()
            return d
        except urllib.error.HTTPError: raise
        except Exception:
            try: c.close()
            except Exception: pass
            if fresh: raise
    raise RuntimeError("yti")
def _fast_search(q, timeout=8, gl="", hl="en"):
    ctx = {"clientName": "WEB", "clientVersion": _ITV, "hl": hl}
    if gl: ctx["gl"] = gl
    body = json.dumps({"context": {"client": ctx}, "query": q}).encode()
    j = json.loads(_yti_post("/youtubei/v1/search?prettyPrint=false", body, timeout).decode("utf-8", "replace"))  # lat-20261111
    out = []
    for it in _it_items(j):
        v = it.get("videoRenderer")
        if v:
            vid = v.get("videoId") or ""
            live = bool(v.get("upcomingEventData")) or any(((b.get("metadataBadgeRenderer") or {}).get("style") or "").endswith("LIVE_NOW") for b in (v.get("badges") or []))
            for ov in v.get("thumbnailOverlays") or []:
                st = (ov.get("thumbnailOverlayTimeStatusRenderer") or {}).get("style")
                if st in ("LIVE", "UPCOMING"): live = True
            ch = _it_txt(v.get("ownerText")) or _it_txt(v.get("longBylineText"))
            lt = _it_txt(v.get("lengthText"))
            out.append({"id": vid, "title": _it_txt(v.get("title")) or "?", "duration": _it_dur(lt) if lt else None, "channel": ch,
                        "live_status": ("is_upcoming" if v.get("upcomingEventData") else "is_live") if live else None})
            continue
        lk = it.get("lockupViewModel")
        if lk and "PLAYLIST" in (lk.get("contentType") or "") or (lk and (lk.get("contentId") or "")[:2] in ("RD", "PL", "OL")):
            cid = lk.get("contentId") or ""
            md = ((lk.get("metadata") or {}).get("lockupMetadataViewModel") or {})
            title = ((md.get("title") or {}).get("content")) or "?"
            cnt = None
            try:
                s = json.dumps(lk.get("contentImage") or {})
                m = re.search(r'"text": "(\d[\d,]*) (?:videos|songs|episodes)"', s)
                if m: cnt = int(m.group(1).replace(",", ""))
            except Exception: pass
            th = ""
            try:
                s = json.dumps(lk.get("contentImage") or {}); m = re.search(r'"url": "(https://i\.ytimg\.com/[^"]+)"', s); th = m.group(1) if m else ""
            except Exception: pass
            out.append({"id": cid, "ie_key": "YoutubeTab", "url": "https://www.youtube.com/playlist?list=" + cid, "title": title, "playlist_count": cnt,
                        "channel": "", "thumbnails": [{"url": th}] if th else []})
    return {"entries": out}
SEARCH_FAST = cfg.get('SEARCH_FAST', '1') not in ('0', 'false', 'no', 'off')
def search(q, n=8):
    q = (q or "").strip()
    if not q:
        return []
    return _single(("s", q.lower(), n), lambda: _search(q, n))
def _search(q, n=8):
    """Videos + mixes/playlists from the real YouTube results page (cached 30 min). n<=1 -> fast single-video resolve."""
    q = (q or "").strip()
    if not q:
        return []
    key = (q.lower(), n); c = _scache.get(key)
    if c and time.time() - c[1] < 1800:
        _search_warm(c[0]); return c[0]
    _d = _sdisk_get(key)  # speed-20261110
    if _d: _scache[key] = (_d, time.time()); _search_warm(_d); return _d
    if n <= 1: args = [f"ytsearch1:{q}", "--flat-playlist", "-J", "--no-warnings"]
    else: args = ["https://www.youtube.com/results?" + urllib.parse.urlencode({"search_query": q}), "--flat-playlist", "-J", "--no-warnings", "--playlist-end", str(max(n, 8) + 6)]
    _pe = args[args.index("--playlist-end") + 1] if "--playlist-end" in args else None  # play2-20261110: in-process first
    out = None
    if SEARCH_FAST:  # search-fast-20261111
        _t0 = time.time()
        try:
            _fr = _fast_search(q, timeout=6)
            if any(VID.match(e.get('id') or '') for e in _fr.get('entries') or []): out = json.dumps(_fr)
            print(f"search fast ms={int((time.time() - _t0) * 1000)} n={len(_fr.get('entries') or [])}", flush=True)
        except Exception as _e: print(f"search fast fail {type(_e).__name__}: {str(_e)[:80]} -> yt-dlp", flush=True)
    if out is None: out = _flat_out(args[0], _pe, 30, lambda left: subprocess.run(YTDLP + args, capture_output=True, text=True, timeout=max(5, left), creationflags=NOFLAGS, encoding="utf-8", errors="replace").stdout)
    res = []
    raw = json.loads(out or '{"entries":[]}') if (out or "").strip() else {}
    if not isinstance(raw, dict):
        raw = {}
    for e in (raw.get("entries") or []):
        i = e.get("id") or ""
        if e.get("ie_key") == "YoutubeTab" or (e.get("url") or "").find("list=") > 0:
            if not re.match(r"^(RD|PL|OL|UU)[A-Za-z0-9_-]{8,}$", i) or n <= 1: continue
            seed = i[2:] if i.startswith("RD") and VID.match(i[2:]) else None
            res.append({"id": None, "list": i, "kind": "mix" if i.startswith("RD") else "playlist", "seed": seed, "thumb": "" if seed else _thumb(e),
                        "title": e.get("title", "?"), "dur": None, "channel": e.get("channel") or e.get("uploader") or ("YouTube Mix" if seed else "Playlist"), "count": e.get("playlist_count")})
        elif VID.match(i):
            ls = _live_status(e); _live_note(i, ls)
            if ls in _LIVE_BAD: continue  # ms-v77: live/upcoming streams are not playable here
            res.append({"id": i, "title": e.get("title", "?"), "dur": e.get("duration"), "channel": e.get("channel") or e.get("uploader") or ""})
    res = res[:max(n, 1) + 4] if n > 1 else res[:1]
    if len(_scache) > 300: _scache.clear()
    if res: _scache[key] = (res, time.time()); _sdisk_put(key, res)  # speed-20261110
    _search_warm(res)
    return res
def _search_warm(res):
    """speed-20261113: resolve stream URLs for the first few hits so a click starts in ~0.1 s, not ~2 s."""
    ids = [x["id"] for x in (res or []) if isinstance(x, dict) and VID.match(x.get("id") or "")][:3]
    if not ids:
        return
    try:
        # Prefer the new first hit (audio, then a full video-rung warm at the default
        # 720p pick) so a later search is not stuck behind leftover warms.
        jobs = [(ids[0], "std"), (ids[0], "vw")] + [(i, "std") for i in ids[1:]]
        _warm_prefer(jobs)
    except Exception:
        pass
_lcache = {}
# backlog-20261112: mix/playlist lists were the slowest thing under load (100 users: p50 18 s, 65% timeouts) - every
# request ran its own in-process yt-dlp list fetch, the same list was fetched in parallel, and empty lists were never
# cached. Now: one fetch per list at a time (others wait for it), at most LIST_MAX (2) list fetches at once
# (8 s wait, then an empty answer the player already handles), empty results cached for 10 min.
_LLK = {}; _LLKL = threading.Lock(); _LLS = threading.BoundedSemaphore(max(1, int(cfg.get("LIST_MAX", "2") or 2)))
def ytlist(lid):
    c = _lcache.get(lid)
    if c and time.time() - c[1] < (1800 if c[0] else 600): return c[0]
    with _LLKL:
        if len(_LLK) > 500: _LLK.clear()
        lk = _LLK.setdefault(lid, threading.Lock())
    with lk:
        c = _lcache.get(lid)
        if c and time.time() - c[1] < (1800 if c[0] else 600): return c[0]
        url = f"https://www.youtube.com/watch?v={lid[2:]}&list={lid}" if lid.startswith("RD") and len(lid) == 13 else f"https://www.youtube.com/playlist?list={lid}"
        if not _LLS.acquire(timeout=8): return []
        try: L = flat(url, 100)
        finally: _LLS.release()
        if len(_lcache) > 200: _lcache.clear()
        _lcache[lid] = (L or [], time.time())
        return L
_art = {}
VID = re.compile(r"^[A-Za-z0-9_-]{11}$")
def resolve(x):
    if VID.match(x): return x
    m = re.search(r"(?:v=|youtu\.be/|/shorts/)([A-Za-z0-9_-]{11})", x)
    if m: return m.group(1)
    r = search(x, 1); return r[0]["id"] if r else None
def audio_url(vid):
    u = subprocess.run(YTDLP + ["-f", "bestaudio", "-g", "--no-warnings", f"https://www.youtube.com/watch?v={vid}"],
                       capture_output=True, text=True, timeout=60, creationflags=NOFLAGS).stdout.strip().splitlines()[0]
    if _live_url(u): _live_note(vid, "is_live"); raise LiveUnsupported("is_live")  # ms-v77: no endless ffmpeg on a live HLS
    return u
_TITLE = {}
def _title_fast(vid):  # play2b-20261110
    try:
        u = "https://www.youtube.com/oembed?" + urllib.parse.urlencode({"url": f"https://www.youtube.com/watch?v={vid}", "format": "json"})
        j = json.loads(urllib.request.urlopen(urllib.request.Request(u, headers={"User-Agent": "Mozilla/5.0"}), timeout=4).read().decode("utf-8", "replace"))
        return str(j.get("title") or "")
    except Exception: return ""
def title_of(vid):
    """Cached title lookup. Never block radio/hot paths on a fresh yt-dlp title scrape."""
    if not vid: return ""
    if vid in _TITLE: return _TITLE[vid]
    # Prefer metadata we already paid for
    try:
        if vid in _seed_meta and _seed_meta[vid].get("title"):
            _TITLE[vid] = _seed_meta[vid]["title"]; return _TITLE[vid]
    except Exception: pass
    try:
        # urls cache / art side tables sometimes hold titles indirectly — skip
        pass
    except Exception: pass
    t = _title_fast(vid)  # play2b-20261110: oEmbed, no yt-dlp process
    if t:
        _TITLE[vid] = t; return t
    # Soft: short timeout; on failure remember empty so we do not stampede
    try:
        t = subprocess.run(YTDLP + ["--get-title", "--no-warnings", f"https://www.youtube.com/watch?v={vid}"],
                          capture_output=True, text=True, timeout=8, creationflags=NOFLAGS).stdout.strip()
        _TITLE[vid] = t or vid
    except Exception:
        _TITLE[vid] = vid
    if len(_TITLE) > 4000:
        for k in list(_TITLE.keys())[:1000]: _TITLE.pop(k, None)
    return _TITLE[vid]
def local_stop():
    p = state["proc"]
    if p and p.poll() is None: p.kill()
    state["proc"] = None; state["title"] = None
def local_play(q):
    vid = resolve(q)
    if not vid: return "not found"
    local_stop()  # PC speaker playback permanently disabled (headless machine): return a phone link instead
    return f"PC playback disabled - play on phone: {public_url()}/?k={KEY}&play={vid}"
def status():
    p = state["proc"]
    return "server ok (PC playback disabled)"
PAGE = """<!doctype html><meta name=viewport content="width=device-width,initial-scale=1"><title>Music</title>
<style>body{font-family:sans-serif;max-width:640px;margin:auto;padding:8px}li{margin:8px 0}</style>
<form><input type=hidden name=k value="%(k)s"><input name=q value="%(q)s" style="width:70%%"><button>Search</button></form>
<p>%(st)s</p><audio id=a controls autoplay style="width:100%%" src="%(src)s"></audio><ul>%(rows)s</ul>"""
def music_cmd(cmd, arg):
    base = public_url(); cmd = cmd.lower().lstrip("/")
    if cmd == "play": return local_play(arg) if arg else "usage: /play <song or url>"
    if cmd in ("stop", "mstop"): local_stop(); return "music stopped"
    if cmd in ("status", "mstatus"): return status()
    if cmd in ("link", "mlink"): return f"{base}/?k={KEY}"
    if cmd in ("search", "msearch"):
        if not arg: return "usage: /msearch <query>"
        rs = search(arg, 5)
        return "\n\n".join(f"{x['title']}\n/play {x['id']}\nlisten: {base}/stream?k={KEY}&id={x['id']}\ndownload: {base}/dl?k={KEY}&id={x['id']}" for x in rs) or "nothing found"
    if cmd in ("dl", "mdl", "stream"):
        v = resolve(arg) if arg else None
        return f"{base}/{'stream' if cmd=='stream' else 'dl'}?k={KEY}&id={v}" if v else "usage: /mdl <song or url>"
    return "music: /play q | /mstop | /mstatus | /msearch q | /mlink | /mdl q"

FMTS = {"hi": "bestaudio[acodec=opus]/bestaudio", "std": "bestaudio[ext=m4a]/bestaudio", "video": "bestvideo[vcodec^=avc1][ext=mp4][height<=720][protocol^=http]/best[ext=mp4][height<=720][protocol^=http]/18/bestvideo[height<=720][protocol^=http]"}
_ucache = {}  # (vid,q) -> {url, headers, expire, cached_at}
UCACHE_DIR = ROOT / "lcache" / "urls"; UCACHE_DIR.mkdir(parents=True, exist_ok=True)
_VHEIGHTS = (144, 240, 360, 480, 720, 1080, 1440)  # v1440-20261111
def vfmt(q):
    # resfix: q = "v<height>[a|h]". Video-only DASH renditions (the audio element carries the sound): fMP4 that plays and seeks over Range.
    # "a" = AV1 when the client says it decodes it smoothly (about half the bytes of H.264 at the same height), else H.264/avc1.
    # v1440-20261111: 1440p is almost never avc1; prefer exact-height AV1 (if the client asked) then VP9 (271/308-class), then the usual <=h ladder.
    m = re.match(r"v(\d+)([ah]?)$", q or ""); h = int(m.group(1)) if m and int(m.group(1)) in _VHEIGHTS else 360
    av1 = bool(m and m.group(2) == "a")
    ladder = ((f"bv*[vcodec^=av01][height<={h}][ext=mp4][protocol=https]/" if av1 else "")
              + f"bv*[vcodec^=avc1][height<={h}][ext=mp4][protocol=https]/b[ext=mp4][height<={h}][protocol=https]/"
              + f"bv*[height<={h}][ext=mp4][protocol=https]/bv*[height<={h}][protocol^=http]/18")
    if h >= 1440:
        exact = ((f"bv*[height={h}][vcodec^=av01][protocol^=http]/" if av1 else "")
                 + f"bv*[height={h}][vcodec^=vp09][protocol^=http]/bv*[height={h}][vcodec^=vp9][protocol^=http]/"
                 + f"bv*[height={h}][protocol^=http]/")
        return exact + ladder
    return ladder
_VINFO = {}  # (vid, c) -> {"t": ts, "res": {h: {...}}}
def _vpick(fmts, h, c):
    # v1440-20261111: 144-1080 stay mp4-only (avc1 preference, AV1 when c=a). 1440+ also allows webm VP9 (271/308) because avc1 1440 is almost never offered.
    def _ok(f, webm):
        if not (f.get("url") and f.get("protocol") in ("https", "http") and (f.get("vcodec") or "none") != "none"): return False
        ext = f.get("ext") or ""
        if not (ext == "mp4" or (webm and ext == "webm")): return False
        return 0 < (f.get("height") or 0) <= h
    ok = [f for f in fmts if _ok(f, h >= 1440)]
    def _pick(pool):
        return max(pool, key=lambda f: ((f.get("height") or 0), (f.get("tbr") or 0))) if pool else None
    if h >= 1440:
        at = [f for f in ok if (f.get("height") or 0) >= 1400]
        if at:
            vc = lambda f: (f.get("vcodec") or "")
            if c == "a":
                pool = [f for f in at if vc(f).startswith("av01")] or [f for f in at if vc(f).startswith("vp")] or at
            else:
                pool = [f for f in at if vc(f).startswith("avc1")] or [f for f in at if vc(f).startswith("vp")] or at
            return _pick(pool)
    pool = ([f for f in ok if (f.get("vcodec") or "").startswith("av01")] if c == "a" else []) or [f for f in ok if (f.get("vcodec") or "").startswith("avc1")] or ok
    return _pick(pool)
def _vwarm(vid, c, need=1080):
    """One yt-dlp extraction resolves every rendition (144..1440) into the URL cache, so switching quality later costs no yt-dlp wait."""
    k = (vid, c); x = _VINFO.get(k)
    if x and time.time() - x["t"] < 3 * 3600: return x
    def go():
        _bg_blocked(vid)  # play4-20261111
        info = _ydl_video_info(vid, c, need=need)  # speed-20261113: merge vis+def if 1080/720 avc1 is missing
        ls = _live_status(info); _live_note(vid, ls)
        if ls in _LIVE_BAD: raise LiveUnsupported(ls)
        fm = info.get("formats") or []; res = {}
        for h in _VHEIGHTS:  # v1440-20261111
            f = _vpick(fm, h, c)
            if not f: continue
            # speed-20261113: never label a 360/480 file as 720/1080 (was happening when
            # a client/helper list lacked the higher avc1 rung, or fell through to fmt 18).
            if (f.get("height") or 0) < h: continue
            hdr = {kk: str(vv) for kk, vv in dict(f.get("http_headers") or info.get("http_headers") or {}).items()}
            if not (_ucache.get((vid, f"v{h}{c}")) or {}).get("url"): _ucache_save(vid, f"v{h}{c}", f["url"], hdr)
            res[str(h)] = {"fmt": f.get("format_id"), "h": f.get("height"), "vcodec": (f.get("vcodec") or "").split(".")[0],
                           "tbr": round(f.get("tbr") or f.get("vbr") or 0), "size": f.get("filesize") or f.get("filesize_approx")}
        r = {"t": time.time(), "res": res}; _VINFO[k] = r; return r
    return _single(("vw", vid, c), go)
def _vinfo_from(vid, info):
    """latency2-20261110: fill the video-rendition URL cache + _VINFO from an extraction done for the audio."""
    fm = info.get("formats") or []
    for c in ("h", "a"):
        if (vid, c) in _VINFO and time.time() - _VINFO[(vid, c)]["t"] < 3 * 3600: continue
        res = {}
        for h in _VHEIGHTS:  # v1440-20261111
            f = _vpick(fm, h, c)
            if not f: continue
            # speed-20261113: never label a 360/480 file as 720/1080 (was happening when
            # a client/helper list lacked the higher avc1 rung, or fell through to fmt 18).
            if (f.get("height") or 0) < h: continue
            hdr = {kk: str(vv) for kk, vv in dict(f.get("http_headers") or info.get("http_headers") or {}).items()}
            if not (_ucache.get((vid, f"v{h}{c}")) or {}).get("url"): _ucache_save(vid, f"v{h}{c}", f["url"], hdr)
            res[str(h)] = {"fmt": f.get("format_id"), "h": f.get("height"), "vcodec": (f.get("vcodec") or "").split(".")[0],
                           "tbr": round(f.get("tbr") or f.get("vbr") or 0), "size": f.get("filesize") or f.get("filesize_approx")}
        if res: _VINFO[(vid, c)] = {"t": time.time(), "res": res}
def _url_expire(u):
    try:
        q = urllib.parse.parse_qs(urllib.parse.urlsplit(u).query)
        e = q.get("expire") or q.get("Expires") or q.get("expires")
        if e: return int(e[0])
    except Exception: pass
    return 0
def _ucache_path(vid, q):
    safe = re.sub(r"[^A-Za-z0-9_-]+", "_", f"{vid}_{q}")
    return UCACHE_DIR / f"{safe}.json"
UC_MARGIN = int(cfg.get("UCACHE_MARGIN", "900"))  # perf-20261112: reuse a stream URL until ~15 min before googlevideo's expire
# speed-20261113: YouTube itag -> pixel height. Used to reject a 360p/fmt-18 URL cached as 720/1080.
_ITAG_H = {"18": 360, "22": 720, "160": 144, "133": 240, "134": 360, "135": 480, "136": 720, "137": 1080,
           "264": 1440, "266": 2160, "298": 720, "299": 1080, "394": 144, "395": 240, "396": 360, "397": 480,
           "398": 720, "399": 1080, "400": 1440, "278": 144, "242": 240, "243": 360, "244": 480, "247": 720,
           "248": 1080, "271": 1440, "313": 2160, "302": 720, "303": 1080, "308": 1440, "315": 2160,
           "91": 144, "92": 240, "93": 360, "94": 480, "95": 720, "96": 1080}
def _q_video_h(q):
    m = re.match(r"v(\d+)([ah]?)$", q or "")
    return int(m.group(1)) if m and int(m.group(1)) in _VHEIGHTS else None
def _url_itag_h(url):
    try:
        itag = (urllib.parse.parse_qs(urllib.parse.urlsplit(url).query).get("itag") or [""])[0]
    except Exception:
        return None
    return _ITAG_H.get(str(itag))
def _url_too_low(url, q):
    """True when a cached/selected stream is clearly below the requested ladder rung (e.g. fmt 18 as 720p)."""
    claim, actual = _q_video_h(q), _url_itag_h(url)
    return bool(claim and actual and actual <= claim - 120)
def _ucache_load(vid, q):
    key = (vid, q); c = _ucache.get(key)
    if c and c.get("url") and (c.get("expire") or 0) > time.time() + UC_MARGIN:
        if _live_url(c["url"]): _live_note(vid, "is_live"); _ucache_invalidate(vid, q); raise LiveUnsupported("is_live")
        if _url_too_low(c["url"], q): _ucache_invalidate(vid, q); c = None
        else: return c
    p = _ucache_path(vid, q)
    if p.exists():
        try:
            c = json.loads(p.read_text())
            if c.get("url") and (c.get("expire") or 0) > time.time() + UC_MARGIN:
                if _live_url(c["url"]): _live_note(vid, "is_live"); _ucache_invalidate(vid, q); raise LiveUnsupported("is_live")  # ms-v77: pre-v77 cached live manifest
                if _url_too_low(c["url"], q):
                    _ucache_invalidate(vid, q)
                else:
                    _ucache[key] = c; return c
        except Exception: pass
    return None
def _ucache_save(vid, q, url, headers):
    if _url_too_low(url, q):
        # keep the URL for this one response, but do not remember it as a higher rung
        exp = _url_expire(url) or (int(time.time()) + 3600 + UC_MARGIN)
        return {"url": url, "headers": headers or {}, "expire": exp, "cached_at": int(time.time()), "vid": vid, "q": q}
    exp = _url_expire(url) or (int(time.time()) + 3600 + UC_MARGIN)  # perf-20261112: no expire= in the URL -> keep ~1 h
    c = {"url": url, "headers": headers or {}, "expire": exp, "cached_at": int(time.time()), "vid": vid, "q": q}
    _ucache[(vid, q)] = c
    try: _ucache_path(vid, q).write_text(json.dumps(c))
    except Exception: pass
    if len(_ucache) > 400:
        now = time.time()
        for kk in [kk for kk, vv in list(_ucache.items()) if (vv.get("expire") or 0) < now]: _ucache.pop(kk, None)
    return c
def _ucache_invalidate(vid, q, bad=False):
    try:  # play3-20261111: only a real 401/403/410 counts against the client that made the URL
        k = _UKIND.pop((vid, q), None)
        if bad: _kind_bad(vid, k)
    except Exception: pass
    _ucache.pop((vid, q), None)
    try: _ucache_path(vid, q).unlink(missing_ok=True)
    except Exception: pass
# --- play2-20261110: fast + reliable yt-dlp lookups -------------------------------------------------------------
_VIS_ON = _flag("YTDLP_VISIONOS", "1")
_KBAD = {}            # vid -> {kind: ts}: that client's URL failed (403 / error) for this video recently -> try the other first
_UKIND = {}           # (vid, q) -> kind that produced the cached URL
_VSTAT = {"vis_ok": 0, "vis_fail": 0, "def_ok": 0, "def_fail": 0, "off_until": 0}
_YP = {"mod": None, "free": {}}; _YPL = threading.Lock()
def _ejs_cache_on():
    try:
        from yt_dlp.extractor.youtube.jsc._builtin import ejs as _ejs
        if hasattr(_ejs.EJSBaseJCP, "_ENABLE_PREPROCESSED_PLAYER_CACHE"): _ejs.EJSBaseJCP._ENABLE_PREPROCESSED_PLAYER_CACHE = True
    except Exception: pass
def _js_opts(): return {} if _JSRT.lower() == "none" else {"js_runtimes": {_JSRT: {}}}
def _ydl_get(kind, fmt):
    import yt_dlp
    with _YPL:
        if _YP["mod"] is not yt_dlp: _YP["mod"] = yt_dlp; _YP["free"] = {}; _ejs_cache_on()
        lst = _YP["free"].get((kind, fmt))
        if lst: return lst.pop()
    o = {"quiet": True, "no_warnings": True, "format": fmt, "skip_download": True, "noplaylist": True, **_js_opts()}
    o["extractor_args"] = {"youtube": {"skip": ["translated_subs"]}}  # perf-20261112
    if kind == "vis": o["extractor_args"]["youtube"]["player_client"] = ["visionos"]
    y = yt_dlp.YoutubeDL(o); y._ms_n = 0; y._ms_mod = yt_dlp
    return y
def _ydl_put(kind, fmt, y, ok):
    y._ms_n += 1
    with _YPL:
        if ok and y._ms_mod is _YP["mod"] and y._ms_n < 120:
            lst = _YP["free"].setdefault((kind, fmt), [])
            if len(lst) < 2: lst.append(y); return
    try: y.close()
    except Exception: pass
def _kinds(vid):
    bad = _KBAD.get(vid) or {}; now = time.time()
    ks = ["vis", "def"] if (_VIS_ON and now > _VSTAT["off_until"]) else ["def"]
    def isbad(k):  # play3-20261111: 2+ HTTP refusals within 30 min
        v = bad.get(k)
        if not v: return False
        if isinstance(v, (int, float)): v = (v, 1)
        return now - v[0] < 1800 and v[1] >= 2
    return sorted(ks, key=lambda k: 1 if isbad(k) else 0)
def _kind_bad(vid, kind):
    if not kind: return
    d = _KBAD.setdefault(vid, {}); v = d.get(kind); now = time.time()  # play3-20261111: (last, count) within 30 min
    if isinstance(v, (int, float)): v = (v, 1)
    d[kind] = (now, (v[1] + 1) if v and now - v[0] < 1800 else 1)
    if len(_KBAD) > 2000:
        for k in list(_KBAD)[:500]: _KBAD.pop(k, None)
def _vis_health(ok):
    k = "vis_ok" if ok else "vis_fail"; _VSTAT[k] += 1
    n = _VSTAT["vis_ok"] + _VSTAT["vis_fail"]
    if n >= 10 and _VSTAT["vis_fail"] > 0.6 * n:  # visionos broken for everyone -> default clients for 6h, then re-test
        _VSTAT.update(vis_ok=0, vis_fail=0, off_until=time.time() + 1800); print("xt visionos failing -> default clients for 30 min", flush=True)  # play5-20261111
    elif n >= 40: _VSTAT.update(vis_ok=_VSTAT["vis_ok"] // 2, vis_fail=_VSTAT["vis_fail"] // 2)
_TLF = threading.local(); _FGV = {}; _BGX = threading.BoundedSemaphore(1); _BOTC = [0.0]  # play4-20261111
# --- perf-20261112: at most MUSIC_YTDLP_MAX yt-dlp lookups at once (stress test: 15 parallel lookups took 25-42 s each on the phone).
# A listener waits up to MUSIC_YTDLP_WAIT s for a slot, then gets a fast "busy" (HTTP 503 + Retry-After) and the player retries.
class ExtractBusy(RuntimeError): pass
def _quiet_call(fn, *a):
    try: return fn(*a)
    except (ExtractBusy, LiveUnsupported): return None
    except Exception as e: print(f"bg {getattr(fn, '__name__', 'job')} fail {type(e).__name__}: {str(e)[:90]}", flush=True)
_BUSYV = {}  # vid -> last time a listener got "busy" for it (perf2-20261112)
def _cfg_int(k, d):
    try: return max(1, int(os.environ.get(k) or cfg.get(k) or d))
    except Exception: return d
XT_MAX = _cfg_int("MUSIC_YTDLP_MAX", 4); XT_WAIT = float(_cfg_int("MUSIC_YTDLP_WAIT", 12)); XT_BG_WAIT = 30.0
class _XGate:
    def __init__(s, n): s.n = n; s.act = 0; s.fgw = 0; s.cv = threading.Condition(); s.stat = {"busy": 0, "max_act": 0, "waits": 0}
    def acquire(s, fg, timeout):
        end = time.time() + timeout
        with s.cv:
            if fg: s.fgw += 1
            try:
                while True:
                    if fg: free = s.n - s.act
                    elif s.fgw: free = 0                       # a listener is waiting: background lookups step aside
                    else: free = max(1, s.n - 1) - s.act       # background never takes the last slot
                    if free > 0:
                        s.act += 1; s.stat["max_act"] = max(s.stat["max_act"], s.act); return True
                    left = end - time.time()
                    if left <= 0:
                        s.stat["busy"] += 1; return False
                    s.stat["waits"] += 1; s.cv.wait(min(left, 1.0))
            finally:
                if fg: s.fgw -= 1
    def release(s):
        with s.cv: s.act = max(0, s.act - 1); s.cv.notify_all()
    def info(s): return {"max": s.n, "active": s.act, "waiting": s.fgw, **s.stat}
_XG = _XGate(XT_MAX)
# --- perf2-20261112: optional LAN lookup helper (scripts/ms_lookup_service.py on a stronger PC). Off unless ROOT/lookup.env has
# LOOKUP_URL + LOOKUP_KEY. Asked first (1.5 s to connect); off / slow / error -> the usual local lookup under the cap above.
def _lk_cfg():
    c = {}
    try:
        for ln in (ROOT / "lookup.env").read_text(encoding="utf-8").splitlines():
            ln = ln.strip()
            if ln and not ln.startswith("#") and "=" in ln: k, v = ln.split("=", 1); c[k.strip()] = v.strip()
    except Exception: pass
    return c
_LKC = _lk_cfg()
_LK = {"url": _LKC.get("LOOKUP_URL", "").rstrip("/"), "key": _LKC.get("LOOKUP_KEY", ""), "down_until": 0.0, "ok": 0, "err": 0, "yt_err": 0, "skip": 0, "ms": 0}
_LK_SEM = threading.BoundedSemaphore(max(1, int(_LKC.get("LOOKUP_MAX", "8") or 8)))
def _ydl_opts(kind, fmt):
    o = {"quiet": True, "no_warnings": True, "format": fmt, "skip_download": True, "noplaylist": True, **_js_opts()}
    o["extractor_args"] = {"youtube": {"skip": ["translated_subs"]}}
    if kind == "vis": o["extractor_args"]["youtube"]["player_client"] = ["visionos"]
    return o
class _LkYtErr(RuntimeError): pass
def _remote_info(vid, fmt, kind):
    """None = helper not used (off/down/busy) -> caller does a local lookup. Raises only for a real YouTube answer (same IP)."""
    if not (_LK["url"] and _LK["key"]) or time.time() < _LK["down_until"]: return None
    if not _LK_SEM.acquire(timeout=2): _LK["skip"] += 1; return None
    t0 = time.time(); c = None
    try:
        pu = urllib.parse.urlsplit(_LK["url"])
        c = _hc.HTTPConnection(pu.hostname, pu.port or 80, timeout=3); c.connect(); c.sock.settimeout(30)
        body = json.dumps({"url": f"https://www.youtube.com/watch?v={vid}", "opts": _ydl_opts(kind, fmt)})
        c.request("POST", "/x", body=body, headers={"Content-Type": "application/json", "X-MS-Lookup-Key": _LK["key"], "Accept-Encoding": "gzip"})
        r = c.getresponse(); b = r.read()
        if r.getheader("Content-Encoding") == "gzip": b = _gz.decompress(b)
        if r.status == 200:
            info = json.loads(b)["info"]; _LK["ok"] += 1; _LK["fails"] = 0; _LK["ms"] = int((time.time() - t0) * 1000); info["_ms_remote"] = 1; return info
        if r.status == 422:
            _LK["yt_err"] += 1; raise _LkYtErr((json.loads(b) or {}).get("err") or "lookup error")
        if r.status in (503, 504): _LK["skip"] += 1; return None
        raise OSError(f"lookup helper http {r.status}")
    except _LkYtErr: raise
    except Exception as e:
        _LK["err"] += 1; _LK["fails"] = _LK.get("fails", 0) + 1
        if isinstance(e, ConnectionRefusedError) or _LK["fails"] >= 3:  # PC off / helper stopped, or 3 failures in a row
            _LK["down_until"] = time.time() + 30; _LK["fails"] = 0
            print(f"lookup helper unavailable ({type(e).__name__}) -> local lookups for 30 s", flush=True)
        return None
    finally:
        _LK_SEM.release()
        try: c and c.close()
        except Exception: pass
class _xslot:
    def __enter__(s):
        fg = getattr(_TLF, "fg", False)
        if not _XG.acquire(fg, XT_WAIT if fg else XT_BG_WAIT): raise ExtractBusy("server busy: too many song lookups at once")
        return s
    def __exit__(s, *a): _XG.release()
def _ydl_info(vid, fmt, kind):
    if getattr(_TLF, "fg", False): return _ydl_info0(vid, fmt, kind)
    got = False; end = time.time() + 25
    try:
        while time.time() < end:
            if _FGV.get(vid): break  # a listener is waiting for exactly this song
            if _FGN[0] == 0 and _BGX.acquire(timeout=0.25): got = True; break
            if _FGN[0]: time.sleep(0.2)
        return _ydl_info0(vid, fmt, kind)
    finally:
        if got: _BGX.release()
def _bg_blocked(vid):  # YouTube bot-check seen in the last 2 min: background lookups wait it out (no client/CLI fallbacks either)
    if not getattr(_TLF, "fg", False) and time.time() - _BOTC[0] < 120 and not _FGV.get(vid):
        raise RuntimeError("background lookup paused after a YouTube bot-check")
def _ydl_info0(vid, fmt, kind):
    try: return _ydl_info1(vid, fmt, kind)
    except Exception as e:
        if "confirm you" in str(e): _BOTC[0] = time.time()
        raise
def _ydl_info1(vid, fmt, kind):
    try:
        ri = _remote_info(vid, fmt, kind)  # perf2-20261112
        if ri is not None: return ri
    except _LkYtErr as e:
        if "confirm you" in str(e) or _UPCOMING_ERR.search(str(e)): raise RuntimeError(str(e)) from None
        pass  # other helper-side yt-dlp errors: try once locally (different yt-dlp version / runtime)
    with _xslot():  # perf-20261112
        y = _ydl_get(kind, fmt); ok = False
        try:
            info = y.extract_info(f"https://www.youtube.com/watch?v={vid}", download=False); ok = True
            return info
        finally: _ydl_put(kind, fmt, y, ok)
def _formats_max_h(fm, prefix=""):
    hs = [f.get("height") or 0 for f in (fm or [])
          if (f.get("vcodec") or "none") != "none" and (not prefix or (f.get("vcodec") or "").startswith(prefix))]
    return max(hs) if hs else 0
def _merge_format_infos(*infos):
    if not infos:
        return None
    seen, fm = set(), []
    for info in infos:
        for f in info.get("formats") or []:
            k = f.get("format_id") or id(f)
            if k in seen:
                continue
            seen.add(k); fm.append(f)
    best = max(infos, key=lambda i: _formats_max_h(i.get("formats"), "avc1"))
    out = dict(best); out["formats"] = fm
    return out
def _fill_higher_rungs(vid, c, infos):
    """Background: merge the other YouTube client so 1080 avc1 is cached without delaying a 720p start."""
    try:
        have = {k for k in ("vis", "def") if any(i.get("_ms_kind") == k for i in infos)}
        for kind in _kinds(vid):
            if kind in have:
                continue
            try:
                infos.append(_ydl_info(vid, vfmt("v360" + (c or "")), kind))
            except Exception:
                continue
            break
        info = _merge_format_infos(*infos) if infos else None
        if info:
            _vinfo_from(vid, info)
    except Exception as e:
        print(f"fill higher rungs {vid} {type(e).__name__}", flush=True)
def _ydl_video_info(vid, c, need=1080):
    """Extract video formats; if visionos/helper lacks 720/1080 avc1, merge the default-client list."""
    infos, err = [], None
    need = int(need or 1080)
    for kind in _kinds(vid):
        try:
            info = _ydl_info(vid, vfmt("v360" + (c or "")), kind)
            try: info["_ms_kind"] = kind
            except Exception: pass
            infos.append(info)
            mx = _formats_max_h(info.get("formats"), "avc1")
            if mx >= max(need, 1080):
                break
            if mx >= 720 and need <= 720:
                # default 720p pick is ready; fill 1080 in the background so start stays fast
                threading.Thread(target=_fill_higher_rungs, args=(vid, c, list(infos)), daemon=True).start()
                break
        except ExtractBusy:
            raise
        except Exception as e:
            err = e
            _kind_bad(vid, kind)
    if not infos:
        raise err or RuntimeError("no info")
    return _merge_format_infos(*infos) if len(infos) > 1 else infos[0]
_FL_INF = {}; _FL_L = threading.Lock(); _FL_SEM = threading.BoundedSemaphore(max(1, int(cfg.get("FLAT_MAX", "2")))); _BG = threading.local()  # play2b-20261110
def _flat_inproc(url, n=None, timeout=45):
    """Same JSON as `yt-dlp --flat-playlist -J [--playlist-end n] url`, without starting a new python + yt-dlp import."""
    import yt_dlp
    box = {}; bg = getattr(_BG, "on", False)
    def go():
        try:
            if bg: _fg_wait(20)  # play2b-20261110
            with _FL_SEM:
                o = {"quiet": True, "no_warnings": True, "extract_flat": "in_playlist", "skip_download": True}
                if n: o["playlistend"] = int(n)
                with yt_dlp.YoutubeDL(o) as y: box["r"] = json.dumps(y.sanitize_info(y.extract_info(url, download=False)))
        except Exception as e: box["e"] = e
    with _FL_L:  # play2b-20261110: one in-flight flat per URL
        ent = _FL_INF.get((url, n))
        if ent is None or (not ent[0].is_alive() and time.time() - ent[2] > 5):
            ent = (threading.Thread(target=go, daemon=True, name="flat"), box, time.time()); _FL_INF[(url, n)] = ent; ent[0].start()
            if len(_FL_INF) > 100:
                for kk in [kk for kk, vv in list(_FL_INF.items()) if not vv[0].is_alive()]: _FL_INF.pop(kk, None)
    th, box = ent[0], ent[1]; th.join(timeout)
    if "r" in box: return box["r"]
    if "e" in box: raise box["e"]
    raise TimeoutError("flat timeout")
def _flat_out(url, n, timeout, cli):
    t0 = time.time()
    try: return _flat_inproc(url, n, timeout)
    except TimeoutError: return ""
    except Exception as e:
        left = timeout - (time.time() - t0)
        if "confirm you" in str(e):  # play4-20261111: YouTube bot-check; the CLI would hit the same wall and costs a whole python start
            _BOTC[0] = time.time(); print("flat bot-check -> no cli", flush=True); return ""
        print(f"flat inproc fail ({type(e).__name__}: {str(e)[:80]}) -> cli", flush=True)
        if left < 3: return ""
        return cli(left)
def _boot_warm():  # build + use one visionos instance at start so the first real song doesn't pay the import/init cost
    try:
        if _VIS_ON: _ydl_info(_SMOKE_VID, FMTS["std"], "vis"); print("xt boot warm ok", flush=True)
    except Exception as e: print(f"xt boot warm fail {type(e).__name__}", flush=True)
    if SEARCH_FAST:  # lat-20261111: open the search connection at start so the first real search is not the slow one
        try: _t0 = time.time(); _fast_search("music", timeout=6); print(f"search boot warm ms={int((time.time() - _t0) * 1000)}", flush=True)
        except Exception as _e: print(f"search boot warm fail {type(_e).__name__}", flush=True)
_bwt = threading.Timer(4, _boot_warm); _bwt.daemon = True; _bwt.start()
def _extract_inproc(vid, q="std"):
    """play2-20261110: pooled YoutubeDL, visionos client first then default clients. Returns (url, http_headers). Falls back to CLI."""
    fmt = vfmt(q) if q.startswith("v") else FMTS.get(q, FMTS["std"])
    e1 = None; _bg_blocked(vid)  # play4-20261111
    for kind in _kinds(vid):  # play2-20261110: visionos first, default clients as fallback
        t0 = time.time()
        try:
            info = _ydl_info(vid, fmt, kind)
            ls = _live_status(info); _live_note(vid, ls)
            if ls in _LIVE_BAD: raise LiveUnsupported(ls)
            u = info.get("url"); hdr = info.get("http_headers") or {}
            if not u and info.get("requested_formats"):
                rf = info["requested_formats"]
                pick = rf[-1] if q.startswith("v") and len(rf) > 1 else rf[0]
                u = pick.get("url"); hdr = pick.get("http_headers") or hdr
            if not u: raise RuntimeError("no media url")
            if q.startswith("v") and _url_too_low(u, q):
                # speed-20261113: this client fell through to fmt 18 / a lower rung; try the other client
                print(f"xt {vid} q={q} client={kind} fmt={info.get('format_id')} too-low, next client", flush=True)
                continue
            try: _vinfo_from(vid, info)  # latency2-20261110
            except Exception: pass
            _UKIND[(vid, q)] = kind
            if info.get("title") and len(_TITLE) < 4000: _TITLE.setdefault(vid, info["title"])  # play2b-20261110
            if kind == "vis": _vis_health(True)
            print(f"xt {vid} q={q} client={kind} fmt={info.get('format_id')} ms={int((time.time() - t0) * 1000)} ok", flush=True)
            return u, {k: str(v) for k, v in dict(hdr).items()}
        except (LiveUnsupported, ExtractBusy): raise  # perf-20261112
        except Exception as e:
            e1 = e
            if "confirm you" not in str(e): _kind_bad(vid, kind)  # play5-20261111
            if kind == "vis" and "confirm you" not in str(e): _vis_health(False)  # play5-20261111: bot-check is IP-wide, not a visionos fault
            print(f"xt {vid} q={q} client={kind} ms={int((time.time() - t0) * 1000)} fail {type(e).__name__}: {str(e)[:90]}", flush=True)
            if _UPCOMING_ERR.search(str(e)): break
    if True:
        if _UPCOMING_ERR.search(str(e1)): _live_note(vid, "is_upcoming"); raise LiveUnsupported("is_upcoming") from e1
        with _xslot():  # perf-20261112: the CLI fallback is a whole new python; same cap
            out = subprocess.run(YTDLP + ["-f", fmt, "-g", "--no-warnings", f"https://www.youtube.com/watch?v={vid}"],
                                 capture_output=True, text=True, timeout=60, creationflags=NOFLAGS)
        lines = (out.stdout or "").strip().splitlines()
        if not lines: raise RuntimeError(f"extract failed: {e1}") from e1
        if _live_url(lines[0]): _live_note(vid, "is_live"); raise LiveUnsupported("is_live")
        return lines[0], {"User-Agent": "Mozilla/5.0"}
def cached_entry(vid, q="std", force=False):
    lk = live_known(vid)
    if lk: raise LiveUnsupported(lk)  # ms-v77: fail fast, no repeated extraction for a known live stream
    if not force:
        c = _ucache_load(vid, q)
        if c: return c
    return _single(("u", vid, q), lambda: _cached_entry(vid, q, True))
def _cached_entry(vid, q="std", force=False):
    if not force:
        c = _ucache_load(vid, q)
        if c: return c
    u, hdr = _extract_inproc(vid, q)
    return _ucache_save(vid, q, u, hdr)
def cached_audio(vid, q="std"):
    """Back-compat: return URL string. Prefer cached_entry for headers."""
    return cached_entry(vid, q)["url"]
def warm_url(vid, q="hi", follow=False):
    """Resolve+cache URL only (no media download). Used by client search/queue warm."""
    if not VID.match(vid): return {"ok": False, "err": "bad id"}
    t0 = time.time()
    try:
        c = cached_entry(vid, q)
        if follow and not c.get("furl") and _FGN[0] == 0:  # lat-20261111: also follow googlevideo's 302 once (1 byte), so a tap on this song skips ~1 s
            try:
                fin = _rget(c["url"], 0, 0, timeout=8, hdrs=c.get("headers") or {})[0]
                if fin: c["furl"] = fin; c["ft"] = time.time()
            except Exception: pass
        return {"ok": True, "cached": True, "expire": c.get("expire"), "ms": int((time.time() - t0) * 1000)}
    except LiveUnsupported as e:
        return {"ok": False, "err": "live_unsupported", "live_status": e.status, "ms": int((time.time() - t0) * 1000)}
    except Exception as e:
        return {"ok": False, "err": str(e)[:120], "ms": int((time.time() - t0) * 1000)}
def suggest(q):
    u = "https://suggestqueries.google.com/complete/search?" + urllib.parse.urlencode({"client": "firefox", "ds": "yt", "q": q, "hl": "en", "gl": "in"})
    return json.loads(urllib.request.urlopen(urllib.request.Request(u, headers={"User-Agent": "Mozilla/5.0"}), timeout=5).read().decode("utf-8", "replace"))[1][:8]

def flat(url, n=50, timeout=45):
    out = _flat_out(url, n, timeout, lambda left: subprocess.run(YTDLP + [url, "--flat-playlist", "-J", "--no-warnings", "--playlist-end", str(n)], capture_output=True, text=True, timeout=max(3, left), creationflags=NOFLAGS).stdout)  # play2-20261110
    res = []
    for e in json.loads(out or '{"entries":[]}').get("entries", []):
        if not e.get("id") or not VID.match(e["id"]): continue
        ls = _live_status(e); _live_note(e["id"], ls)
        if ls in _LIVE_BAD: continue  # ms-v77: radio/mix/playlist lists never hand out live/upcoming streams
        res.append({"id": e["id"], "title": e.get("title", "?"), "dur": e.get("duration"), "channel": e.get("channel") or e.get("uploader") or ""})
        if e.get("title") and len(_TITLE) < 4000: _TITLE.setdefault(e["id"], e["title"])  # play2b-20261110
    return res
def _norm(t):
    t = re.sub(r"[\(\[].*?[\)\]]|official|video|audio|lyrics?|music|hd|4k|ft\.?.*|feat\.?.*", "", t.lower())
    return re.sub(r"[^a-z0-9]+", "", t)[:40]
# ---- song-family matcher (mirror of famkey.js; conservative, no fuzzy/transliteration/cross-language guessing)
import unicodedata as _ud
_PK = re.compile(r"^(official|lyric|lyrics|lyrical|audio|video|videos|song|songs|full|music|visualizer|visualiser|4k|hd|hq|1080p|720p|remaster|remastered|mv|m v|clip|with|the|new|telugu|tamil|hindi|kannada|malayalam|english|punjabi|bengali|marathi|version|\d{4}|from|movie|film|ost|soundtrack|cover|remix|live|lofi|lo fi|slowed|reverb|sped|up|acoustic|unplugged|reprise|8d|karaoke|instrumental|by|and|reverbed)$")
_VER = re.compile(r"\b(cover|remix|live|lo ?fi|slowed|reverb|sped up|acoustic|unplugged|reprise|8d|karaoke|instrumental)\b")
_TR = re.compile(r"^(lyrical|lyric|lyrics|video|audio|official|hd|4k|hq|visualizer|visualiser)$")
def _fn(s):
    t = "".join(c if _ud.category(c)[0] in "LMN" else " " for c in _ud.normalize("NFKC", s or "").lower())
    return " ".join(t.split())
def _pko(s):
    w = [x for x in _fn(s).split(" ") if x]; return bool(w) and all(_PK.match(x) for x in w)
def fam_parse(title, channel="", meta=None):
    t = _ud.normalize("NFKC", title or "").lower()
    for a, b in (("\u2018", "'"), ("\u2019", "'"), ("\u201c", "'"), ("\u201d", "'")): t = t.replace(a, b)
    st = {"ver": bool(_VER.search(_fn(t)))}; segs = []
    m = re.search(r"\bversion of\s+(.+)$", t)
    if m: st["ver"] = True; t = m.group(1)
    def br(mm):
        c = mm.group(1); f = re.match(r"^\s*from\s+[\"']?(.+?)[\"']?\s*$", c)
        if f: segs.append(_fn(f.group(1))); return " "
        if _VER.search(_fn(c)): st["ver"] = True
        return " " if _pko(c) else mm.group(0)
    t = re.sub(r"[\(\[\{]([^\)\]\}]*)[\)\]\}]", br, t)
    parts = re.split(r"\s[|｜]\s|\|", t); head = parts.pop(0) if parts else ""
    segs += [_fn(p) for p in parts if not _pko(p)]
    hp = []
    for p in re.split(r"\s[-–—]\s", head):
        n = _fn(p)
        if _VER.search(n) and re.search(r"\b(cover|remix|version|live)\b", n) and len(n.split(" ")) <= 4: st["ver"] = True; continue
        if not _pko(p): hp.append(p)
    bw = _fn(re.sub(r"\s*\b(ft|feat|featuring)\b\.?.*$", "", " - ".join(hp))).split(" ")
    while True:
        L = len(bw)
        if L > 2 and re.match(r"^(video|audio|full|lyrical)$", bw[L-2]) and bw[L-1] == "song": del bw[L-2:]; continue
        if L > 1 and _TR.match(bw[L-1]): bw.pop(); continue
        break
    base = " ".join(bw).strip(); meta = meta or {}; ch = channel or ""
    gen = bool(re.search(r"\s-\s*topic\s*$", ch, re.I)) or "vevo" in ch.lower()
    art = _fn(meta["artist"]) if meta.get("artist") else (_fn(re.sub(r"vevo", "", re.sub(r"\s*-\s*topic\s*$", "", ch, flags=re.I), flags=re.I)) if gen else "")
    sg = [x for x in [base] + [y for y in segs if y] if x]
    return {"base": base, "segs": sg[1:], "ver": st["ver"], "art": art, "full": " " + _fn(title) + " ", "seq": "|".join(sg), "nseg": len(sg),
            "isrc": meta.get("isrc") or "", "work": meta.get("mb_work") or "", "workRel": meta.get("mb_work_rel") or ""}
def fam_rel(a, b):
    """Strong corroboration only -> 'merge' | 'unknown' | 'distinct'. Only 'merge' suppresses in radio.
    Label/uploader channel is never artist; same film, same channel, cover/remix keywords are not evidence."""
    if a["isrc"] and a["isrc"] == b["isrc"]: return "merge"
    if a["work"] and (a["work"] == b["work"] or a["work"] in re.split(r"\W+", b["workRel"] or "")): return "merge"
    if b["work"] and b["work"] in re.split(r"\W+", a["workRel"] or ""): return "merge"
    if not a["base"] or not b["base"]: return "unknown"
    if a["base"] != b["base"]:  # 'distinct' only when proven: same genuine artist, not spelling-variants, no segment-order swap
        sk = lambda x: re.sub(r"(.)\1+", r"\1", re.sub(r"[aeiou\s]", "", x))
        if sk(a["base"]) == sk(b["base"]): return "unknown"
        if b["base"] in a["segs"] or a["base"] in b["segs"]: return "unknown"
        return "distinct" if a["art"] and a["art"] == b["art"] else "unknown"
    if len(a["base"]) < 2: return "unknown"
    if a["art"] and a["art"] == b["art"]: return "merge"
    app = lambda x, y: bool(x["art"]) and len(x["art"]) >= 3 and (" " + x["art"] + " ") in y["full"]
    if app(a, b) or app(b, a): return "merge"
    if a["nseg"] >= 3 and a["seq"] == b["seq"]: return "merge"
    return "unknown"
def fam_same(a, b): return fam_rel(a, b) == "merge"
# Cross-language / dubbed-version gate (famlang). Enrichment uses ONLY fields already on the item
# (title/channel/dur/album/artist/tags/description if present) — never a blocking yt-dlp call on the radio hot path.
try:
    from famlang import enrich as _famlang_enrich, lang_dub_rel as _lang_dub_rel
except Exception:
    def _famlang_enrich(x): return dict(x) if isinstance(x, dict) else x
    def _lang_dub_rel(a, b): return "unknown"
_seed_meta = {}  # vid -> {id,title,channel,dur} from items already fetched (search/radio pools); bounded
def _remember_meta(items, lim=500):
    for x in items or ():
        if not isinstance(x, dict): continue
        i = x.get("id")
        if not i or not VID.match(i) or not x.get("title"): continue
        _seed_meta[i] = {"id": i, "title": x.get("title") or "", "channel": x.get("channel") or "", "dur": x.get("dur")}
    if len(_seed_meta) > lim:
        for k in list(_seed_meta)[: len(_seed_meta) - lim]: _seed_meta.pop(k, None)
def _fam_item(s):
    if isinstance(s, (tuple, list)):
        return {"title": (s[0] if s else "") or "", "channel": (s[1] if len(s) > 1 else "") or "", "dur": (s[2] if len(s) > 2 else None)}
    if isinstance(s, dict): return s
    return {"title": str(s or ""), "channel": ""}
def fam_same_full(item_a, item_b):
    """fam_same OR famlang lang-dub merge. No network I/O."""
    a, b = _fam_item(item_a), _fam_item(item_b)
    pa = fam_parse(a.get("title") or "", a.get("channel") or "", a)
    pb = fam_parse(b.get("title") or "", b.get("channel") or "", b)
    if fam_same(pa, pb): return True
    try: return _lang_dub_rel(_famlang_enrich(a), _famlang_enrich(b)) == "merge"
    except Exception: return False
def fam_filter(items, seeds=()):
    """Drop items whose song family matches any seed or an earlier kept item (incl. cross-lang dubs). Never refills."""
    keep, fams, raws = [], [], []
    for s in seeds:
        it = _fam_item(s)
        if not it.get("title"): continue
        fams.append(fam_parse(it.get("title") or "", it.get("channel") or "", it)); raws.append(it)
    for x in items:
        it = x if isinstance(x, dict) else _fam_item(x)
        f = fam_parse(it.get("title") or "", it.get("channel") or "", it)
        if any(fam_same(f, g) for g in fams): continue
        if any(fam_same_full(it, s) for s in raws): continue
        fams.append(f); raws.append(it); keep.append(x)
    return keep
_rcache = {}
W_MIX = 0.55; W_SIM = 0.25; W_LANG = 0.20; NOV_EVERY = 5
LANG_BIAS = {"te": 0.40, "hi": 0.35, "en": 0.25}
LANG_LABEL = {"te": "telugu", "hi": "hindi", "en": "english", "ta": "tamil"}
_LANG_CUES = {"te": (r"[\u0C00-\u0C7F]", r"telugu|tollywood"), "hi": (r"[\u0900-\u097F]", r"hindi|bollywood"),
              "ta": (r"[\u0B80-\u0BFF]", r"tamil|kollywood"), "en": (None, r"english")}
def _chn(c):
    s = (c or "").casefold()
    for junk in (" - topic", " topic", "vevo", " official audio", " official", " - topic"):
        s = s.replace(junk, " ")
    return " ".join(s.split()).strip()
def _liked_ch(ch, lks):
    """Exact after _chn (Topic/VEVO stripped). Substring is not a D1 substitute — inject is."""
    return bool(ch) and ch in lks

def parse_lang(s):
    d = {}
    for part in (s or "").split("|"):
        k, _, v = part.partition(":")
        try: d[k.strip().lower()[:3]] = float(v)
        except ValueError: pass
    return d or dict(LANG_BIAS)
def lang_match(x, lb):
    t = (x.get("title") or "") + " " + (x.get("channel") or ""); tl = t.lower()
    for k in lb:
        sc, cue = _LANG_CUES.get(k, (None, LANG_LABEL.get(k, k)))
        if (sc and re.search(sc, t)) or re.search(cue, tl): return k
    return None
def taste_rank(L, ta=(), sk=(), lk=(), lb=None, nov=NOV_EVERY, lk_ids=(), seed_ch=""):
    """Re-rank radio by taste (lower=better): base index, -6 liked channel, -4 liked video id, -2 language cue,
    -1.5*tasteTop rank, +25 soft / hard=set(sk) (client sends each ≥2-skip channel once).
    D3: usual = ta ∪ seed ∪ lk; outside-usual same_lane → fresh. familiar nov=0 (≤1 fresh); fresh nov=3 min 3/15."""
    ta = [_chn(x) for x in ta if x][:8]; skl = [_chn(x) for x in sk if x]
    hard = set(skl); sks = set(skl); lks = {_chn(x) for x in lk if x}  # client tasteSkip already ≥2 demoted, once each
    lids = {x for x in lk_ids if x and VID.match(x)}; lb = lb if lb is not None else LANG_BIAS
    usual = set(ta) | lks | ({_chn(seed_ch)} if seed_ch else set()); usual.discard("")
    def tb(ch): return next((8 - j for j, t in enumerate(ta) if ch and t and (ch in t or t in ch)), 0)
    sc = []
    for i, x in enumerate(L):
        ch = _chn(x.get("channel")); x = dict(x)
        if ch in hard: continue
        b = tb(ch); liked_ch = _liked_ch(ch, lks); liked_id = x.get("id") in lids; liked = liked_ch or liked_id; lm = lang_match(x, lb)
        if lm: x["lang"] = lm
        s = i - b * 1.5 - (6 if liked_ch else 0) - (4 if liked_id else 0) - (2 if lm else 0) + (25 if ch in sks else 0)
        why = x.get("why") or ""
        if liked: x["why"] = "liked_lane"
        elif why == "similar_artist": pass
        elif why == "lang_pull" or (lm and not b and why != "same_lane"): x["why"] = "lang_pull" if lm else (why or "fresh")
        elif why in ("same_lane", ""):
            x["why"] = "fresh" if (ch and ch not in usual) else (why or "same_lane")
        elif not why:
            x["why"] = "fresh" if (ch and ch not in usual) else ("same_lane" if b or ch in usual else "fresh")
        sc.append((s, i, x, b))
    sc.sort(key=lambda t: (t[0], t[1]))
    out = [t[2] for t in sc]
    outside = [x for x in out if _chn(x.get("channel")) not in usual and x.get("why") != "liked_lane"]
    if usual and nov and nov > 1:
        for k in range(nov - 1, len(out), nov):
            if _chn(out[k].get("channel")) not in usual: continue
            c = next((y for y in outside if y in out and out.index(y) > k), None)
            if c is None: break
            out.remove(c); c["why"] = "fresh"; out.insert(k, c)
    if nov == 0:  # Familiar: no forced fresh; keep ≤1 if natural
        kept = 0
        for x in out:
            if x.get("why") != "fresh": continue
            if kept < 1: kept += 1
            else: x["why"] = "same_lane"
    elif nov == 3:  # Fresh: ≥3 why=fresh in first 15 (don't steal liked/lang/similar)
        n_f = sum(1 for x in out[:15] if x.get("why") == "fresh")
        for x in out[:15]:
            if n_f >= 3: break
            if x.get("why") in ("liked_lane", "lang_pull", "similar_artist", "fresh"): continue
            ch = _chn(x.get("channel"))
            if ch and ch not in usual:
                x["why"] = "fresh"; n_f += 1
        if n_f < 3:
            for x in out[:15]:
                if n_f >= 3: break
                if x.get("why") in ("liked_lane", "lang_pull", "similar_artist", "fresh"): continue
                x["why"] = "fresh"; n_f += 1
    return out
def radio(vid, exclude=(), ta=(), sk=(), lk=(), lang="", mix="", lk_ids=(), seed_ch="", exf=()):
    mx = (mix or "").lower(); nov = {"familiar": 0, "balanced": 5, "fresh": 3}.get(mx, NOV_EVERY)
    lb = parse_lang(lang)
    base = [dict(x, why=x.get("why") or "same_lane") for x in _radio_c(vid, exclude)]
    if not seed_ch:
        seed_ch = next((x.get("channel") or "" for x in base if x.get("channel")), "")
    n_lang = max(2, round(len(base) * W_LANG / max(W_MIX, 0.01))) if base else 6
    pool = _lang_pool(vid, base, lb, set(exclude) | {vid} | {x["id"] for x in base}, n_lang)
    merged, j = [], 0  # interleave: ~1 lang pick per (W_MIX/W_LANG) mix picks; W_SIM lane merged below via _sim_pool
    step = max(2, round(W_MIX / max(W_LANG, 0.01)))
    for i, x in enumerate(base):
        merged.append(x)
        if (i + 1) % step == 0 and j < len(pool): merged.append(pool[j]); j += 1
    merged += pool[j:]
    n_sim = max(2, round(len(base) * W_SIM / max(W_MIX, 0.01))) if base else 4
    exs = set(exclude) | {vid} | {x.get("id") for x in merged}
    sims = [x for x in _sim_async(vid, base, n_sim) if x["id"] not in exs][:n_sim]
    if sims:  # interleave similar ~every (W_MIX/W_SIM) slots, offset so it doesn't collide with lang picks
        st = max(2, round((W_MIX + W_LANG) / max(W_SIM, 0.01))); out, k = [], 0
        for i, x in enumerate(merged):
            out.append(x)
            if (i + 2) % st == 0 and k < len(sims): out.append(sims[k]); k += 1
        merged = out + sims[k:]
    # D1 liked inject (B): max 2 — skip demoted channels (D5 hard)
    hearts, CAP = [], 2
    sk_hard = {_chn(x) for x in sk if x}; sk_hard.discard("")
    seen = set(exclude) | {vid} | {x.get("id") for x in merged if x.get("id")}
    for hid in lk_ids:
        if len(hearts) >= CAP: break
        if not hid or not VID.match(hid) or hid in seen: continue
        try: title = title_of(hid)
        except Exception: title = hid
        hearts.append({"id": hid, "title": title or hid, "channel": "", "dur": None, "why": "liked_lane"})
        seen.add(hid)
    if len(hearts) < CAP and (lk or lk_ids):
        hop = next((x for x in lk_ids if x and VID.match(x)), None)
        picks = []
        if hop:
            try: picks = flat(f"https://music.youtube.com/watch?v={hop}&list=RDAMVM{hop}", 20)
            except Exception: picks = []
        if len([x for x in picks if x.get("id") and x["id"] not in seen]) < (CAP - len(hearts)):
            ch = next((c for c in lk if c and _chn(c) not in sk_hard), None)
            if ch:
                try: picks = list(picks) + [x for x in search(ch, 8) if x.get("id") and _chn(x.get("channel")) not in sk_hard]
                except Exception: pass
        for x in picks:
            if len(hearts) >= CAP: break
            i = x.get("id")
            if not i or i in seen or not VID.match(i): continue
            if _chn(x.get("channel")) in sk_hard: continue
            hearts.append({"id": i, "title": x.get("title") or i, "channel": x.get("channel") or "", "dur": x.get("dur"), "why": "liked_lane"})
            seen.add(i)
    if hearts:
        out = list(merged)
        for i, h in enumerate(hearts):
            out.insert(min(1 + i * 3, len(out)), h)
        merged = out
    ranked = taste_rank(merged, ta, sk, lk, lb, nov, lk_ids, seed_ch)
    usual = {_chn(x) for x in ta if x} | {_chn(x) for x in lk if x} | ({_chn(seed_ch)} if seed_ch else set()); usual.discard("")
    if mx == "fresh":
        n_f = sum(1 for x in ranked[:15] if x.get("why") == "fresh")
        if n_f < 3:
            hop = next((x["id"] for x in ranked if x.get("id") and _chn(x.get("channel")) not in usual), None) or vid
            try: extra = flat(f"https://music.youtube.com/watch?v={hop}&list=RDAMVM{hop}", 15)
            except Exception: extra = []
            seen = {x.get("id") for x in ranked if x.get("id")}
            for e in extra:
                if n_f >= 3: break
                i = e.get("id")
                if not i or i in seen or not VID.match(i): continue
                if _chn(e.get("channel")) in usual: continue
                ranked.insert(min(14, len(ranked)), dict(e, why="fresh"))
                seen.add(i); n_f += 1
    # Final-pool song-family exclusion (seed + client queue/recent-history families + intra-pool duplicates).
    # Applied after ALL lanes (liked/lang/similar/fresh) so no injection can reintroduce the same composition; never refills.
    # famlang uses title/channel/dur already on items (+ opportunistic _seed_meta); no per-candidate yt-dlp.
    _remember_meta(ranked); _remember_meta(base); _remember_meta(merged)
    _seeds = list(exf)
    if vid and vid in _seed_meta:
        _seeds = [_seed_meta[vid]] + list(_seeds)
    _n0 = len(ranked); ranked = fam_filter(ranked, _seeds); _fd = _n0 - len(ranked)
    n_f = sum(1 for x in ranked if x.get("why") == "fresh")
    n_ll = sum(1 for x in ranked if x.get("why") == "liked_lane")
    print(f"radio fresh={n_f}/{len(ranked)} mix={mx or 'balanced'} usual={len(usual)} liked_lane={n_ll} inject={len(hearts)} sk_hard={len(sk_hard)} fam_drop={_fd}", flush=True)
    ranked = _mix_order(ranked, mx)
    try: _radio_disk_save(vid, mix=mx, full=ranked)
    except Exception: pass
    return ranked
_simpool, _simth = {}, {}
SIM_BUDGET = 1.2  # max extra seconds radio() waits for the similar lane; late results are cached for the next extend
def _sim_async(vid, base, n):
    c = _simpool.get(vid)
    if c and time.time() - c[1] < 6 * 3600: return c[0]
    th = _simth.get(vid)
    if not th or not th.is_alive():
        def go():
            try: _simpool[vid] = (_sim_pool(vid, base, {vid}, n + 4), time.time())
            except Exception: pass
            _simth.pop(vid, None)
        if len(_simpool) > 300: _simpool.clear()
        th = threading.Thread(target=go, daemon=True); _simth[vid] = th; th.start()
    th.join(SIM_BUDGET)
    c = _simpool.get(vid); return c[0] if c else []
def _sim_pool(vid, base, ex, n):
    """Server-side W_SIM lane: similar(title, artist) for the seed, resolved to playable YouTube ids via search()."""
    try:
        sd = base[0] if base else {}
        t = (title_of(vid) if not base else sd.get("title")) or ""; a = sd.get("channel") or ""
        S = similar(t, _chn(a) or a) or []
    except Exception: return []
    from concurrent.futures import ThreadPoolExecutor
    def rs(x):
        if x.get("id"): return None
        try: return search(x.get("q") or f"{x.get('channel','')} {x.get('title','')}", 1)
        except Exception: return []
    S = S[:n + 4]
    with ThreadPoolExecutor(6) as ex_: R = list(ex_.map(rs, S))
    out, seen = [], set(ex)
    for x, r in zip(S, R):
        if len(out) >= n: break
        i = x.get("id")
        if not i:
            if not r: continue
            r = r[0]; i = r.get("id"); x = dict(x, title=r.get("title") or x.get("title"), channel=r.get("channel") or x.get("channel"), dur=r.get("dur"))
        if not i or i in seen or _NON_MUSIC.search(x.get("title") or ""): continue
        seen.add(i); out.append({"id": i, "title": x.get("title") or "?", "dur": x.get("dur"), "channel": x.get("channel") or "", "why": "similar_artist"})
    return out
_lcache = {}
_NON_MUSIC = re.compile(r"\b(interview|podcast|trailer|full movie|movie scene|reaction|live stream)\b", re.I)
def _prefer_ch(c):
    cl = (c or "").lower()
    return cl.endswith(" topic") or cl.endswith("- topic") or "vevo" in cl or "official" in cl
def _lang_pool(vid, base, lb, ex, n):
    top = sorted(lb.items(), key=lambda kv: -kv[1])[:2]
    seed = (base[0].get("channel") if base else "") or title_of(vid) or ""
    seed = _chn(seed)
    cand, seen = [], set()
    for k, _w in top:
        q = f"{LANG_LABEL.get(k, k)} {seed}".strip(); c = _lcache.get(q)
        if c and time.time() - c[1] < 1800: res = c[0]
        else:
            try: res = search(q, 8) or []
            except Exception: res = []
            if len(_lcache) > 200: _lcache.clear()
            _lcache[q] = (res, time.time())
        for x in res:
            if not x.get("id") or x["id"] in ex or x["id"] in seen: continue
            title = x.get("title") or ""
            if _NON_MUSIC.search(title): continue
            seen.add(x["id"]); cand.append({"id": x["id"], "title": title or "?", "dur": x.get("dur"), "channel": x.get("channel") or "", "why": "lang_pull"})
    cand.sort(key=lambda x: (0 if _prefer_ch(x.get("channel")) else 1))
    return cand[:n]
RCACHE_DIR = ROOT / "lcache" / "radio"; RCACHE_DIR.mkdir(parents=True, exist_ok=True)
RADIO_TTL = 7200  # 2h disk/mem radio cache

# ---- Play counts + home shelves (Apple/Amazon-style) ----
PLAYS_DIR = ROOT / "lcache" / "plays"; PLAYS_DIR.mkdir(parents=True, exist_ok=True)
PLAYS_FILE = PLAYS_DIR / "plays.json"
_plays_lock = threading.Lock()
_HOME_CACHE = {"t": 0, "key": "", "v": None}
def _plays_path():
    """login-state-20261110: a signed-in user has their own play counts / recent list / home shelves."""
    _u = getattr(_REQ, "user", None)
    if _u and _MSU.STORE is not None:
        try: return _MSU.STORE.plays_path(_u["u"])
        except Exception: pass
    return PLAYS_FILE

def _plays_load():
    try:
        d = json.loads(_plays_path().read_text(encoding="utf-8"))
        if not isinstance(d, dict): raise ValueError
        d.setdefault("counts", {}); d.setdefault("recent", []); d.setdefault("meta", {})
        return d
    except Exception:
        return {"counts": {}, "recent": [], "meta": {}}

def _plays_save(d):
    try:
        _plays_path().write_text(json.dumps(d, ensure_ascii=False, default=str), encoding="utf-8")
    except Exception as e:
        print(f"plays_save fail: {e}", flush=True)

def record_play(vid, title="", channel="", dur=None, client=""):
    """Bump server-side play count + recent list. Called from POST /api/played."""
    if not VID.match(vid or ""): return {"ok": False}
    with _plays_lock:
        d = _plays_load()
        d["counts"][vid] = int(d["counts"].get(vid) or 0) + 1
        meta = d["meta"].setdefault(vid, {})
        if title: meta["title"] = title[:200]
        if channel: meta["channel"] = channel[:120]
        if dur is not None:
            try: meta["dur"] = int(dur)
            except Exception: pass
        meta["t"] = time.time()
        recent = [x for x in d["recent"] if x.get("id") != vid]
        recent.append({"id": vid, "title": meta.get("title") or title or vid,
                       "channel": meta.get("channel") or channel or "",
                       "dur": meta.get("dur"), "t": meta["t"]})
        d["recent"] = recent[-300:]
        _plays_save(d)
        _HOME_CACHE["t"] = 0
    return {"ok": True, "n": d["counts"][vid]}

def _item_from_meta(vid, meta=None, why=""):
    m = meta or {}
    return {"id": vid, "title": m.get("title") or vid, "channel": m.get("channel") or "",
            "dur": m.get("dur"), "why": why, "plays": m.get("plays")}

def _trending_lang(lang, n=12):
    """Lightweight trending via yt suggest/search; cached in mem."""
    lang = (lang or "").lower()[:8]
    qmap = {"te": "telugu songs 2026", "hi": "hindi songs 2026", "en": "top english songs 2026",
            "ta": "tamil songs 2026", "kn": "kannada songs 2026", "ml": "malayalam songs"}
    q = qmap.get(lang) or (f"{lang} songs" if lang else "trending music")
    key = ("trend", q)
    c = _rcache.get(key)
    if c and time.time() - c[1] < 3600:
        return list(c[0])[:n]
    try:
        items = search(q, n) or []
    except Exception:
        items = []
    for x in items:
        x["why"] = "trending"
    _rcache[key] = (items, time.time())
    return items[:n]

def home_feed(langs="", lk_ids="", seed="", hist_ids=""):
    """Build home shelves. Prefers server play counts; falls back to client hist ids."""
    key = f"{(getattr(_REQ, 'user', None) or {}).get('u', '')}|{langs}|{lk_ids[:80]}|{seed}|{hist_ids[:80]}"  # login-state-20261110
    if _HOME_CACHE["v"] is not None and _HOME_CACHE["key"] == key and time.time() - _HOME_CACHE["t"] < 90:
        return _HOME_CACHE["v"]
    with _plays_lock:
        d = _plays_load()
    counts, meta, recent = d["counts"], d["meta"], list(d["recent"])
    # Most played
    top = sorted(counts.items(), key=lambda kv: (-kv[1], -(meta.get(kv[0], {}).get("t") or 0)))[:16]
    most = []
    for vid, n in top:
        if not VID.match(vid): continue
        it = _item_from_meta(vid, meta.get(vid), "most_played")
        it["plays"] = n
        most.append(it)
    # Recently played (newest first)
    seen = set(); rec = []
    for x in reversed(recent):
        i = x.get("id")
        if not i or i in seen or not VID.match(i): continue
        seen.add(i)
        rec.append({"id": i, "title": x.get("title") or i, "channel": x.get("channel") or "",
                    "dur": x.get("dur"), "why": "recent", "plays": counts.get(i)})
        if len(rec) >= 16: break
    # Seed client hist if server empty
    if not most and hist_ids:
        for i, vid in enumerate([x for x in hist_ids.split(",") if VID.match(x)][:16]):
            most.append(_item_from_meta(vid, meta.get(vid), "most_played"))
    if not rec and hist_ids:
        for vid in [x for x in hist_ids.split(",") if VID.match(x)][:16]:
            if vid in seen: continue
            rec.append(_item_from_meta(vid, meta.get(vid), "recent"))

    # Made for you / fresh: prefer cached radio only on the hot path (prewarm fills later)
    def _cached_radio(vid, n=10):
        if not vid or not VID.match(vid): return []
        # mem wrap cache
        for k, v in list(_rcache.items()):
            if isinstance(k, tuple) and k and k[0] == "fast" and len(k) > 1 and k[1] == vid and time.time() - v[1] < RADIO_TTL:
                return list(v[0])[:n]
            if isinstance(k, tuple) and k and k[0] == "fast_out" and len(k) > 1 and k[1] == vid and time.time() - v[1] < RADIO_TTL:
                return list(v[0])[:n]
        dsk = _radio_disk_load(vid, "balanced") or _radio_disk_load(vid, "")
        if dsk and dsk.get("fast_out"): return list(dsk["fast_out"])[:n]
        if dsk and dsk.get("wrap_out"): return list(dsk["wrap_out"])[:n]
        if dsk and dsk.get("fast"): return list(dsk["fast"])[:n]
        return []

    made = []
    seeds = []
    for vid in [x for x in lk_ids.split(",") if VID.match(x)][:4]:
        seeds.append(vid)
    if seed and VID.match(seed): seeds.insert(0, seed)
    for vid, _n in top[:3]:
        if vid not in seeds: seeds.append(vid)
    for vid in seeds[:3]:
        items = _cached_radio(vid, 10)
        if not items:
            continue
        title = (meta.get(vid) or {}).get("title") or vid
        made.append({"id": "mix_"+vid, "title": "Mix · " + (title[:40] or "For you"),
                     "channel": "Made for you", "dur": None, "why": "made_for_you",
                     "seed": vid, "items": items, "id0": items[0].get("id")})

    fresh = []
    fseed = (rec[0]["id"] if rec else (most[0]["id"] if most else (seeds[0] if seeds else "")))
    if fseed:
        fresh = [dict(x, why=x.get("why") or "fresh") for x in _cached_radio(fseed, 14)]
    if len(fresh) < 6:
        # only use search if already cached by a prior call; else bg
        try:
            key = ("trend", "new songs 2026")  # reuse any prior search cache via direct call only in bg
            pass
        except Exception:
            pass
        def _bg_fresh():
            try:
                extra = search("new songs 2026", 10) or []
                # stash under rcache for next home
                _rcache[("home_fresh_search",)] = (extra, time.time())
                _HOME_CACHE["t"] = 0
            except Exception:
                pass
        c = _rcache.get(("home_fresh_search",))
        if c and time.time() - c[1] < 3600:
            seenf = {x.get("id") for x in fresh}
            for x in c[0]:
                if x.get("id") and x["id"] not in seenf:
                    fresh.append(dict(x, why="fresh")); seenf.add(x["id"])
        else:
            threading.Thread(target=_bg_fresh, daemon=True).start()
    # background: fill radio caches for next home open
    def _bg_radio():
        for vid in seeds[:3]:
            try: radio_fast(vid)
            except Exception: pass
        if fseed:
            try: radio_fast(fseed)
            except Exception: pass
        _HOME_CACHE["t"] = 0
    threading.Thread(target=_bg_radio, daemon=True).start()

    # Trending by langs — cache-only on request path (never block home on yt search)
    trending = []
    langs_l = [x.strip() for x in (langs or "").split(",") if x.strip()][:3] or ["en"]
    seen_t = set()
    for lg in langs_l:
        key = ("trend", {"te": "telugu songs 2026", "hi": "hindi songs 2026", "en": "top english songs 2026",
                         "ta": "tamil songs 2026"}.get(lg) or f"{lg} songs")
        c = _rcache.get(("trend", key[1] if isinstance(key, tuple) else key))
        # _trending_lang uses key ("trend", q)
        qmap = {"te": "telugu songs 2026", "hi": "hindi songs 2026", "en": "top english songs 2026",
                "ta": "tamil songs 2026", "kn": "kannada songs 2026", "ml": "malayalam songs"}
        q = qmap.get(lg) or (f"{lg} songs" if lg else "trending music")
        c = _rcache.get(("trend", q))
        items = list(c[0])[:8] if c and time.time() - c[1] < 3600 else []
        for x in items:
            i = x.get("id")
            if i and i not in seen_t:
                trending.append(x); seen_t.add(i)
            if len(trending) >= 14: break
        if len(trending) >= 14: break
    def _bg_trend():
        for lg in langs_l:
            try: _trending_lang(lg, 8)
            except Exception: pass
        _HOME_CACHE["t"] = 0
    threading.Thread(target=_bg_trend, daemon=True).start()

    out = {
        "most_played": most[:12],
        "recent": rec[:12],
        "made_for_you": made[:4],
        "fresh": fresh[:12],
        "trending": trending[:12],
    }
    _HOME_CACHE.update(t=time.time(), key=key, v=out)
    # background warm first of each row
    def _warm():
        ids = []
        for row in (most, rec, fresh, trending):
            if row and row[0].get("id"): ids.append(row[0]["id"])
        for m in made:
            if m.get("id0"): ids.append(m["id0"])
        for i in ids[:8]:
            try: warm_url(i, "std")
            except Exception: pass
    threading.Thread(target=_warm, daemon=True).start()
    return out


def _mix_norm(mix=""):
    m = (mix or "").lower().strip()
    return m if m in ("familiar", "balanced", "fresh") else "balanced"
def _radio_disk_path(vid, mix=""):
    mx = _mix_norm(mix)
    # per-mix files so Familiar/Balanced/Fresh never clobber each other
    return RCACHE_DIR / (f"{vid}.{mx}.json" if mx != "balanced" else f"{vid}.json")
def _radio_disk_load(vid, mix=""):
    path = _radio_disk_path(vid, mix)
    if not path.exists(): return None
    try:
        d = json.loads(path.read_text())
        if time.time() - d.get("t", 0) < RADIO_TTL: return d
    except Exception: pass
    return None
def _radio_disk_save(vid, mix="", **parts):
    mx = _mix_norm(mix)
    d = _radio_disk_load(vid, mx) or {"t": time.time(), "vid": vid, "mix": mx}
    d["t"] = time.time(); d["mix"] = mx; d.update(parts)
    path = _radio_disk_path(vid, mx)
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(d, ensure_ascii=False, default=str), encoding="utf-8")
    except Exception as e:
        print(f"_radio_disk_save {path}: {e}", flush=True)
    return d
def _mix_order(items, mix=""):
    """Mix-specific subset+order so Familiar/Balanced/Fresh return distinct id sets (not just reshuffles)."""
    mx = _mix_norm(mix)
    xs = [dict(x) for x in (items or [])]
    if not xs: return []
    n = len(xs)
    if mx == "familiar":
        # Prefer early radio lane (closest to seed) + liked/same_lane
        pri = {"liked_lane": 0, "same_lane": 1, "lang_pull": 2, "similar_artist": 3, "fresh": 4}
        buckets = {k: [] for k in range(5)}
        for x in xs:
            buckets[pri.get((x.get("why") or ""), 3)].append(x)
        ordered = buckets[0] + buckets[1] + buckets[2] + buckets[3] + buckets[4]
        # drop the most "fresh" tail so set differs from fresh mix
        cut = max(8, int(n * 0.7))
        return ordered[:cut]
    if mx == "fresh":
        # Prefer later lane picks + why=fresh; reverse non-fresh so set shifts vs familiar
        fresh = [x for x in xs if (x.get("why") or "") == "fresh"]
        rest = [x for x in xs if (x.get("why") or "") != "fresh"]
        rest = list(reversed(rest))
        # take from the back half of original first
        back = xs[n // 3 :] + xs[: n // 3]
        seen = set(); out = []
        for x in fresh + back + rest:
            i = x.get("id")
            if not i or i in seen: continue
            seen.add(i); out.append(x)
        return out
    # balanced: keep middle-biased order (skip first 2 of raw-like list when long)
    if n > 10:
        return xs[2:] + xs[:2]
    return xs
def _radio_c(vid, exclude=()):
    c = _rcache.get(vid)
    if c and time.time() - c[1] < RADIO_TTL: return [x for x in c[0] if x["id"] not in set(exclude)]
    d = _radio_disk_load(vid)
    if d and d.get("base"):
        r = d["base"]; _rcache[vid] = (r, time.time())
        return [x for x in r if x["id"] not in set(exclude)]
    r = _radio(vid, exclude)
    if len(_rcache) > 100: _rcache.clear()
    if r:
        _rcache[vid] = (r, time.time())
        _radio_disk_save(vid, base=r)
    return r
def _radio(vid, exclude=()):
    """Parallel YT Music radio + YouTube mix flat fetch; optional 2nd-hop when rich."""
    import random
    from concurrent.futures import ThreadPoolExecutor, as_completed
    ex = set(exclude) | {vid}; pools = []
    urls = (f"https://music.youtube.com/watch?v={vid}&list=RDAMVM{vid}", f"https://www.youtube.com/watch?v={vid}&list=RD{vid}")
    def one(u):  # radio-20261111
        try: return _mixlist_url(u, 30, 8)
        except Exception: return []
    with ThreadPoolExecutor(2) as pool:
        futs = [pool.submit(one, u) for u in urls]
        try:  # radio-20261111
            for fut in as_completed(futs, timeout=10):
                try: pools.append(fut.result())
                except Exception: pools.append([])
        except Exception: pass
    base = [x for p in pools for x in p if x["id"] not in ex]
    if len(base) > 8:
        hop = random.choice(base[5:min(len(base), 20)])["id"]
        try: pools.append(flat(f"https://music.youtube.com/watch?v={hop}&list=RDAMVM{hop}", 20, timeout=10))
        except Exception: pass
    out, seen, per = [], set(), {}
    mx = max((len(p) for p in pools), default=0)
    for i in range(mx):
        for p in pools:
            if i >= len(p): continue
            x = p[i]; n = _norm(x["title"]); ch = (x.get("channel") or "").lower()
            if x["id"] in ex or n in seen or per.get(ch, 0) >= 2: continue
            seen.add(n); per[ch] = per.get(ch, 0) + 1; ex.add(x["id"]); out.append(x)
    return out[:40]
def _radio_fast_raw(vid, exclude=()):
    """First batch: parallel RDAMVM+RD only, no 2nd-hop / lang / sim / liked."""
    from concurrent.futures import ThreadPoolExecutor, as_completed
    ex = set(exclude) | {vid}; pools = []
    urls = (f"https://music.youtube.com/watch?v={vid}&list=RDAMVM{vid}", f"https://www.youtube.com/watch?v={vid}&list=RD{vid}")
    def one(u):  # radio-20261111
        try: return _mixlist_url(u, 25, 7)
        except Exception: return []
    with ThreadPoolExecutor(2) as pool:
        futs = [pool.submit(one, u) for u in urls]
        try:  # radio-20261111: a slow list must not raise out of radio
            for fut in as_completed(futs, timeout=9):
                try: pools.append(fut.result())
                except Exception: pools.append([])
        except Exception: pass
    out, seen, per = [], set(), {}
    mx = max((len(p) for p in pools), default=0)
    for i in range(mx):
        for p in pools:
            if i >= len(p): continue
            x = p[i]; n = _norm(x.get("title") or ""); ch = (x.get("channel") or "").lower()
            if not x.get("id") or x["id"] in ex or n in seen or per.get(ch, 0) >= 2: continue
            seen.add(n); per[ch] = per.get(ch, 0) + 1; ex.add(x["id"])
            out.append(dict(x, why="same_lane"))
    return out[:24]
def radio_fast(vid, exclude=(), exf=(), mix="", ta=(), sk=(), lk=(), lk_ids=(), seed_ch=""):
    """Instant-feel first batch with disk/mem cache + family/famlang filter; honors mix ordering."""
    t0 = time.time(); mx = _mix_norm(mix)
    ex_key = (tuple(sorted(set(exclude) | {vid})), tuple((a, b) for a, b in (exf or [])[:8]))
    memo = _rcache.get(("fast_out", vid, mx, ex_key))
    if memo and time.time() - memo[1] < RADIO_TTL:
        print(f"radio_fast mix={mx} n={len(memo[0])} cache=mem_out_early ms={int((time.time() - t0) * 1000)}", flush=True)
        return list(memo[0])
    d = _radio_disk_load(vid, mx) or (_radio_disk_load(vid, "balanced") if mx != "balanced" else None) or _radio_disk_load(vid, "")
    if d and d.get("fast_out") and not exclude and not exf:
        items = [x for x in d["fast_out"] if x.get("id") != vid]
        print(f"radio_fast mix={mx} n={len(items)} cache=disk_out ms={int((time.time() - t0) * 1000)}", flush=True)
        return items
    if d and d.get("fast"):
        items = [x for x in d["fast"] if x.get("id") not in set(exclude) | {vid}]
    else:
        c = _rcache.get(("fast", vid, mx))
        if c and time.time() - c[1] < RADIO_TTL:
            items = [x for x in c[0] if x.get("id") not in set(exclude) | {vid}]
        else:
            # raw pool shared by vid; order/annotate per mix
            raw_c = _rcache.get(("fast_raw", vid))
            if raw_c and time.time() - raw_c[1] < RADIO_TTL:
                raw = list(raw_c[0])
            else:
                raw = _radio_fast_raw(vid, exclude)
                if raw:  # play2-20261110: an empty batch (timeout) must not stick for RADIO_TTL
                    _rcache[("fast_raw", vid)] = (raw, time.time())
                    try: _radio_disk_save(vid, mix="balanced", base=raw)
                    except Exception: pass
            # Per-mix pool slice BEFORE rank so id sets diverge (UI Familiar/Balanced/Fresh)
            if mx == "familiar":
                pool = raw[: max(10, int(len(raw) * 0.65))] or raw
            elif mx == "fresh":
                # later lane + optional 2nd-hop for more novelty
                pool = (raw[len(raw)//3 :] + raw[: len(raw)//3]) if raw else []
                if raw:
                    try:
                        hop = raw[min(len(raw)-1, max(5, len(raw)//2))].get("id")
                        if hop and VID.match(hop):
                            extra = flat(f"https://music.youtube.com/watch?v={hop}&list=RDAMVM{hop}", 12, timeout=8)
                            seen = {x.get("id") for x in pool}
                            for e in extra:
                                i = e.get("id")
                                if i and i not in seen and VID.match(i):
                                    pool.append(dict(e, why="fresh")); seen.add(i)
                    except Exception:
                        pass
            else:
                pool = raw[1:] + raw[:1] if len(raw) > 4 else list(raw)
            nov = {"familiar": 0, "balanced": 5, "fresh": 3}.get(mx, 5)
            items = taste_rank([dict(x) for x in pool], ta, sk, lk, None, nov, lk_ids, seed_ch)
            items = _mix_order(items, mx)
            if items:  # play2-20261110
                _rcache[("fast", vid, mx)] = (items, time.time())
                _radio_disk_save(vid, mix=mx, fast=items)
    _remember_meta(items)
    seeds = list(exf)
    if vid and vid in _seed_meta: seeds = [_seed_meta[vid]] + list(seeds)
    n0 = len(items); items = fam_filter(items, seeds)
    items = _mix_order(items, mx)
    if items: _rcache[("fast_out", vid, mx, ex_key)] = (list(items), time.time())  # play2-20261110
    try:
        if items: _radio_disk_save(vid, mix=mx, fast=items, fast_out=items)
    except Exception as e:
        print(f"radio_disk_save fail {vid}: {e}", flush=True)
    print(f"radio_fast mix={mx} n={len(items)} drop={n0 - len(items)} ms={int((time.time() - t0) * 1000)}", flush=True)
    return items
_RPW = []; _RPW_L = threading.Lock(); _RPW_EV = threading.Event(); _RPW_DONE = {}; _RPW_T = [None]  # play2b-20261110
def _rpw_worker():
    while True:
        _RPW_EV.wait(60)
        with _RPW_L:
            vid = _RPW.pop() if _RPW else None
            if not _RPW: _RPW_EV.clear()
        if not vid: continue
        _fg_wait(30); _BG.on = True; t0 = time.time()
        try:
            radio_fast(vid); _fg_wait(30); radio(vid)
            print(f"radio_prewarm {vid} ms={int((time.time() - t0) * 1000)}", flush=True)
        except Exception as e:
            print(f"radio_prewarm fail {vid}: {e}", flush=True)
        finally: _BG.on = False; _RPW_DONE[vid] = time.time()
def radio_prewarm(vid):
    if not VID.match(vid or ""): return {"ok": False}
    if time.time() - _RPW_DONE.get(vid, 0) < 1800: return {"ok": True, "cached": True}
    with _RPW_L:
        if _RPW_T[0] is None or not _RPW_T[0].is_alive():
            _RPW_T[0] = threading.Thread(target=_rpw_worker, daemon=True, name="radio-prewarm"); _RPW_T[0].start()
        if vid not in _RPW: _RPW.append(vid)
        del _RPW[:-2]; _RPW_EV.set()
    if len(_RPW_DONE) > 2000: _RPW_DONE.clear()
    return {"ok": True, "warming": True}

_chips = {"t": 0, "v": []}
def chips(artists):
    """Dynamic chips: YouTube suggest for the user's recent artists + rotating trending seeds (cached 3h)."""
    import datetime, random
    out = []
    for a in [x for x in artists if x][:3]:
        try: out += [q for q in suggest(a)[1:4] if q.lower() != a.lower()][:2]
        except Exception: pass
    if time.time() - _chips["t"] > 3 * 3600 or not _chips["v"]:
        m = datetime.date.today().strftime("%B %Y")
        seeds = ["new songs", "trending songs", "top hindi songs", "new punjabi songs", "top english songs", "lofi", "new tamil songs", "telugu hits", "party songs", "romantic songs"]
        v = []
        for sd in random.sample(seeds, 5):
            try: v += suggest(f"{sd} {m.split()[1]}")[:2]
            except Exception: pass
        _chips.update(t=time.time(), v=list(dict.fromkeys(v)))
    return list(dict.fromkeys(out + random.sample(_chips["v"], min(8, len(_chips["v"])))))[:12]
def spotify(url):
    m = re.search(r"open\.spotify\.com/(?:intl-\w+/)?(playlist|album|track)/([A-Za-z0-9]+)", url)
    if not m: return []
    h = urllib.request.urlopen(urllib.request.Request(f"https://open.spotify.com/embed/{m.group(1)}/{m.group(2)}", headers={"User-Agent": "Mozilla/5.0"}), timeout=15).read().decode("utf-8", "replace")
    d = json.loads(re.search(r'<script id="__NEXT_DATA__" type="application/json">(.*?)</script>', h, re.S).group(1))
    ent = d["props"]["pageProps"]["state"]["data"]["entity"]
    tl = ent.get("trackList") or [{"title": ent.get("name"), "subtitle": ", ".join(a["name"] for a in ent.get("artists", []))}]
    return [{"id": None, "q": f"{t.get('title','')} {t.get('subtitle','')}".strip(), "title": t.get("title", "?"), "channel": t.get("subtitle", ""), "dur": (t.get("duration") or 0) // 1000 or None} for t in tl]
def import_safe(text):
    try: return import_text(text)
    except ValueError as e:
        if str(e) == "AMAZON": return {"error": "amazon", "msg": "Amazon Music doesn't publish playlist tracks publicly (the page loads them only inside a signed-in app), so the link can't be read. Export it instead: open the playlist in the Amazon Music app/web, select all songs and copy, or use TuneMyMusic/Soundiiz (free) to export as CSV/TXT, then paste or upload here. One 'Title - Artist' per line works."}
        raise
def import_text(text):
    items = []
    for line in text.splitlines():
        line = line.strip().strip(",")
        if not line or line.startswith("#"): continue
        if "spotify.com" in line: items += spotify(line); continue
        if re.search(r"music\.amazon\.|amazon\.[a-z.]+/music|amzn\.(to|in|eu)/|Check out this (playlist|song|album) on Amazon Music", line, re.I): raise ValueError("AMAZON")
        lm = re.search(r"[?&]list=([A-Za-z0-9_-]{10,64})", line)
        if lm and re.match(r"^https?://(www\.|music\.|m\.)?youtube\.com/", line): items += flat(f"https://www.youtube.com/playlist?list={lm.group(1)}", 200); continue
        v = resolve(line) if re.search(r"youtu\.?be|^[A-Za-z0-9_-]{11}$", line) else None
        if v: items.append({"id": v, "title": line, "channel": "", "dur": None}); continue
        line = re.sub(r"^\d+[.)]\s*", "", line).replace(",", " - ")
        items.append({"id": None, "q": line, "title": line, "channel": "", "dur": None})
    return items[:300]

# ---- chunked disk cache: googlevideo throttles open-ended ranges (~30KB/s); bounded 1MB ranges come at full speed
# lat-20261111: HEAD_KB (default 96, was 256): a smaller first upstream read gets the first audio bytes to the player ~0.3-0.6 s sooner
CACHE = ROOT / "cache"; CACHE.mkdir(exist_ok=True); CH = 1 << 20; _VRA = max(4, min(256, int(cfg.get("VIDEO_RA_MB", "24") or 24))); HEAD_B = max(32, min(1024, int(cfg.get("HEAD_KB", "96") or 96))) << 10; DIRECT_B = 256 << 10; _blobs = {}; _blk = threading.Lock()
MAX_FETCH = int(cfg.get("MAX_FETCH", "8")); MAX_ACTIVE = int(cfg.get("MAX_ACTIVE_DL", "4")); MAX_FF = int(cfg.get("MAX_FFMPEG", "2"))
_FETCH = threading.BoundedSemaphore(MAX_FETCH)   # global cap on parallel 1MB upstream fetches (all listeners combined)
_FF = threading.BoundedSemaphore(MAX_FF)         # cap on concurrent ffmpeg mp3 transcodes (/stream, /dl)
_pend = [0]
def active_dls(): return sum(1 for b in list(_blobs.values()) if not b.err and len(b.have) < b.n)
_tl = threading.local()
_ARA = max(0, min(64, int(cfg.get("AUDIO_RA_MB", "6") or 0)))  # perf2-20261112: audio read-ahead window (MB); 0 = old whole-file prefetch
_V4_ALWAYS = _flag("STREAM_IPV4", "0")  # perf2-20261112: force IPv4 for every stream fetch (default: only for IPv4-bound URLs)
class _HTTPS4(_hc.HTTPSConnection):  # perf2-20261112
    def connect(s):
        import socket, ssl
        ai = socket.getaddrinfo(s.host, s.port or 443, socket.AF_INET, socket.SOCK_STREAM)
        raw = socket.create_connection(ai[0][4][:2], s.timeout)
        s.sock = (getattr(s, "_context", None) or ssl.create_default_context()).wrap_socket(raw, server_hostname=s.host)
def _v4_url(url):
    try:
        ip = (urllib.parse.parse_qs(urllib.parse.urlsplit(url).query).get("ip") or [""])[0]
        return bool(ip) and ":" not in ip
    except Exception: return False
def _rget(url, a, b, timeout=20, hdrs=None):
    """Ranged GET over a per-thread keep-alive HTTPS connection (googlevideo: new TLS per 1MB chunk cost ~0.5-1s).
    Returns (final_url, headers, body). Follows up to 3 redirects; falls back to urllib on any connection error.
    hdrs: optional upstream http_headers from yt-dlp (User-Agent/Cookie); Range is always set."""
    import http.client
    base = {"User-Agent": "Mozilla/5.0"}
    if hdrs: base.update({k: v for k, v in hdrs.items() if k.lower() not in ("range", "host", "content-length")})
    base["Range"] = f"bytes={a}-{b}"; url0 = url
    for _ in range(4):
        p = urllib.parse.urlsplit(url)
        if p.scheme != "https": break
        pool = getattr(_tl, "c", None)
        if pool is None: pool = _tl.c = {}
        v4 = _V4_ALWAYS or _v4_url(url) or _v4_url(url0); pk = p.netloc + ("|4" if v4 else "")  # perf2-20261112
        c = pool.get(pk)
        for attempt in (0, 1):
            try:
                if c is None: c = pool[pk] = (_HTTPS4 if v4 else http.client.HTTPSConnection)(p.netloc, timeout=timeout)
                c.request("GET", p.path + ("?" + p.query if p.query else ""), headers=base)
                r = c.getresponse(); body = r.read(); break
            except Exception:
                try: c.close()
                except Exception: pass
                c = None; pool.pop(pk, None)
                if attempt: raise
        if r.status in (301, 302, 303, 307, 308) and r.getheader("Location"):
            url = urllib.parse.urljoin(url, r.getheader("Location")); continue
        if r.status >= 400: raise urllib.error.HTTPError(url, r.status, r.reason, r.headers, None)
        return url, r.headers, body
    r = urllib.request.urlopen(urllib.request.Request(url, headers=base), timeout=timeout)
    return r.geturl(), r.headers, r.read()
class Blob:
    def __init__(s, vid, fq):
        s.vid, s.fq = vid, fq; s.cond = threading.Condition(); s.have = set(); s.want = 0; s.err = None; s.t = time.time(); s.busy = set()
        ent = cached_entry(vid, fq); url, uh = ent["url"], ent.get("headers") or {}
        _fu = ent.get("furl") if time.time() - (ent.get("ft") or 0) < 3600 else None  # lat-20261111: post-redirect URL from warm
        if _fu: url = _fu
        # Small head probe: first bytes reach the player sooner; workers fill chunk 0. On 403/expired: singleflight refresh BEFORE any response headers.
        for _hp in range(3):  # play3-20261111: cached URL -> fresh -> fresh from the other client
            try: fin, rh, d0 = _rget(url, 0, HEAD_B - 1, hdrs=uh); break
            except Exception as e:
                if _fu and url == _fu:  # lat-20261111: stale redirect target -> plain URL, no re-extraction
                    ent.pop("furl", None); url = ent["url"]; _fu = None
                    try: fin, rh, d0 = _rget(url, 0, HEAD_B - 1, hdrs=uh); break
                    except Exception as e2: e = e2
                # 403/expired/DNS/TLS: invalidate + singleflight refresh BEFORE any response headers leave the server
                http = isinstance(e, urllib.error.HTTPError) and getattr(e, "code", 0) in (401, 403, 410)
                print(f"blob head {vid} {fq} try={_hp} {type(e).__name__} {getattr(e, 'code', '')}", flush=True)
                _ucache_invalidate(vid, fq, bad=http)
                if _hp == 2: raise
                ent = cached_entry(vid, fq, force=True); url, uh = ent["url"], ent.get("headers") or {}
        try: ent["furl"] = fin; ent["ft"] = time.time()  # lat-20261111
        except Exception: pass
        s.url = fin; s.uh = uh  # post-redirect URL + yt-dlp headers for later chunk fetches
        s.ctype = rh.get("Content-Type", "application/octet-stream")
        s.size = int(rh["Content-Range"].split("/")[1])
        s.n = (s.size + CH - 1) // CH; s.path = CACHE / f"{vid}_{fq}.bin"
        try: _blob_ok_path(vid, fq).unlink()  # speed-20261110: being rewritten
        except Exception: pass
        with open(s.path, "wb") as f: f.truncate(s.size)
        s.f = open(s.path, "r+b"); s.fl = threading.Lock()
        s.head = d0 if len(d0) == min(s.size, HEAD_B) else b""
        if s.head and len(d0) == min(s.size, CH):
            s.f.seek(0); s.f.write(d0); s.have.add(0)
        # vbuf-20261111: video (and long audio) keep a read-ahead window instead of pulling the whole file. Pulling every
        # rendition in full (seen: 360+480+720+1080 = 1.3 GB in 2 min for one long video) saturated the phone's Wi-Fi and
        # starved the tunnel upload, which is what made video buffer. Window = VIDEO_RA_MB ahead of the newest read.
        s.ra = _VRA if fq.startswith("v") else (_ARA if _ARA else (0 if s.n <= 48 else 48)); s.nw = 0  # perf2-20261112: _ARA
        s._spawn()
    nw = 0; ra = 0; slid = False; rdn = 0  # rdn: chunks the player has moved through (perf2-20261112: window = 2 x that, 3..VIDEO_RA_MB)  # slid: a real read arrived (until then only the first 2 MB, the player usually joins mid-video)
    def _spawn(s):
        with s.cond:
            k = 4 - s.nw
            if k <= 0: return
            s.nw += k
        for _ in range(k): threading.Thread(target=s.work, daemon=True).start()
    def pick(s):
        with s.cond:
            rng = range(s.want, min(s.n, s.want + (min(s.ra, max(3, 2 * s.rdn)) if s.slid else 2))) if s.ra else list(range(s.want, s.n)) + list(range(0, s.want))  # perf2-20261112
            for i in rng:
                if i not in s.have and i not in s.busy: s.busy.add(i); return i
        return None
    busy = None
    def work(s):
        try:
            while (i := s.pick()) is not None:
                if not s.fetch1(i): return
        finally:
            with s.cond: s.nw -= 1
    def fetch1(s, i):
        if True:
            a, b = i * CH, min(s.size, (i + 1) * CH) - 1
            for tr in range(4):
                try:
                    with _FETCH: d = _rget(s.url, a, b, hdrs=getattr(s, "uh", None))[2]
                    if len(d) != b - a + 1: raise IOError("short")
                    with s.fl: s.f.seek(a); s.f.write(d)
                    break
                except urllib.error.HTTPError as e:
                    if e.code in (401, 403, 410) and tr < 3:
                        try:
                            _ucache_invalidate(s.vid, s.fq, bad=True)  # play3-20261111
                            ent = cached_entry(s.vid, s.fq, force=True)
                            s.url, s.uh = ent["url"], ent.get("headers") or {}
                        except Exception: pass
                        time.sleep(0.2); continue
                    if tr == 3:
                        with s.cond: s.err = e; s.busy.discard(i); s.cond.notify_all()
                        return False
                    time.sleep(0.5)
                except Exception as e:
                    if tr == 3:
                        with s.cond: s.err = e; s.busy.discard(i); s.cond.notify_all()
                        return False
                    time.sleep(0.5)
            with s.cond: s.have.add(i); s.busy.discard(i); s.cond.notify_all(); _all = len(s.have) >= s.n
            if _all: _blob_done(s)  # speed-20261110
            return True
    def direct(s, a, b):  # bounded ranged fetch straight from upstream (bypasses the queue for seek targets)
        with _FETCH: return _rget(s.url, a, b, hdrs=getattr(s, "uh", None))[2]
    def read(s, a, b):  # bytes a..b (inclusive); serves head/direct slices while the 1MB chunk is still in flight
        i = a // CH
        if s.ra and (i != s.want or not s.slid):  # vbuf-20261111: slide the read-ahead window with playback
            with s.cond:
                if s.slid and i == s.want + 1: s.rdn += 1  # perf2-20261112: steady playback grows the window; a seek does not
                s.want = i; s.slid = True
            s._spawn()
        if a < len(s.head) and i not in s.have: return s.head[a:min(b + 1, len(s.head))]
        with s.cond:
            if i not in s.have:
                s.want = i
                if i not in s.busy: s.busy.add(i); threading.Thread(target=s.fetch1, args=(i,), daemon=True).start()
        if i not in s.have:  # seek target not on disk yet: answer the first slice directly instead of waiting for the whole chunk
            e = min(b, (i + 1) * CH - 1, a + DIRECT_B - 1)
            try:
                d = s.direct(a, e)
                if len(d) == e - a + 1: return d
            except Exception: pass
        with s.cond:
            end = time.time() + 30
            while i not in s.have:
                if s.err or time.time() > end: raise IOError("fetch failed")
                s.cond.wait(5)
        e = min(b, (i + 1) * CH - 1)
        with s.fl: s.f.seek(a); return s.f.read(e - a + 1)
Blob.busy = None
def get_blob(vid, fq):
    with _blk:
        bl = _blobs.get((vid, fq))
        if bl and not bl.err and time.time() - bl.t < 3 * 3600: bl.t2 = time.time(); return bl
    return _single(("b", vid, fq), lambda: _new_blob(vid, fq))
# --- speed-20261110: a fully downloaded song/video stays usable after a restart (no yt-dlp lookup at all) ---
BLOB_DISK_TTL = int(cfg.get("BLOB_DISK_TTL", str(30 * 86400)))
def _blob_ok_path(vid, fq): return CACHE / f"{vid}_{fq}.ok"
class _DiskBlob:
    def __init__(s, vid, fq, path, meta):
        s.vid, s.fq, s.path = vid, fq, path; s.size = int(meta["size"]); s.ctype = meta.get("ctype") or "application/octet-stream"
        s.err = None; s.t = s.t2 = time.time(); s.head = b""; s.n = (s.size + CH - 1) // CH; s.have = set(range(s.n)); s.busy = set()
        s.cond = threading.Condition(); s.want = 0; s.fl = threading.Lock(); s.f = open(path, "rb"); s.url = None; s.uh = {}; s.disk = True
    def read(s, a, b):
        with s.fl: s.f.seek(a); return s.f.read(min(b, s.size - 1) - a + 1)
def _disk_blob(vid, fq):
    try:
        f = CACHE / f"{vid}_{fq}.bin"; okp = _blob_ok_path(vid, fq)
        if not (f.exists() and okp.exists()): return None
        m = json.loads(okp.read_text())
        if int(m.get("size", 0)) <= 0 or int(m["size"]) != f.stat().st_size or time.time() - float(m.get("t", 0)) > BLOB_DISK_TTL: return None
        try: os.utime(f, None)
        except Exception: pass
        return _DiskBlob(vid, fq, f, m)
    except Exception: return None
def _blob_done(b):
    try:
        with b.fl: b.f.flush()
        okp = _blob_ok_path(b.vid, b.fq); t = okp.with_suffix(".oktmp")
        t.write_text(json.dumps({"size": b.size, "ctype": b.ctype, "t": time.time()})); os.replace(t, okp)
    except Exception: pass
def _new_blob(vid, fq):
    with _blk:  # another thread may have finished it while we waited
        bl = _blobs.get((vid, fq))
        if bl and not bl.err and time.time() - bl.t < 3 * 3600: return bl
    bl = _disk_blob(vid, fq) or Blob(vid, fq)  # speed-20261110
    with _blk:
        _blobs[(vid, fq)] = bl
        _cache_evict_locked()
    return bl

CACHE_MAX_BYTES = int(cfg.get("CACHE_MAX_GB", "5")) * (1 << 30)

def _cache_evict_locked():
    """LRU-ish eviction by mtime across in-memory blobs + on-disk .bin files. Cap ~CACHE_MAX_GB."""
    # close/drop oldest in-memory beyond 32
    if len(_blobs) > 32:
        for key, o in sorted(_blobs.items(), key=lambda kv: getattr(kv[1], "t2", kv[1].t))[:len(_blobs) - 32]:
            _blobs.pop(key, None)
            try: o.f.close()
            except Exception: pass
    try:
        files = list(CACHE.glob("*.bin"))
        total = sum(f.stat().st_size for f in files)
        if total <= CACHE_MAX_BYTES: return
        # evict oldest files not currently open in _blobs
        open_paths = {str(getattr(b, "path", "")) for b in _blobs.values()}
        for f in sorted(files, key=lambda p: p.stat().st_mtime):
            if total <= CACHE_MAX_BYTES: break
            if str(f) in open_paths: continue
            try:
                sz = f.stat().st_size; f.unlink(); total -= sz
            except Exception: pass
    except Exception: pass
# Keep media .bin and URL disk cache across restarts (ms-v49). Do not wipe valid cache at startup.
# Drop only empty zero-byte stubs left by a crashed truncate.
for _f in CACHE.glob("*.bin"):
    try:
        if _f.stat().st_size == 0: _f.unlink()
    except Exception: pass
def _ly_cjk(s): return len(re.findall(r"[\u3040-\u30ff\u3400-\u9fff]", s or ""))
def _ly_indic(s): return len(re.findall(r"[\u0900-\u0D7F]", s or ""))
def _ly_mismatch(query, body):
    """Drop NetEase/etc JP/CJK hits for Indic or Latin-script songs (Magale → wrong JP lyrics)."""
    if not body: return False
    qcjk, qind = _ly_cjk(query), _ly_indic(query)
    bcjk, bind = _ly_cjk(body), _ly_indic(body)
    if qind >= 2 and bcjk >= 8 and bind < 2: return True
    if qcjk < 2 and qind < 2 and bcjk >= 12 and len(re.findall(r"[A-Za-z]", body)) < 12: return True
    return False
def lyrics(t, a, d):
    base = "https://lrclib.net/api/"; hd = {"User-Agent": "music-stream (personal)"}
    t2 = re.sub(r"\s*[\(\[][^)\]]*(official|video|audio|lyric|4k|hd|visualizer|mv)[^)\]]*[\)\]]", "", t, flags=re.I)
    if " - " in t2 and (not a or a.lower().endswith("vevo") or "topic" in a.lower()): a, t2 = t2.split(" - ", 1)
    elif " - " in t2: a2, t3 = t2.split(" - ", 1); a, t2 = a2, t3
    a = re.sub(r"(VEVO| - Topic)$", "", a or "").strip(); t2 = re.sub(r"\s*\|.*$", "", t2).strip()
    try:
        r = json.load(urllib.request.urlopen(urllib.request.Request(base + "search?" + urllib.parse.urlencode({"track_name": t2, "artist_name": a}), headers=hd), timeout=8))
        if not r: r = json.load(urllib.request.urlopen(urllib.request.Request(base + "search?" + urllib.parse.urlencode({"q": f"{a} {t2}"}), headers=hd), timeout=8))
    except Exception: r = []
    r = [x for x in r if not _ly_mismatch(f"{t2} {a}".strip(), (x.get("syncedLyrics") or "") + (x.get("plainLyrics") or "") + (x.get("trackName") or ""))]
    if not r or not any(x.get("syncedLyrics") for x in r):
        try:
            import syncedlyrics
            box = {}  # hard 10s cap: syncedlyrics providers can hang and stall the request thread
            th = threading.Thread(target=lambda: box.update(r=syncedlyrics.search(f"{t2} {a}".strip(), providers=["Musixmatch", "NetEase"], synced_only=True)), daemon=True)
            th.start(); th.join(10); lrc = box.get("r")
            if lrc and not _ly_mismatch(f"{t2} {a}".strip(), lrc): return {"synced": lrc, "plain": "", "name": t2, "artist": a, "src": "syncedlyrics"}
        except Exception: pass
    if not r: return {}
    # v66: don't pick a live/tribute/remix cut for a studio upload (its timing differs), and prefer the
    # version most LRCLIB entries agree on (same duration + same first line) when no duration is close.
    _VERW = r"\b(live|concert|tribute|wembley|rio|montreal|unplugged|acoustic|drumless|karaoke|instrumental|remix|cover|slowed|reverb|sped|8d|demo|session)\b"
    tl = (t or "").lower()
    def _pen(x):
        nm = f"{x.get('albumName') or ''} {x.get('trackName') or ''}".lower()
        return any(w not in tl for w in re.findall(_VERW, nm))
    def _fl(x):
        m0 = re.search(r"\[(\d+):(\d+(?:\.\d+)?)\]", x.get("syncedLyrics") or ""); return float(m0.group(1)) * 60 + float(m0.group(2)) if m0 else -1
    _ag = {id(x): sum(1 for y in r if y.get("syncedLyrics") and abs((y.get("duration") or 0) - (x.get("duration") or 0)) <= 1 and abs(_fl(y) - _fl(x)) < .6) for x in r}
    _agree = lambda x: _ag.get(id(x), 0)  # precomputed: list.sort() empties r while sorting
    if d: r.sort(key=lambda x: (not x.get("syncedLyrics"), _pen(x), abs((x.get("duration") or 0) - d) > 4, -min(_agree(x), 5) if abs((x.get("duration") or 0) - d) > 4 else 0, abs((x.get("duration") or 0) - d)))
    else: r.sort(key=lambda x: (not x.get("syncedLyrics"), _pen(x), -min(_agree(x), 5)))
    x = r[0]; return {"synced": x.get("syncedLyrics") or "", "plain": x.get("plainLyrics") or "", "name": x.get("trackName"), "artist": x.get("artistName"), "dur": x.get("duration") or 0, "album": x.get("albumName") or ""}
def translate(lines, tl):
    out = []
    for i in range(0, len(lines), 40):
        chunk = "\n".join(lines[i:i + 40])
        u = "https://translate.googleapis.com/translate_a/single?" + urllib.parse.urlencode({"client": "gtx", "sl": "auto", "tl": tl, "dt": "t", "q": chunk})
        try:
            j = json.load(urllib.request.urlopen(urllib.request.Request(u, headers={"User-Agent": "Mozilla/5.0"}), timeout=10))
            txt = "".join(seg[0] for seg in j[0] if seg[0])
        except Exception:  # gtx 429/blocked -> clients5 dict-chrome-ex fallback
            u2 = "https://clients5.google.com/translate_a/t?" + urllib.parse.urlencode({"client": "dict-chrome-ex", "sl": "auto", "tl": tl, "q": chunk})
            j = json.load(urllib.request.urlopen(urllib.request.Request(u2, headers={"User-Agent": "Mozilla/5.0"}), timeout=10))
            txt = j[0][0] if isinstance(j[0], list) else j[0]
        part = txt.split("\n")
        part += [""] * (len(lines[i:i + 40]) - len(part)); out += part[:len(lines[i:i + 40])]
    return out
# ---- persistent disk cache for lyrics / translations / karaoke (survives restarts) ----
import hashlib
LCD = ROOT / "lcache"; LCD.mkdir(exist_ok=True)
def _dc(ns, fn):
    def w(*a):
        p = LCD / f"{ns}_{hashlib.sha1(json.dumps([ns, a], ensure_ascii=False).encode()).hexdigest()}.json"
        if p.exists():
            try: return json.loads(p.read_text(encoding="utf-8"))
            except Exception: pass
        r = fn(*a)
        if r:
            try: p.write_text(json.dumps(r, ensure_ascii=False), encoding="utf-8")
            except Exception: pass
        return r
    return w
class _TrPartial(list):
    """lyrics2-20261111: falsy so _dc() skips caching an incomplete translation; still serialises as a normal list."""
    def __bool__(self): return False
def _tr_nocache_partial(fn):
    def w(lines, tl):
        out = fn(lines, tl)
        if any(str(l).strip() and not str(o or "").strip() for l, o in zip(lines, out)): return _TrPartial(out)
        return out
    return w
lyrics = _dc("ly2", lyrics); translate = _dc("tr", _tr_nocache_partial(translate))
# ---- lyrics2-20261111: language-aware lyrics pick (Telugu song must not get Tamil/Hindi lyrics) ----
_LYSC = {"te": r"[\u0C00-\u0C7F]", "ta": r"[\u0B80-\u0BFF]", "hi": r"[\u0900-\u097F]", "kn": r"[\u0C80-\u0CFF]", "ml": r"[\u0D00-\u0D7F]"}
_LYN = {"te": "Telugu", "ta": "Tamil", "hi": "Hindi", "kn": "Kannada", "ml": "Malayalam"}
_LYW = {  # distinctive romanized words (shared words like nee/naa/kanna left out on purpose)
    "te": set("nenu nuvvu nuvve ninnu nannu ninne naaku neeku naatho neetho manasu manasa gunde gundello prema premalo ledu ledhu ledule undi undhi unnadi unnave antha entha cheppu cheppave chesi chese choosi chusi chuse choode vachi vachindi vasthe raave ravee kadha kosam laga chala chaala inka ivvu avunu poyi poye poindi andham andhamaina kalalu kanulu kallu oohalu emaindi emito ayyo okka oka edho yedho nijam neeli ninnila nanne nee-tho padhi kaani kaadu ani anna jathaga jantaga cheli cheliya sakhi baava bava".split()),
    "ta": set("naan unnai ennai unakku enakku unnodu ennodu illa illai illaye enna kadhal kaadhal nenjil nenje nenjam kanne kannil pola polae polave vaa vaazh vaazhkai vaazhkkai ellaam ellam thaan dhaan irukku irukken irundhu aval avan mattum ippo ippodhu sollu solla sonnaal paaru paarthu paarvai uyire uyir azhagu azhage penne ponnu machan nenaichu ninaivu kanavu kanave nilave vaanam mazhai thoda theriyum theriyala venum vendum podhum aagum aanaal adi adiye unna enna-va".split()),
    "hi": set("hai hain mein tum tera teri tere mera meri mere dil nahi nahin kya pyaar pyar ishq jaana saath yeh woh kabhi bhi hum tujhe mujhe aaj raat sanam piya rang zindagi aankhein dekho kaise jaise tumhe humko jaan chahat dard bas yaara yaar kuch".split()),
}
def _ly_lang(body):
    """'te'/'ta'/'hi'/'kn'/'ml' from the script, else from romanized words; '' when unsure (e.g. English-only lines)."""
    body = body or ""
    c = {k: len(re.findall(p, body)) for k, p in _LYSC.items()}; k = max(c, key=c.get)
    if c[k] >= 8: return k
    w = set(re.findall(r"[a-z]+", body.lower())); sc = sorted(((len(w & v), k2) for k2, v in _LYW.items()), reverse=True)
    return sc[0][1] if sc[0][0] >= 3 and sc[0][0] >= 2 * sc[1][0] else ""
def lyrics_l(t, a, d, lang):
    """Like lyrics() but only returns a candidate in `lang`. Wrong-language hits are rejected even when the
    duration matches; romanized/English-only entries inherit the language of a same-name same-length sibling."""
    if lang not in _LYN: return lyrics(t, a, d)
    base = "https://lrclib.net/api/"; hd = {"User-Agent": "music-stream (personal)"}; LN = _LYN[lang]
    t2 = re.sub(r"\s*[\(\[][^)\]]*(official|video|audio|lyric|4k|hd|visualizer|mv)[^)\]]*[\)\]]", "", t, flags=re.I)
    if " - " in t2 and (not a or a.lower().endswith("vevo") or "topic" in a.lower()): a, t2 = t2.split(" - ", 1)
    elif " - " in t2: a2, t3 = t2.split(" - ", 1); a, t2 = a2, t3
    a = re.sub(r"(VEVO| - Topic)$", "", a or "").strip(); t2 = re.sub(r"\s*\|.*$", "", t2).strip()
    seen, r = set(), []
    for p in ({"track_name": t2, "artist_name": a}, {"q": f"{a} {t2}"}, {"q": f"{t2} {LN}"}, {"track_name": t2}):
        if not p.get("track_name", p.get("q", "")).strip() or ("artist_name" in p and not a): continue
        try: res = json.load(urllib.request.urlopen(urllib.request.Request(base + "search?" + urllib.parse.urlencode(p), headers=hd), timeout=8))
        except Exception: res = []
        for x in res or []:
            if x.get("id") in seen: continue
            seen.add(x.get("id")); r.append(x)
        if sum(1 for x in r if x.get("syncedLyrics")) >= 40: break
    r = [x for x in r if not _ly_mismatch(f"{t2} {a}".strip(), (x.get("syncedLyrics") or "") + (x.get("plainLyrics") or "") + (x.get("trackName") or ""))]
    for x in r: x["_lg"] = _ly_lang((x.get("syncedLyrics") or x.get("plainLyrics") or "") + " " + (x.get("albumName") or ""))
    _nm = lambda x: re.sub(r"[^a-z0-9]", "", (x.get("trackName") or "").lower())
    for x in r:  # English-only / unsure entry: same song name + same length as a sure entry -> same version
        if not x["_lg"]:
            sib = [y["_lg"] for y in r if y["_lg"] and _nm(y) == _nm(x) and abs((y.get("duration") or 0) - (x.get("duration") or 0)) <= 1.5]
            if sib: x["_lg"] = max(set(sib), key=sib.count)
    ok = [x for x in r if x["_lg"] == lang] or [x for x in r if not x["_lg"]]
    if not ok or not any(x.get("syncedLyrics") for x in ok):
        try:
            import syncedlyrics
            box = {}
            th = threading.Thread(target=lambda: box.update(r=syncedlyrics.search(f"{t2} {LN}".strip(), providers=["Musixmatch", "NetEase"], synced_only=True)), daemon=True)
            th.start(); th.join(10); lrc = box.get("r")
            if lrc and _ly_lang(lrc) in (lang, "") and not _ly_mismatch(t2, lrc): return {"synced": lrc, "plain": "", "name": t2, "artist": a, "src": "syncedlyrics", "lang": _ly_lang(lrc) or lang}
        except Exception: pass
    if not ok:
        oth = [x for x in r if x["_lg"] and x["_lg"] != lang]
        if not oth: return {}
        x = _ly_sort(oth, t, d)[0]
        return {"langmismatch": 1, "want": lang, "lang": x["_lg"], "synced": x.get("syncedLyrics") or "", "plain": x.get("plainLyrics") or "", "name": x.get("trackName"), "artist": x.get("artistName"), "dur": x.get("duration") or 0, "album": x.get("albumName") or ""}
    x = _ly_sort(ok, t, d)[0]
    return {"synced": x.get("syncedLyrics") or "", "plain": x.get("plainLyrics") or "", "name": x.get("trackName"), "artist": x.get("artistName"), "dur": x.get("duration") or 0, "album": x.get("albumName") or "", "lang": x["_lg"] or lang}
def _ly_sort(r, t, d):
    """Same ordering as lyrics(): synced first, no live/remix cut, closest duration / most-agreed version."""
    _VERW = r"\b(live|concert|tribute|wembley|rio|montreal|unplugged|acoustic|drumless|karaoke|instrumental|remix|cover|slowed|reverb|sped|8d|demo|session)\b"
    tl = (t or "").lower()
    def _pen(x):
        nm = f"{x.get('albumName') or ''} {x.get('trackName') or ''}".lower()
        return any(w not in tl for w in re.findall(_VERW, nm))
    def _fl(x):
        m0 = re.search(r"\[(\d+):(\d+(?:\.\d+)?)\]", x.get("syncedLyrics") or ""); return float(m0.group(1)) * 60 + float(m0.group(2)) if m0 else -1
    _ag = {id(x): sum(1 for y in r if y.get("syncedLyrics") and abs((y.get("duration") or 0) - (x.get("duration") or 0)) <= 1 and abs(_fl(y) - _fl(x)) < .6) for x in r}
    _agree = lambda x: _ag.get(id(x), 0)
    if d: return sorted(r, key=lambda x: (not x.get("syncedLyrics"), _pen(x), abs((x.get("duration") or 0) - d) > 4, -min(_agree(x), 5) if abs((x.get("duration") or 0) - d) > 4 else 0, abs((x.get("duration") or 0) - d)))
    return sorted(r, key=lambda x: (not x.get("syncedLyrics"), _pen(x), -min(_agree(x), 5)))
lyrics_l = _dc("ly3", lyrics_l)
# ---- /lyrics2-20261111 ----

PWA = {"/manifest.webmanifest", "/sw.js", "/icon-192.png", "/icon-512.png", "/favicon.ico", "/icon.svg", "/famkey.js", "/famlang.js"}  # server3-20261111 (no /game.js)
_kc = {}
def _ta(t, a):
    t2 = re.sub(r"\s*[\(\[][^)\]]*(official|video|audio|lyric|4k|hd|visualizer|mv)[^)\]]*[\)\]]", "", t, flags=re.I)
    if " - " in t2: a, t2 = t2.split(" - ", 1)
    return re.sub(r"\s*\|.*$", "", t2).strip(), re.sub(r"(VEVO| - Topic)$", "", a or "").strip()
def karaoke(t, a):
    """Word-level (enhanced LRC) lyrics via syncedlyrics (Musixmatch richsync). Runs with an 12s cap; {} if none."""
    t2, a2 = _ta(t, a); key = (t2.lower(), a2.lower())
    if key in _kc: return _kc[key]
    box = {}
    def go():
        try:
            import syncedlyrics
            box["r"] = syncedlyrics.search(f"{t2} {a2}".strip(), enhanced=True, providers=["Musixmatch"])
        except Exception: pass
    th = threading.Thread(target=go, daemon=True); th.start(); th.join(12)
    r = box.get("r") or ""
    out = {"lrc": r} if re.search(r"<\d+:\d+", r) else {}
    if len(_kc) > 300: _kc.clear()
    _kc[key] = out; return out
karaoke = _dc("kk", karaoke)
_simc = {}
def similar(t, a):
    """Similar tracks: Last.fm track.getSimilar if LASTFM_KEY set (free key), else ListenBrainz similar-artists (no key) via MusicBrainz."""
    t2, a2 = _ta(t, a); key = (t2.lower(), a2.lower()); c = _simc.get(key)
    if c and time.time() - c[1] < 6 * 3600: return c[0]
    hd = {"User-Agent": "music-stream/1.1 (personal player)"}; g = lambda u: json.load(urllib.request.urlopen(urllib.request.Request(u, headers=hd), timeout=8)); out = []
    lf = cfg.get("LASTFM_KEY")
    if lf and a2:
        try:
            j = g("https://ws.audioscrobbler.com/2.0/?" + urllib.parse.urlencode({"method": "track.getsimilar", "artist": a2, "track": t2, "api_key": lf, "format": "json", "limit": 15, "autocorrect": 1}))
            out = [{"id": None, "q": f"{x['artist']['name']} - {x['name']}", "title": x["name"], "channel": x["artist"]["name"], "dur": None, "sim": "lastfm"} for x in j.get("similartracks", {}).get("track", [])]
        except Exception: out = []
    if not out and a2:
        a3 = re.split(r",| & | x | feat\.? | ft\.? ", a2, flags=re.I)[0].strip()
        mb = g("https://musicbrainz.org/ws/2/artist/?fmt=json&limit=1&query=" + urllib.parse.quote(f'artist:"{a3}"')).get("artists", [])
        if mb and mb[0].get("score", 0) >= 90:
            s = g("https://labs.api.listenbrainz.org/similar-artists/json?algorithm=session_based_days_7500_session_300_contribution_5_threshold_10_limit_100_filter_True_skip_30&artist_mbids=" + mb[0]["id"])
            out = [{"id": None, "q": f"{x['name']} top song", "title": f"{x['name']} (similar artist)", "channel": x["name"], "dur": None, "sim": "listenbrainz"} for x in s[:8]]
    _simc[key] = (out, time.time()); return out
ROOMS = {}
def room(qs):
    """Listen-together: host pushes {id,title,channel,t,p}; guests poll and follow. Rooms expire after 2h idle."""
    now = time.time()
    for c in [c for c, r in ROOMS.items() if now - r["ts"] > 7200]: ROOMS.pop(c, None)
    code = re.sub(r"[^A-Z0-9]", "", qs.get("r", "").upper())[:8]; op = qs.get("op", "get")
    if op == "new":
        code = secrets.token_hex(3).upper(); hk = secrets.token_urlsafe(8)
        ROOMS[code] = {"hk": hk, "ts": now, "id": None, "t": 0, "p": False, "title": "", "channel": "", "n": {}}
        return {"r": code, "hk": hk}
    r = ROOMS.get(code)
    if not r: return {"error": "no room"}
    if op == "set":
        if not secrets.compare_digest(qs.get("hk", ""), r["hk"]): return {"error": "not host"}
        r.update(ts=now, id=qs.get("id") if VID.match(qs.get("id", "")) else r["id"], t=float(qs.get("t", 0) or 0), p=qs.get("p") == "1", title=qs.get("title", "")[:200], channel=qs.get("channel", "")[:100])
        return {"ok": 1, "listeners": sum(1 for v in r["n"].values() if now - v < 15)}
    r["n"][qs.get("me", "?")[:16]] = now
    return {"id": r["id"], "t": r["t"] + ((now - r["ts"]) if r["p"] else 0), "p": r["p"], "title": r["title"], "channel": r["channel"], "age": now - r["ts"], "listeners": sum(1 for v in r["n"].values() if now - v < 15)}
_hits = {}
_hits_lock = threading.Lock()
def limited(key, n=120, win=60):
    """Sliding-window rate limit. key is opaque."""
    if not key: key = "unknown"
    t = time.time()
    with _hits_lock:
        L = [x for x in _hits.get(key, []) if t - x < win]
        L.append(t)
        _hits[key] = L
        if len(_hits) > 8000:
            dead = [k for k, v in _hits.items() if not v or t - v[-1] >= win]
            for k in dead[:4000]: _hits.pop(k, None)
        return len(L) > n

def _peer_ip(handler):
    peer = (handler.client_address[0] if handler.client_address else "") or ""
    if peer.startswith("::ffff:"): peer = peer[7:]
    return peer

def _is_loopback(ip):
    return ip in ("127.0.0.1", "::1", "localhost") or ip.startswith("127.")

def _public_ip_key(handler):
    """Trust CF-Connecting-IP only when TCP peer is loopback (cloudflared / local proxy)."""
    peer = _peer_ip(handler)
    if _is_loopback(peer):
        cf = (handler.headers.get("CF-Connecting-IP") or handler.headers.get("Cf-Connecting-Ip") or "").strip()
        if cf and len(cf) <= 45 and re.match(r"^[0-9a-fA-F:.]+$", cf) and "," not in cf:
            if not _is_loopback(cf):
                return "cf:" + cf
        return "peer:" + peer
    return "peer:" + peer

# Back-compat alias used by tests / callers
def _client_limit_key(handler):
    return _public_ip_key(handler)

def _qs_from_handler(handler):
    try:
        return {k: v[0] for k, v in urllib.parse.parse_qs(urllib.parse.urlparse(handler.path).query).items()}
    except Exception:
        return {}


# cookie-20261110: long-lived auth cookie (1y, HttpOnly, SameSite=Lax, Secure over HTTPS).
# Set only when a real key is presented in ?k= or X-Music-Key; accepted later without the key.
# Token is HMAC-SHA256(KEY, "ms-auth-v1:"+presented_key) so the raw key is never stored in the cookie.
import hmac as _ms_hmac
_AUTH_COOKIE, _AUTH_MAX_AGE = "ms_auth", 31536000
def _auth_token(k):
    return _ms_hmac.new((KEY or "").encode(), b"ms-auth-v1:" + (k or "").encode(), _hsl.sha256).hexdigest()
def _cookie_get(handler, name):
    raw = handler.headers.get("Cookie") or ""
    m = re.search(r"(?:^|;\s*)" + re.escape(name) + r"=([0-9a-fA-F]{64})(?:;|$)", raw)
    return m.group(1) if m else ""
def _presented_key(handler):
    qs = _qs_from_handler(handler)
    return (qs.get("k") or (handler.headers.get("X-Music-Key") or "").strip() or "")
def _auth_cookie_ok(handler):
    v = _cookie_get(handler, _AUTH_COOKIE)
    if not v: return False
    if secrets.compare_digest(v, _auth_token(KEY)): return True
    return any(secrets.compare_digest(v, _auth_token(x)) for x in USERS)
def _req_authok(handler):
    """OPEN / trusted LAN / presented key / auth cookie."""
    if OPEN: return True
    if getattr(_REQ, "trusted", False): return True
    if getattr(_REQ, "user", None): return True  # login-20261110: signed-in user session
    k = _presented_key(handler)
    if k and _keyok(k): return True
    return _auth_cookie_ok(handler)
def _owner_authok(handler):
    """Owner KEY in query/header, or the auth cookie minted from the owner KEY."""
    _u = getattr(_REQ, "user", None)
    if _u and _u.get("role") == "admin": return True  # login-20261110: admin session counts as owner
    k = _presented_key(handler)
    if k and secrets.compare_digest(k, KEY): return True
    v = _cookie_get(handler, _AUTH_COOKIE)
    return bool(v) and secrets.compare_digest(v, _auth_token(KEY))

def _request_has_valid_key(handler):
    if OPEN: return True
    if getattr(_REQ, "trusted", False): return True  # sec-20261110
    if getattr(_REQ, "user", None): return True  # login-20261110
    try:
        k = _presented_key(handler)
        if k and _keyok(k): return True
        return _auth_cookie_ok(handler)
    except Exception:
        return False

def _client_id(handler):
    """Existing client id from header, cookie, or query. Sanitized. Does not mint."""
    for hdr in ("X-MS-Client", "X-Music-Client", "X-Ms-Client"):
        h = (handler.headers.get(hdr) or "").strip()
        if h and re.match(r"^[\w.-]{4,64}$", h):
            return h[:64]
    cookie = handler.headers.get("Cookie") or ""
    m = re.search(r"(?:^|;\s*)ms_cid=([\w.-]{4,64})", cookie)
    if m:
        return m.group(1)[:64]
    qs = _qs_from_handler(handler)
    for name in ("cid", "u"):
        v = (qs.get(name) or "").strip()
        if v and re.match(r"^[\w.-]{4,64}$", v):
            return v[:64]
    return None

def _ensure_client_id(handler):
    """For valid-key requests: reuse ms_cid / header, or mint and mark Set-Cookie.
    Prefer server cookie so real browsers (no player change) get per-tab/device buckets."""
    existing = _client_id(handler)
    if existing:
        handler._ms_cid = existing
        handler._ms_cid_is_new = False
        return existing
    if not _request_has_valid_key(handler):
        return None
    cid = secrets.token_urlsafe(12)[:24]
    if not re.match(r"^[\w.-]{4,64}$", cid):
        cid = "c" + secrets.token_hex(8)
    handler._ms_cid = cid
    handler._ms_cid_is_new = True
    return cid

def _limit_bucket_keys(handler):
    """Return (ip_key, client_key). Valid-key + client id → per-session bucket; else IP-only."""
    ip_key = _public_ip_key(handler)
    if _request_has_valid_key(handler):
        cid = _ensure_client_id(handler)
        if cid:
            return ip_key, f"{ip_key}|c:{cid}"
    try:  # server3-20261111: signed-in users (login cookie, no key) get a bucket per user
        _u = getattr(_REQ, "user", None)
        if isinstance(_u, dict) and _u.get("u"):
            return ip_key, f"{ip_key}|u:{_u['u']}"
    except Exception:
        pass
    return ip_key, ip_key

# Stream/chunk + static assets: never rate-limit (auth still applies downstream).
_RL_EXEMPT_EXACT = frozenset({
    "/health", "/favicon.ico", "/manifest.webmanifest", "/sw.js",
    "/icon-192.png", "/icon-512.png", "/icon.svg", "/famkey.js", "/famlang.js",
})
_RL_EXEMPT_PREFIX = ("/audio", "/video", "/stream", "/dl", "/skins/", "/viz-demo", "/art", "/vendor/", "/assets/")
# Heavy endpoints — per authenticated client (radio/search cached → allow household fan-out).
_RL_HEAVY = frozenset({
    "/api/search", "/api/radio", "/api/warm", "/api/prefetch", "/api/list", "/api/home",
    "/api/similar", "/api/chips", "/api/suggest", "/api/playable",
})
# Per-client budgets (10 users behind one Wi‑Fi / one public IP).
_RL_DEFAULT_N, _RL_DEFAULT_WIN = 180, 60
_RL_HEAVY_N, _RL_HEAVY_WIN = 120, 60
_RL_POST_N, _RL_POST_WIN = 60, 60
# Global per-IP ceiling (abuse: many forged client ids). Exempt paths skip both.
_RL_IP_CEIL_N, _RL_IP_CEIL_WIN = 900, 60

def _rate_limit_exempt(path):
    if path in _RL_EXEMPT_EXACT: return True
    if path == "/": return True
    for pref in _RL_EXEMPT_PREFIX:
        if path == pref or path.startswith(pref if pref.endswith("/") else pref + "/") or path.startswith(pref + "?"):
            return True
        if path == pref.rstrip("/"): return True
    return False

def _rate_limit_budget(path, method="GET"):
    if method == "POST": return _RL_POST_N, _RL_POST_WIN
    if path in _RL_HEAVY: return _RL_HEAVY_N, _RL_HEAVY_WIN
    return _RL_DEFAULT_N, _RL_DEFAULT_WIN

_RAD_JUNK = re.compile(r"\b(full (hd |length |action |telugu |tamil |hindi )*movie|full film|dubb(ed|ing)|documentary|motivational|attacks?|facts|explained|full album|greatest hits|best songs of|best of .* collection|songs collection|collection #|non ?stop|1 hour|2 hours?|10 hours?)\b", re.I)
_SK_JUNK = re.compile(r"\b(official|music|video|videos|audio|lyrics?|lyrical|hd|4k|8d|remaster(?:ed)?|live|full(?:\s+song)?|song|songs|with|slowed|reverb(?:ed)?|remix|cover|version|feat(?:uring)?|ft|visualizer|visualiser|mv|hq|1080p|720p|topic|vevo)\b", re.I)
# v68: stronger composition key — strips version/upload-style tags (3D/8D audio, lofi, slowed, lyric, title track,
# female/male version…), prefers quoted song names and "Movie: Song" right side; plus duration+fuzzy-title compare.
_SK_VAR = re.compile(r"\b(\d{1,2}d(?:\s*(?:audio|sound|song))?|\d{1,2}k|lo\s*-?\s*fi|slowed(?:\s*\+?\s*reverb)?|reverb(?:ed)?|sped\s*up|bass\s*boost(?:ed)?|unplugged|reprise|acoustic|(?:fe)?male(?:\s*version)?|full\s*(?:video|song|audio|hd|length)?|title\s*(?:track|song)|lyrical|lyrics?|with\s*lyrics|extended(?:\s*(?:version|mix))?|remaster(?:ed)?|karaoke|instrumental|jukebox|whatsapp\s*status|status|ringtone|new\s*song|latest|hindi|bollywood|romantic|sad)\b", re.I)
# v68: rough Devanagari -> Latin so "तुम ही हो" keys like "Tum Hi Ho" (inherent-a + word-final schwa drop; no dictionary)
_DV_C = dict(zip("कखगघङचछजझञटठडढणतथदधनपफबभमयरलवशषसह", "k kh g gh n ch chh j jh n t th d dh n t th d dh n p ph b bh m y r l v sh sh s h".split()))
_DV_V = dict(zip("अआइईउऊऋएऐओऔ", "a aa i i u u ri e ai o au".split())); _DV_M = dict(zip("ािीुूृेैोौ", "aa i i u u ri e ai o au".split()))
def _dv(t):
    if not re.search(r"[\u0900-\u097f]", t): return t
    o = []; ch = list(t); n = len(ch)
    for i, c in enumerate(ch):
        nx = ch[i + 1] if i + 1 < n else ""
        if nx == "\u093c": nx = ch[i + 2] if i + 2 < n else ""
        if c in _DV_C:
            o.append(_DV_C[c])
            if nx in _DV_M or nx == "\u094d": continue
            if nx and (nx in _DV_C or nx in "\u0902\u0901"): o.append("a"); continue
            if not nx or not re.match(r"[\u0900-\u097f]", nx): continue  # word-final schwa drop
            o.append("a")
        elif c in _DV_M: o.append(_DV_M[c])
        elif c in _DV_V: o.append(_DV_V[c])
        elif c in "\u0902\u0901": o.append("n" if re.match(r"[\u0900-\u097f]", nx or " ") else "m")
        elif c in "\u094d\u093c\u0903": continue
        else: o.append(c)
    s = re.sub(r"([aeiou])\1+", r"\1", "".join(o))
    return re.sub(r"\b(ka|ki|ke|gana|git|geet|pura|bol ke sath|ke sath|ke sang|sangit|sangeet)\b", " ", s)
try:
    from unidecode import unidecode as _unidecode
except Exception:
    _unidecode = None
def _xlit(t):
    """v69: Devanagari via _dv (schwa-aware); any other non-Latin script via unidecode when installed."""
    t = _dv(t)
    if _unidecode and re.search(r"[^\x00-\x7f]", t):
        t = re.sub(r"[^\x00-\u024f\s]+", lambda m: _unidecode(m.group(0)), t).lower()
    return t
def _chn_norm(c):
    c = (c or "").lower(); c = re.sub(r"\s*-\s*topic$|vevo|official|music|records?|\s+", "", c); return c
def _sk_clean(t):
    t = re.sub(r"\b(ft\.?|feat\.?|featuring)\b.*$", " ", t, flags=re.I)
    if re.search(r"\w{4,}.*\s(by|sung by|singer)\s+\w", t): t = re.sub(r"\s(sung by|by|singer)\s+.*$", " ", t, flags=re.I)  # v69: "Song BY Artist"
    if re.search(r"\w{4,}.*\b(from|movie|film)\b", t): t = re.sub(r"\b(from|movie|film)\b.*$", " ", t, flags=re.I)
    t = _SK_VAR.sub(" ", t); t = _SK_JUNK.sub(" ", t); t = _SK_VAR.sub(" ", t)
    t = " ".join(w for w in re.split(r"[^\w]+", t) if w)
    t = re.sub(r"\b(\w+(?:\s+\w+){0,5})\s+\1\b", r"\1", t)  # v69: bilingual titles repeat the name ("अच्युतम केशवम Achyutam Keshavam") -> once; non-adjacent words kept
    return re.sub(r"([aeiou])\1+", r"\1", re.sub(r"[^\w]+", "", t))
def _song_keys(t):
    """v68 composition keys: 1 key, or 2 (left, right) for 'A - B' titles where we can't tell Artist-Song from Song-Movie."""
    t = _xlit(__import__("unicodedata").normalize("NFKC", t or "").lower())
    for x, y in (("\u2018", "'"), ("\u2019", "'"), ("\u201c", '"'), ("\u201d", '"')): t = t.replace(x, y)
    q = re.search(r'"([^"]{3,60})"', t) or re.search(r"(?:^|\s)'([^']{3,60})'(?:\s|$)", t)
    if q and len(_sk_clean(q.group(1))) >= 4: return (_sk_clean(q.group(1)),)
    t = re.sub(r"[\(\[\{][^\)\]\}]*[\)\]\}]", " ", t)
    t = re.split(r"\s*[|｜]\s*", t)[0]
    if ":" in t:  # "Movie: Song" / "Movie 2: Song"
        left, right = t.split(":", 1)
        if len(_sk_clean(right)) >= 4: t = right
    for sep in (" - ", " – ", " — ", " -- ", " ~ "):
        if sep in t:
            left, right = t.split(sep, 1)
            l, r = _sk_clean(left), _sk_clean(right)
            if len(r) < 4: return (l,)
            if len(l) < 4: return (r,)
            return (l, r)
    return (_sk_clean(t),)
def _song_key(t):
    ks = _song_keys(t); return ks[-1] if ks else ""
import difflib as _dl
def _sk_ratio(a, b):
    return _dl.SequenceMatcher(None, a, b, autojunk=False).ratio() if a and b else 0.0
def _sk_m(a, b, dd=None):
    if len(a) < 4 or len(b) < 4: return False
    if a == b: return True
    x, y = (a, b) if len(a) <= len(b) else (b, a)
    if len(x) >= 6 and x in y: return True  # Hawayein ⊂ hawayeinarijitsingh; tumhiho ⊂ tumhihoaashiqui2
    if len(x) >= 12 and _sk_ratio(x, y[:len(x)]) >= 0.9: return True  # v69 fuzzy prefix: "Achutam Keshavam - …" vs "Achyutam Keshavam Krishna…"
    r = _sk_ratio(a, b)
    if r >= 0.86: return True
    return dd is not None and dd <= 3 and r >= 0.7  # duration-plus-fuzzy-title
def _alt_keys(t):
    """v70: song-name keys hidden behind a leading '|' artist segment ("Arijit Singh | Pritam - Hawayein (Lyrics)"):
    every later '|' segment (max 3) that has an 'A - B' / 'Movie: Song' split contributes both sides (>=6 chars)."""
    t = _xlit(__import__("unicodedata").normalize("NFKC", t or "").lower())
    t = re.sub(r"[\(\[\{][^\)\]\}]*[\)\]\}]", " ", t)
    out = []
    for seg in re.split(r"\s*[|｜]\s*", t)[1:4]:
        for sep in (" - ", " – ", " — ", ": "):
            if sep in seg:
                for side in seg.split(sep, 1):
                    k = _sk_clean(side)
                    if len(k) >= 6: out.append(k)
                break
    return tuple(out)
_PAREN_SKIP = re.compile(r"^\s*(from|film|movie|feat|ft|with|by|prod|official|lyric|lyrical|lyrics|full|video|audio|song|female|male|version|reprise|remix|lofi|lo-fi|slowed|unplugged|live|cover|karaoke|instrumental|\d)", re.I)
def _paren_keys(t):
    """v72: explicit alias in brackets that NAMES another song, e.g. "Kaun Kehte Hain Bhagwan Aate Nahi (Achyutam Keshavam)".
    Only bracket text that is not a version/credit/movie tag, cleaned to >=10 chars. Used as a prefix alias, never as a substring
    match against arbitrary chants."""
    t = _xlit(__import__("unicodedata").normalize("NFKC", t or "").lower())
    out = []
    for m in re.finditer(r"[\(\[]([^\)\]]{4,60})[\)\]]", t):
        c = m.group(1)
        if _PAREN_SKIP.search(c): continue
        k = _sk_clean(c)
        if len(k) >= 10: out.append(k)
    return tuple(out[:2])
def _paren_m(p, f):
    """alias p names song f: p is a fuzzy prefix of f (>=0.9) and covers >=40% of f, or near-equal."""
    if len(p) < 10 or len(f) < 10: return False
    if _sk_ratio(p, f) >= 0.88: return True
    return len(p) >= 0.4 * len(f) and _sk_ratio(p, f[:len(p)]) >= 0.9
def _sk_alt_m(a, b):
    return len(a) >= 6 and len(b) >= 6 and (a == b or _sk_ratio(a, b) >= 0.92)
class _SkSeen:
    """Seen compositions: list of (keys, dur); v70 also alt keys + channel."""
    def __init__(self): self.L = []; self.C = []; self.A = []; self.P = []
    def __bool__(self): return bool(self.L)
    def add(self, t, dur=0, ch=""):
        ks = tuple(k for k in _song_keys(t) if len(k) >= 4)
        if ks: self.L.append((ks, float(dur or 0))); self.C.append(_chn_norm(ch)); self.A.append(_alt_keys(t)); self.P.append(_paren_keys(t))
    def hit(self, t, dur=0, ch=""):
        ks = tuple(k for k in _song_keys(t) if len(k) >= 4)
        if not ks: return False
        # v70 alt keys: candidate's hidden song name vs seen primary keys, and seen alt keys vs candidate primary keys
        ak = _alt_keys(t); pk = _paren_keys(t)
        for n_, (fs, _d) in enumerate(self.L):
            if (len(fs) == 1 and any(_sk_alt_m(a, fs[0]) for a in ak)) or (len(ks) == 1 and any(_sk_alt_m(a, ks[0]) for a in self.A[n_])): return True
            # v72 bracket alias names a seen song (or a seen title's bracket alias names this one)
            if any(_paren_m(p_, f) for p_ in pk for f in fs) or any(_paren_m(p_, k) for p_ in self.P[n_] for k in ks): return True
        # SEO-stuffed uploads ("Other Bhajan | अच्युतम केशवं कृष्ण दामोदरं | …"): a long (>=3-word) secondary "|" segment that
        # near-equals an already seen song counts as that song. Short segments (movie names) are ignored.
        for seg in re.split(r"\s*[|｜]\s*", _xlit(__import__("unicodedata").normalize("NFKC", t or "").lower()))[1:4]:
            if len(_fn(_SK_JUNK.sub(" ", seg)).split()) < 3: continue
            sk2 = _sk_clean(seg)
            if len(sk2) >= 10 and any(_sk_ratio(sk2, f) >= 0.86 or (len(sk2) >= 12 and len(f) >= 12 and _sk_ratio(sk2, f[:len(sk2) + 1]) >= 0.9) for fs, _ in self.L for f in fs): return True  # v70: SEO segment = prefix of a seen song name
        d = float(dur or 0); cn = _chn_norm(ch)
        for n_, (fs, d2) in enumerate(self.L):
            dd = abs(d - d2) if d and d2 else None
            # v69 duration-plus-channel: same uploader channel, same length (±2 s), loosely similar title = re-upload
            if cn and dd is not None and dd <= 2 and self.C[n_] == cn and max(_sk_ratio(a, b) for a in ks for b in fs) >= 0.5: return True
            # v70 same-title + same-channel: same uploader and near-identical normalized title (any length/dur) = re-upload
            # (not for 'Artist - Song A' vs 'Artist - Song B': 2-key vs 2-key stays on the pair logic below; keys that are just the
            # channel/artist name never count)
            if cn and self.C[n_] == cn and (len(ks) == 1 or len(fs) == 1) and any(
                    len(a) >= 6 and len(b) >= 6 and _sk_ratio(a, b) >= 0.8 and _sk_ratio(a, cn) < 0.8 and _sk_ratio(b, cn) < 0.8
                    for a in ks for b in fs): return True
            if len(ks) == 1 or len(fs) == 1:
                if any(_sk_m(a, b, dd) for a in ks for b in fs): return True
            elif _sk_m(ks[0], fs[1], dd) or _sk_m(ks[1], fs[0], dd) or (_sk_m(ks[0], fs[0], dd) and _sk_m(ks[1], fs[1], dd)): return True
            else:
                # v69: "Adharam Madhuram Lofi - Krishna Bhajan" vs "Adharam Madhuram Vadanam Madhuram - Madhurashtakam":
                # left sides where one is a strict prefix of the other (>=12 chars) = same song name. Exact-equal lefts are
                # left alone (that is the "Artist - Song A" / "Artist - Song B" pattern).
                x_, y_ = sorted((ks[0], fs[0]), key=len)
                if x_ != y_ and len(x_) >= 12 and y_.startswith(x_): return True
        return False
def _key_seen(kk, seen):  # legacy helper (single-key); kept for callers/tests
    if not kk or len(kk) < 4: return False
    return any(_sk_m(kk, s) for s in seen)
def _rad_exf_pairs(a, k):
    """(title, channel) pairs from client exf."""
    cands = ([k.get("exf")] if isinstance(k, dict) and k.get("exf") is not None else []) + list(a)
    for cand in cands:
        if not isinstance(cand, (list, tuple)) or not cand: continue
        x0 = cand[0]
        if isinstance(x0, (list, tuple)): return [((it[0] if it else ""), (it[1] if len(it) > 1 else "")) for it in cand if isinstance(it, (list, tuple))]
        if isinstance(x0, str) and "\t" in x0: return [tuple((it.split("\t") + [""])[:2]) for it in cand if isinstance(it, str)]
    return []
def _rad_exf_titles(a, k):
    """Pull client exf titles (played/queued). exf is list of (title, channel) tuples."""
    titles = []
    cands = []
    if isinstance(k, dict) and k.get("exf") is not None: cands.append(k.get("exf"))
    cands.extend(a)
    exf = ()
    for cand in cands:
        if not isinstance(cand, (list, tuple)) or not cand: continue
        x0 = cand[0]
        if isinstance(x0, (list, tuple)): exf = cand; break
        if isinstance(x0, str) and "\t" in x0: exf = cand; break
    for it in exf:
        if isinstance(it, (list, tuple)): titles.append(it[0] if it else "")
        elif isinstance(it, dict): titles.append(it.get("title") or "")
        elif isinstance(it, str): titles.append(it.split("\t")[0] if "\t" in it else it)
    return titles
def _rad_clean(fn):
    def w(vid, *a, **k):
        out = fn(vid, *a, **k)
        if not isinstance(out, list): return out
        try: st = title_of(vid) or ""
        except Exception: st = ""
        long_ok = bool(re.search(r"jukebox|nonstop|non stop|mashup|mix\b", st, re.I))
        seen = _SkSeen(); seen.add(st, _YTSD.get(vid), _YTCH.get(vid, ""))
        for t0, c0 in _rad_exf_pairs(a, k): seen.add(t0, 0, c0)
        res = []
        for x in out:
            t = x.get("title") or ""; d = x.get("dur") or 0
            if x.get("id") and live_known(x["id"]): continue  # ms-v77: cached radio lists from before the live filter
            if not long_ok and (d > 1200 or _RAD_JUNK.search(t)): continue
            if seen.hit(t, d, x.get("channel")): continue
            seen.add(t, d, x.get("channel")); res.append(x)
        return res  # never reintroduce duplicates even if short
    w.__wrapped__ = fn; return w
_YTR = {}; _YTSD = {}; _YTCH = {}  # RD list cache; seed durations seen in RD lists
_CH = threading.local()  # per-request chain ids (last played/queued) for v68 chain-fetch
def _rd_list(vid):
    c = _YTR.get(vid)
    if c and c[0] and time.time() - c[1] <= RADIO_TTL: return c[0]
    L = _mixlist(vid, "RD" + vid, 40, 8)  # radio-20261111: innertube first (~1 s), yt-dlp flat only as fallback
    if not L:  # radio-20261111: an empty answer (YouTube slow / bot-check) must never stick for 2 h; reuse an older good copy
        return (c[0] if c and c[0] else None) or _radio_stale(vid).get("rd") or []
    if len(_YTR) > 300: _YTR.clear()
    _YTR[vid] = (L, time.time())
    try: _radio_disk_save(vid, mix="balanced", rd=L)
    except Exception: pass
    for x in L:
        if x.get("id") and x.get("dur") and len(_YTSD) < 5000: _YTSD.setdefault(x["id"], x["dur"])
        if x.get("id") and x.get("channel") and len(_YTCH) < 5000: _YTCH.setdefault(x["id"], x["channel"])
    return L
def _yt_radio(fn):
    """Primary autoplay source: YouTube mix list=RD<id>. Drop seed + ex ids + same compositions.
    v68: if seed RD comes back empty / fully deduped, chain-fetch RD of the last played/queued tracks,
    then fall back to the old algo. Never return empty when any source has something new."""
    def w(vid, ex=(), *a, **k):
        exs = set(ex or ()) | {vid}
        try: st = title_of(vid) or ""
        except Exception: st = ""
        long_ok = bool(re.search(r"jukebox|nonstop|non stop|mashup|mix\b", st, re.I))
        seen = _SkSeen()
        for t0, c0 in _rad_exf_pairs(a, k): seen.add(t0, 0, c0)
        out = []; t0 = time.time()
        def take(L, why):
            for x in L or ():
                i = x.get("id")
                if not i or i in exs: continue
                t = x.get("title") or ""; d = x.get("dur") or 0
                if not long_ok and (d > 1200 or _RAD_JUNK.search(t)): continue
                if seen.hit(t, d, x.get("channel")): continue
                seen.add(t, d, x.get("channel")); exs.add(i); out.append(dict(x, why=why) if why else x)
                if len(out) >= 20: return
        try:
            L = _rd_list(vid)
            sx = next((x for x in L if x.get("id") == vid), {})
            seen.add(st, sx.get("dur") or _YTSD.get(vid), sx.get("channel") or _YTCH.get(vid, ""))
            take(L, "yt_radio")
        except Exception: seen.add(st)
        if len(out) < 5:
            chain = [c for c in (getattr(_CH, "ids", None) or []) if c != vid][:4]
            for c in chain:
                if len(out) >= 8 or time.time() - t0 > 6: break  # radio-20261111
                try: take(_rd_list(c), "yt_radio_chain")
                except Exception: continue
        if len(out) >= 5: return out
        try: rest = fn(vid, ex, *a, **k) or []
        except Exception: rest = []
        if isinstance(rest, list): take(rest, None)
        return out
    w.__wrapped__ = fn; return w
def _memo_radio(fn, tag="radio"):
    """Cache final wrapped radio lists per (vid, mix, exclude-fingerprint) for RADIO_TTL."""
    def w(vid, ex=(), *a, **k):
        mix = ""
        try:
            # radio_fast signature: vid, exclude, exf, mix, ...
            if tag == "fast":
                mix = (a[1] if len(a) > 1 else k.get("mix", "")) or ""
            else:
                mix = k.get("mix", "") or (a[4] if len(a) > 4 else "")
        except Exception:
            mix = ""
        mx = _mix_norm(mix) if tag == "fast" else _mix_norm(str(mix)[:12])
        ex_fp = tuple(sorted(set(ex or ()) | {vid}))[:40]
        key = (tag, vid, mx, ex_fp)
        hit = _rcache.get(key)
        if hit and time.time() - hit[1] < RADIO_TTL:
            return list(hit[0])
        out = fn(vid, ex, *a, **k)
        if isinstance(out, list) and out:
            _rcache[key] = (list(out), time.time())
            try:
                if tag == "fast":
                    _radio_disk_save(vid, mix=mx, wrap_out=out)
            except Exception as e:
                print(f"wrap disk save {vid}: {e}", flush=True)
        return out
    w.__wrapped__ = getattr(fn, "__wrapped__", fn); return w

# ---- radio-20261111: radio must never "just fail" ------------------------------------------------------------------
# Root cause of the repeat failures: every radio list came from a yt-dlp scrape of YouTube's mix page (12-16 s timeouts,
# up to ~45 s chained), on a phone sharing 2 scrape slots with background prewarm, while the player gives up after 12 s.
# When YouTube was slow or bot-checking the phone, the list came back empty, the empty list was cached for 2 h, and the
# player showed "Could not load next songs". Now: the mix list comes from YouTube's own JSON "next" endpoint (~1 s, no
# yt-dlp), empty results are never cached, every /api/radio call is time-boxed, and a thin/empty/late answer is topped
# up from backup sources (older good list for this seed -> YouTube related videos -> radio of the last played songs ->
# a search on the artist) so the queue keeps going.
_YTREL = {}
def _yti_next(vid, pl=None, timeout=6):
    """YouTube mix list (playlistPanel) + related videos for vid from /youtubei/v1/next. Returns (mix, related)."""
    body = json.dumps({"context": {"client": {"clientName": "WEB", "clientVersion": _ITV, "hl": "en"}}, "videoId": vid, "playlistId": pl or ("RD" + vid)}).encode()
    j = json.loads(_yti_post("/youtubei/v1/next?prettyPrint=false", body, timeout).decode("utf-8", "replace"))
    twc = (j.get("contents") or {}).get("twoColumnWatchNextResults") or {}
    mix, rel = [], []
    for c in (((twc.get("playlist") or {}).get("playlist") or {}).get("contents") or []):
        v = c.get("playlistPanelVideoRenderer") or {}
        i = v.get("videoId") or ""; lt = _it_txt(v.get("lengthText"))
        if not VID.match(i) or not lt: continue  # no length = live/upcoming
        mix.append({"id": i, "title": _it_txt(v.get("title")) or "?", "dur": _it_dur(lt), "channel": _it_txt(v.get("longBylineText")) or _it_txt(v.get("shortBylineText"))})
    for r in (((twc.get("secondaryResults") or {}).get("secondaryResults") or {}).get("results") or []):
        lk = r.get("lockupViewModel") or {}
        if lk.get("contentType") != "LOCKUP_CONTENT_TYPE_VIDEO" or not VID.match(lk.get("contentId") or ""): continue
        md = (lk.get("metadata") or {}).get("lockupMetadataViewModel") or {}
        ch = ""
        try: ch = md["metadata"]["contentMetadataViewModel"]["metadataRows"][0]["metadataParts"][0]["text"]["content"]
        except Exception: pass
        m = re.search(r'"text": "(\d+(?::\d+){1,2})"', json.dumps(lk.get("contentImage") or {}))
        if not m: continue  # no length badge = live/upcoming
        rel.append({"id": lk["contentId"], "title": ((md.get("title") or {}).get("content")) or "?", "dur": _it_dur(m.group(1)), "channel": ch})
    for x in mix + rel:
        if x.get("title") and len(_TITLE) < 4000: _TITLE.setdefault(x["id"], x["title"])
        if x.get("dur") and len(_YTSD) < 5000: _YTSD.setdefault(x["id"], x["dur"])
        if x.get("channel") and len(_YTCH) < 5000: _YTCH.setdefault(x["id"], x["channel"])
    if rel:
        if len(_YTREL) > 300: _YTREL.clear()
        _YTREL[vid] = (rel, time.time())
    return mix, rel
def _mixlist(vid, pl, n=25, timeout=7):
    """Mix list for (vid, playlist id): innertube first, yt-dlp flat as fallback within the same time budget."""
    t0 = time.time()
    try:
        mix, _r = _yti_next(vid, pl, timeout=min(6, timeout))
        if len(mix) >= 5: return mix[:n]
    except Exception as e:
        print(f"radio next fail {vid} {type(e).__name__}: {str(e)[:60]}", flush=True)
    left = timeout - (time.time() - t0)
    if left < 2.5: return []
    u = (f"https://music.youtube.com/watch?v={vid}&list={pl}" if pl.startswith("RDAMVM") else f"https://www.youtube.com/watch?v={vid}&list={pl}")
    try: return flat(u, n, timeout=left)
    except Exception: return []
def _mixlist_url(u, n=25, timeout=7):
    m = re.search(r"[?&]v=([\w-]{11}).*?[?&]list=([\w-]+)", u)
    if not m: return flat(u, n, timeout=timeout)
    return _mixlist(m.group(1), m.group(2), n, timeout)
def _radio_stale(vid, max_age=14 * 86400):
    """Any older good radio lists saved for this seed (ignores the 2 h freshness rule; a stale list beats silence)."""
    out = {}
    for mx in ("balanced", "familiar", "fresh"):
        path = _radio_disk_path(vid, mx)
        try:
            d = json.loads(path.read_text(encoding="utf-8"))
            if time.time() - d.get("t", 0) > max_age: continue
            for f in ("wrap_out", "fast_out", "fast", "base", "rd", "full"):
                if d.get(f) and not out.get(f): out[f] = d[f]
        except Exception: continue
    return out
RESCUE_MIN = int(cfg.get("RADIO_MIN", "12"))
def _tcall(_tl, fn, *a, **k):
    """Run fn in a daemon thread; give up after timeout seconds (a hung socket can't hold the radio answer)."""
    box = {}
    def go():
        try: box["r"] = fn(*a, **k)
        except Exception as e: box["e"] = e
    th = threading.Thread(target=go, daemon=True, name="radio-call"); th.start(); th.join(max(0.5, _tl))
    if "r" in box: return box["r"]
    if "e" in box: raise box["e"]
    raise TimeoutError("radio call timeout")
def _radio_rescue(vid, ex, a, k, have, deadline):
    exs = set(ex or ()) | {vid} | {x.get("id") for x in have}
    try: st = title_of(vid) or ""
    except Exception: st = ""
    long_ok = bool(re.search(r"jukebox|nonstop|non stop|mashup|mix\b", st, re.I))
    seen = _SkSeen(); seen.add(st, _YTSD.get(vid), _YTCH.get(vid, ""))
    try:
        for t0, c0 in _rad_exf_pairs(a, k): seen.add(t0, 0, c0)
    except Exception: pass
    for x in have: seen.add(x.get("title") or "", x.get("dur") or 0, x.get("channel"))
    out = list(have); used = []
    def take(L, why):
        n0 = len(out)
        for x in L or ():
            i = x.get("id")
            if not i or not VID.match(i) or i in exs: continue
            t = x.get("title") or ""; d = x.get("dur") or 0
            try:
                if live_known(i): continue
            except Exception: pass
            if not long_ok and (d > 1200 or _RAD_JUNK.search(t)): continue
            if seen.hit(t, d, x.get("channel")): continue
            seen.add(t, d, x.get("channel")); exs.add(i); out.append(dict(x, why=x.get("why") or why))
            if len(out) >= 24: break
        if len(out) > n0: used.append(f"{why}+{len(out) - n0}")
    full = lambda: len(out) >= 20 or time.time() > deadline
    # 1) older good lists for this seed (instant, no network)
    sd = _radio_stale(vid)
    for f in ("wrap_out", "fast_out", "fast", "full", "rd", "base"):
        if full(): break
        take(sd.get(f), "same_lane")
    c = _YTR.get(vid)
    if c and not full(): take(c[0], "same_lane")
    # 2) YouTube's own mix + related videos (one ~1 s call)
    if not full():
        try:
            rc = _YTREL.get(vid)
            if rc and time.time() - rc[1] < RADIO_TTL: mix, rel = [], rc[0]
            else:
                tl = max(1.5, min(5, deadline - time.time())); mix, rel = _tcall(tl + 0.5, _yti_next, vid, "RD" + vid, timeout=tl)
            take(mix, "same_lane"); take(rel, "similar_artist")
        except Exception as e: used.append(f"next:{type(e).__name__}")
    # 3) radio of the last played / queued songs
    for cid in [x for x in (getattr(_CH, "ids", None) or []) if x != vid][:3]:
        if full(): break
        try:
            L = (_YTR.get(cid) or [None])[0] or _radio_stale(cid).get("rd") or _tcall(max(1.5, min(4, deadline - time.time())) + 0.5, _yti_next, cid, "RD" + cid, timeout=max(1.5, min(4, deadline - time.time())))[0]
            take(L, "same_lane")
        except Exception: continue
    # 4) a plain search on the artist / song
    if not full():
        ch = re.sub(r"\s*-\s*topic$|vevo$", "", (_YTCH.get(vid) or (_seed_meta.get(vid) or {}).get("channel") or ""), flags=re.I).strip()
        q = f"{ch} songs" if ch else (f"{st} similar songs" if st else "")
        if q:
            try:
                tl = max(1.5, min(5, deadline - time.time())); r = _tcall(tl + 0.5, _fast_search, q, timeout=tl)
                take([{"id": e.get("id"), "title": e.get("title"), "dur": e.get("duration"), "channel": e.get("channel")} for e in r.get("entries") or [] if not e.get("live_status")], "similar_artist")
            except Exception as e: used.append(f"search:{type(e).__name__}")
    return out, used
_RG = {}; _RG_L = threading.Lock()
def _radio_guard(fn, tag, budget):
    """Answer inside `budget` seconds. Late, failed, empty or thin lists are topped up by _radio_rescue.
    The real lookup keeps running in the background and fills the caches for the next call."""
    def w(vid, ex=(), *a, **k):
        t0 = time.time(); chid = list(getattr(_CH, "ids", None) or []); bg = getattr(_BG, "on", False)
        try: key = (tag, vid, hash(repr((sorted(set(ex or ())), a, sorted(k.items())))))
        except Exception: key = (tag, vid, t0)
        with _RG_L:
            ent = _RG.get(key)
            if ent is None or (not ent[0].is_alive() and time.time() - ent[2] > 2):
                box = {}
                def go():
                    _CH.ids = chid; _BG.on = bg
                    try: box["r"] = fn(vid, ex, *a, **k)
                    except Exception as e: box["e"] = e
                ent = (threading.Thread(target=go, daemon=True, name="radio-" + tag), box, time.time()); _RG[key] = ent; ent[0].start()
                if len(_RG) > 200:
                    for kk in [kk for kk, vv in list(_RG.items()) if not vv[0].is_alive()]: _RG.pop(kk, None)
        th, box = ent[0], ent[1]; th.join(max(0.5, budget - (time.time() - t0)))
        got = box.get("r") if isinstance(box.get("r"), list) else []
        if len(got) >= RESCUE_MIN: return got
        why = "late" if th.is_alive() else ("error:" + type(box["e"]).__name__ if "e" in box else ("empty" if not got else "thin"))
        _CH.ids = chid
        try: res, used = _radio_rescue(vid, ex, a, k, got, t0 + budget + 3)
        except Exception as e: res, used = got, [f"rescue:{type(e).__name__}"]
        print(f"radio_guard {tag} {vid} {why} main={len(got)} out={len(res)} via={','.join(used) or '-'} ms={int((time.time() - t0) * 1000)}", flush=True)
        return res
    w.__wrapped__ = getattr(fn, "__wrapped__", fn); return w
RADIO_FAST_BUDGET = float(cfg.get("RADIO_FAST_BUDGET", "7")); RADIO_FULL_BUDGET = float(cfg.get("RADIO_FULL_BUDGET", "16"))
radio = _radio_guard(_rad_clean(_yt_radio(radio)), "full", RADIO_FULL_BUDGET); radio_fast = _radio_guard(_memo_radio(_rad_clean(_yt_radio(radio_fast)), "fast"), "fast", RADIO_FAST_BUDGET)  # radio-20261111
_pg = {"m": 0, "b": b""}
def _page():
    p = ROOT / "player.html"; m = p.stat().st_mtime
    if m != _pg["m"]: _pg.update(m=m, b=p.read_bytes())
    return _pg["b"]
# ---- dancefix 2026-11-10: download jobs (mp3 / YouTube Music audio / mp4 video) ----
# Old /dl streamed an ffmpeg pipe with a hard 90 s wall clock and no Content-Length: on a ~50-70 KB/s Wi-Fi link a
# 4-5 min song (6+ MB) was cut off mid-file, and the file was named after the video id. Jobs now build a real file
# in cache/dl in the background, report progress, and serve it with Content-Length, Range and "Artist - Title.ext".
DL_DIR = ROOT / "cache" / "dl"; DL_DIR.mkdir(parents=True, exist_ok=True)
DLJOBS = {}; _DLLOCK = threading.Lock(); _DLSEM = threading.Semaphore(2)
_DL_JUNK = re.compile(r"\s*[\(\[](?:official\s*(?:music\s*)?(?:video|audio|lyric(?:s)?\s*video|visuali[sz]er)|lyrics?|audio|video|hd|4k|mv|m/v)[^\)\]]*[\)\]]", re.I)
def _dl_name(title, artist):
    t = _DL_JUNK.sub("", title or "").strip(" -_|")
    a = re.sub(r"\s*-\s*topic$|vevo$", "", (artist or "").strip(), flags=re.I).strip()
    n = t if (" - " in t or not a or a.lower() in t.lower()) else f"{a} - {t}"
    n = re.sub(r'[\\/:*?"<>|\x00-\x1f]+', " ", n); n = re.sub(r"\s+", " ", n).strip(" .") or "track"
    return n[:120]
def _sb_music_only(vid):
    """keep-intervals after removing SponsorBlock non-music (music_offtopic) + sponsor/selfpromo/intro/outro/preview/interaction."""
    try:
        C = ["sponsor", "selfpromo", "interaction", "intro", "outro", "preview", "music_offtopic"]
        r = urllib.request.urlopen(urllib.request.Request("https://sponsor.ajay.app/api/skipSegments?" + urllib.parse.urlencode({"videoID": vid, "categories": json.dumps(C)}), headers={"User-Agent": "music-stream"}), timeout=6)
        segs = sorted((float(x["segment"][0]), float(x["segment"][1])) for x in json.load(r) if x.get("actionType", "skip") == "skip")
    except Exception:
        segs = []
    return segs
def _ffdur(path):
    try:
        out = subprocess.run([FFMPEG, "-i", str(path)], capture_output=True, text=True, timeout=30, creationflags=NOFLAGS, errors="replace").stderr
        m = re.search(r"Duration:\s*(\d+):(\d+):(\d+(?:\.\d+)?)", out)
        return int(m.group(1)) * 3600 + int(m.group(2)) * 60 + float(m.group(3)) if m else 0.0
    except Exception: return 0.0
def _ytm_match(title, artist):
    q = _DL_JUNK.sub("", title or "").strip()
    ar = re.sub(r"(?i)\s*-\s*topic$", "", artist or "")
    if ar and ar.lower() not in q.lower(): q = ar + " " + q
    out = subprocess.run(YTDLP + ["--flat-playlist", "-J", "--playlist-items", "1-3", "--no-warnings", "https://music.youtube.com/search?q=" + urllib.parse.quote(q) + "#songs"],
                         capture_output=True, text=True, timeout=60, creationflags=NOFLAGS, encoding="utf-8", errors="replace").stdout
    ents = [e for e in (json.loads(out or "{}").get("entries") or []) if e.get("id") and VID.match(e["id"])]
    return (ents[0]["id"], ents[0].get("title") or title) if ents else (None, None)
def _dl_meta(vid):
    """title/artist straight from YouTube when the client did not send them (so files are never named after the id)."""
    try:
        out = subprocess.run(YTDLP + ["--skip-download", "--no-warnings", "--no-playlist", "--print", "%(track,title)s\t%(artist,creator,uploader,channel)s", "https://www.youtube.com/watch?v=" + vid],
                             capture_output=True, text=True, timeout=60, creationflags=NOFLAGS, encoding="utf-8", errors="replace").stdout.strip().splitlines()
        t, _, a = (out[-1] if out else "").partition("\t")
        return (t if t and t != "NA" else ""), (a if a and a != "NA" else "")
    except Exception: return "", ""
def _dl_run(j):
    jd = DLJOBS[j]; vid = jd["vid"]; kind = jd["kind"]; tmpd = DL_DIR / ("tmp_" + j); tmpd.mkdir(exist_ok=True)
    def st(**kw): jd.update(kw); jd["t"] = time.time()
    def ytdl(args, url, lo, hi):
        p = subprocess.Popen(YTDLP + ["--newline", "--no-warnings", "--no-playlist", "-o", str(tmpd / "src.%(ext)s")] + args + [url],
                             stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, encoding="utf-8", errors="replace", creationflags=NOFLAGS)
        tail = []; deadline = time.time() + 2700  # hiresdl2: 4K/long videos need more than 15 min on a slow link
        for line in p.stdout:
            tail = (tail + [line.strip()])[-6:]
            m = re.search(r"\[download\]\s+([\d.]+)%", line)
            if m: st(pct=max(jd.get("pct") or 0, round(lo + (hi - lo) * float(m.group(1)) / 100, 1)))  # video+audio are two passes: never go backwards
            if time.time() > deadline: p.kill(); break
        if p.wait() != 0: raise RuntimeError("yt-dlp failed: " + (" ".join(tail)[-200:] or "unknown"))
        fs = [f for f in tmpd.iterdir() if f.name.startswith("src.") and not f.name.endswith(".part")]
        if not fs: raise RuntimeError("yt-dlp produced no file")
        return max(fs, key=lambda f: f.stat().st_size)
    def ff(args, out, dur, lo, hi):
        p = subprocess.Popen([FFMPEG, "-y", "-hide_banner", "-loglevel", "error", "-progress", "pipe:1", "-nostats"] + args + [str(out)],
                             stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, errors="replace", creationflags=NOFLAGS)
        for line in p.stdout:
            if line.startswith("out_time_us=") and dur:
                try: st(pct=round(lo + (hi - lo) * min(1.0, int(line.split("=")[1]) / 1e6 / dur), 1))
                except ValueError: pass
        err = p.stderr.read()[-300:]
        if p.wait() != 0: raise RuntimeError("ffmpeg failed: " + err)
    try:
        with _DLSEM:
            st(state="running", pct=1, msg="Starting")
            title, artist = jd.get("title") or title_of(vid) or vid, jd.get("artist") or ""
            if not jd.get("title") or not artist:
                st(msg="Reading track info"); mt, ma = _dl_meta(vid)
                if not jd.get("title") and mt: title = mt
                artist = artist or ma
            src_id = vid
            if kind == "ytm":
                st(msg="Finding the YouTube Music track")
                mid, mt = _ytm_match(title, artist)
                if not mid: raise RuntimeError("no YouTube Music match found")
                src_id = mid; jd["ytm_id"] = mid; jd["ytm_title"] = mt
            url = f"https://www.youtube.com/watch?v={src_id}"
            name = _dl_name(title, artist)
            if kind in ("mp3", "ytm"):
                st(msg="Downloading audio")
                src = ytdl(["-f", "bestaudio/best"], url, 2, 70)
                dur = _ffdur(src); args = ["-i", str(src), "-vn", "-map_metadata", "-1", "-metadata", f"title={name.split(' - ', 1)[-1]}", "-metadata", f"artist={name.split(' - ', 1)[0] if ' - ' in name else artist}"]
                a, b = jd.get("a"), jd.get("b")
                keep = None
                if jd.get("sb"):
                    segs = _sb_music_only(src_id); t0 = 0.0; keep = []
                    for s, e in segs:
                        if s > t0 + 0.5: keep.append((t0, s))
                        t0 = max(t0, e)
                    if dur and dur > t0 + 0.5: keep.append((t0, dur))
                    if not segs: keep = None
                    jd["sb_removed"] = round(sum(e - s for s, e in segs), 1)
                if keep:
                    expr = "+".join(f"between(t,{x:.3f},{y:.3f})" for x, y in keep)
                    args += ["-af", f"aselect='{expr}',asetpts=N/SR/TB"]; odur = sum(y - x for x, y in keep)
                else:
                    if a: args = ["-ss", str(a)] + args
                    if b: args += ["-to", str(float(b) - float(a or 0))] if a else ["-to", str(b)]
                    odur = (float(b) if b else dur) - float(a or 0)
                st(msg="Converting to MP3")
                out = tmpd / "out.mp3"; ff(args + ["-c:a", "libmp3lame", "-q:a", "2", "-id3v2_version", "3"], out, odur, 70, 99)
                ext, ctype = "mp3", "audio/mpeg"
            else:
                # hiresdl2: res can be 360..2160 or "max". YouTube only has H.264 (avc1) up to 1080p; 1440p/2160p exist only as
                # AV1 (mp4) or VP9 (webm) video-only streams, so those are merged with the m4a audio into an MP4 by ffmpeg.
                r_ = 0 if jd.get("res") == "max" else int(jd.get("res") or 720); hq = f"[height<={r_}]" if r_ else ""
                st(msg=f"Downloading {r_ or 'best'}{'p' if r_ else ''} video")
                fmt = (f"bv*{hq}[vcodec^=avc1]+ba[ext=m4a]/" if r_ and r_ <= 1080 else "") + f"bv*{hq}+ba[ext=m4a]/bv*{hq}+ba/b{hq}/b"
                _ffp = __import__("shutil").which(FFMPEG)
                src = ytdl(["-f", fmt, "-S", "res,fps", "--merge-output-format", "mp4", "-N", "4"] + (["--ffmpeg-location", _ffp] if _ffp else []), url, 2, 97)
                out = tmpd / "out.mp4"
                if src.suffix.lower() == ".mp4": src.replace(out)
                else: st(msg="Packaging MP4"); ff(["-i", str(src), "-c", "copy", "-movflags", "+faststart"], out, _ffdur(src), 97, 99)
                ext, ctype = "mp4", "video/mp4"
                try:  # hiresdl2: label with the real height (a 1080p request on a 720p-max video gives a 720p file)
                    _i = subprocess.run([FFMPEG, "-i", str(out)], capture_output=True, text=True, timeout=30, creationflags=NOFLAGS, errors="replace").stderr
                    _m = re.search(r"Video:.*?\b(\d{3,4})x(\d{3,4})\b", _i); jd["got_h"] = int(_m.group(2)) if _m else None
                except Exception: jd["got_h"] = None
                _h = jd.get("got_h") or r_; name = f"{name} ({_h}p)" if _h else name
            final = DL_DIR / f"{j}.{ext}"; out.replace(final)
            st(state="done", pct=100, msg="Ready", file=str(final), size=final.stat().st_size, name=f"{name}.{ext}", ctype=ctype, secs=round(time.time() - jd["t0"], 1))
    except Exception as e:
        st(state="error", msg=str(e)[:300])
    finally:
        try:
            for f in tmpd.iterdir(): f.unlink()
            tmpd.rmdir()
        except Exception: pass
# --- speed-20261110: background lookups wait while a song someone picked is being looked up ---
_FGN = [0]; _FGL = threading.Lock(); _FG_LAST = [0.0]
class _fg:
    def __init__(s, vid=None): s.v = vid  # play4-20261111
    def __enter__(s):
        s.o = getattr(_TLF, "fg", False); _TLF.fg = True
        _FG_LAST[0] = time.time()  # perf2-20261112
        with _FGL:
            _FGN[0] += 1
            if s.v: _FGV[s.v] = _FGV.get(s.v, 0) + 1
    def __exit__(s, *a):
        _TLF.fg = s.o
        with _FGL:
            _FGN[0] -= 1
            if s.v:
                _FGV[s.v] = _FGV.get(s.v, 1) - 1
                if _FGV[s.v] <= 0: _FGV.pop(s.v, None)
def _fg_wait(limit=25):
    end = time.time() + limit
    while _FGN[0] > 0 and time.time() < end: time.sleep(0.25)
_WARMQ = []; _WARMQ_L = threading.Lock(); _WARMQ_EV = threading.Event()
def _warm_worker():
    while True:
        _WARMQ_EV.wait(30)
        with _WARMQ_L:
            job = _WARMQ.pop(0) if _WARMQ else None
            if not _WARMQ: _WARMQ_EV.clear()
        if not job: continue
        # speed-20261113: do not wait for foreground to go idle (that blocked prefetch
        # while a song was playing, so random/next tracks always paid a cold ~2 s lookup).
        # _XGate already keeps a slot for listeners.
        try:
            if job[1] == "vw":
                t0 = time.time()
                _vwarm(job[0], "h", need=720)
                x = _VINFO.get((job[0], "h")) or {}
                hs = ",".join(sorted((x.get("res") or {}), key=lambda z: int(z or 0)))
                print(f"warm vw {job[0]} ms={int((time.time()-t0)*1000)} rungs={hs} err=ok", flush=True)
            else:
                r = warm_url(*job, follow=True)  # lat-20261111
                if isinstance(r, dict):
                    print(f"warm {job[1] if len(job)>1 else 'std'} {job[0]} ms={r.get('ms')} err={r.get('err') or 'ok'}", flush=True)
        except Exception as e:
            print(f"warm fail {job}: {type(e).__name__}", flush=True)
# speed-20261113: every worker must drain /api/warm and search prefetch. Only quiet-warm stays on worker 0.
threading.Thread(target=_warm_worker, daemon=True).start()
WARM_PER_HOUR = max(0, int(cfg.get("WARM_PER_HOUR", "60") or 0)); _QW = {"n": 0, "hour": 0, "last": ""}  # perf2-20261112
def _quiet_warm():
    """When nobody has started a song for 2 min: pre-resolve stream URLs of the most played and recently played songs
    (low priority; stays far under YouTube's guest budget of ~300 lookups/hour)."""
    time.sleep(90)
    while True:
        time.sleep(60)
        try:
            if not WARM_PER_HOUR: continue
            h = int(time.time() // 3600)
            if h != _QW["hour"]: _QW.update(hour=h, n=0)
            if _QW["n"] >= WARM_PER_HOUR or _FGN[0] or _XG.act or time.time() - _FG_LAST[0] < 120 or time.time() - _BOTC[0] < 1800: continue
            d = _plays_load(); top = sorted((d.get("counts") or {}).items(), key=lambda kv: -int(kv[1] or 0))[:40]
            cand = list(dict.fromkeys([k for k, _ in top] + [x.get("id") for x in reversed(d.get("recent") or [])][:30]))
            done = 0
            for v in cand:
                if done >= 4 or _QW["n"] >= WARM_PER_HOUR or _FGN[0] or time.time() - _FG_LAST[0] < 120: break
                if not v or not VID.match(v) or live_known(v) or _ucache_load(v, "std"): continue
                if _disk_blob(v, "std"): continue  # already on disk: plays with no lookup at all
                _QW["n"] += 1; done += 1; _QW["last"] = v
                try: warm_url(v, "std")
                except Exception: pass
                time.sleep(5)
        except Exception as e: print(f"quiet warm skip {type(e).__name__}", flush=True)
if os.environ.get('MUSIC_WORKER_BG', '1') != '0':
    threading.Thread(target=_quiet_warm, daemon=True, name="quiet-warm").start()
def _warm_prefer(jobs):
    """Move these (vid, q) jobs to the front, keeping order. In-flight work is already popped."""
    with _WARMQ_L:
        n = 0
        seen, prefer = set(), []
        for j in jobs:
            if not j or j in seen:
                continue
            seen.add(j)
            if j not in _WARMQ:
                n += 1
            prefer.append(j)
        rest = [j for j in _WARMQ if j not in seen]
        _WARMQ[:] = (prefer + rest)[:40]
        if _WARMQ:
            _WARMQ_EV.set()
    return n
def _warm_enqueue(ids, fq, front=False):
    jobs = [(i, fq) for i in ids if i]
    if front:
        return _warm_prefer(jobs)
    with _WARMQ_L:
        n = 0
        for job in jobs:
            if job not in _WARMQ and len(_WARMQ) < 40:
                _WARMQ.append(job); n += 1
        if _WARMQ:
            _WARMQ_EV.set()
    return n
def dl_start(qs):
    vid = resolve(qs.get("id", "") or "")
    if not vid: return {"error": "bad id"}
    kind = qs.get("kind", "mp3"); kind = kind if kind in ("mp3", "ytm", "video") else "mp3"
    res = qs.get("res", "720"); res = res if res in ("360", "480", "720", "1080", "1440", "2160", "max") else "720"  # hiresdl2
    def num(x):
        try: v = float(x); return v if 0 <= v < 36000 else None
        except (TypeError, ValueError): return None
    a, b, sb = num(qs.get("a")), num(qs.get("b")), qs.get("sb") == "1"
    if a is not None and b is not None and b <= a: return {"error": "end must be after start"}
    key = f"{vid}|{kind}|{res if kind == 'video' else ''}|{a}|{b}|{int(sb)}"
    j = hashlib.sha1(key.encode()).hexdigest()[:16]
    with _DLLOCK:
        old = DLJOBS.get(j)
        if old and (old["state"] in ("queued", "running") or (old["state"] == "done" and Path(old.get("file", "")).exists())):
            _t = (qs.get("t") or "")[:200]
            if _t and not old.get("title"):  # an earlier request had no title: name the file properly now
                old["title"] = _t; old["artist"] = (qs.get("ar") or "")[:120]
                if old["state"] == "done" and old.get("name"):
                    _ext = old["name"].rsplit(".", 1)[-1]; _sfx = f" ({old['res']}p)" if old.get("kind") == "video" and old.get("res") else ""
                    old["name"] = f"{_dl_name(old['title'], old['artist'])}{_sfx}.{_ext}"
            return dl_public(j)
        # prune: keep the newest 40 finished files
        done = sorted((x for x in DLJOBS.values() if x.get("file")), key=lambda x: x["t"])
        for x in done[:-40]:
            try: Path(x["file"]).unlink()
            except Exception: pass
        DLJOBS[j] = {"id": j, "vid": vid, "kind": kind, "res": res, "a": a, "b": b, "sb": sb, "title": (qs.get("t") or "")[:200], "artist": (qs.get("ar") or "")[:120],
                     "state": "queued", "pct": 0, "msg": "Queued", "t": time.time(), "t0": time.time()}
    threading.Thread(target=_dl_run, args=(j,), daemon=True).start()
    return dl_public(j)
def dl_public(j):
    x = DLJOBS.get(j)
    if not x: return {"error": "no such job"}
    return {k: x.get(k) for k in ("id", "kind", "res", "state", "pct", "msg", "size", "name", "secs", "ytm_id", "ytm_title", "sb_removed", "got_h")}


# adult-viz-20261111: serve the 18+ visuals pack only to signed-in users whose admin-set flag is on.
def _ms_adult_path(path):
    p = (path or "").split("?")[0].replace("\\", "/")
    if not p.startswith("/"): p = "/" + p
    return p.startswith("/assets/dance/adult/") or p.startswith("/assets/chars/vrm/adult/") or p.startswith("/assets/viz/adult/")
def _ms_adult_allowed(handler=None):
    # request_user() returns None during must-change-password; those sessions must not unlock 18+ assets.
    user = getattr(_REQ, "user", None) or {}
    return bool(user.get("adult_viz"))

class H(BaseHTTPRequestHandler):
    server_version = "music"; sys_version = ""
    protocol_version = "HTTP/1.1"  # speed-20261113: keep-alive so reloads reuse the tunnel/origin socket
    timeout = 30
    def end_headers(self):
        # Issue persistent per-browser client id for keyed sessions (household same-IP rate buckets).
        if getattr(self, "_ms_cid_is_new", False) and getattr(self, "_ms_cid", None):
            self.send_header(
                "Set-Cookie",
                f"ms_cid={self._ms_cid}; Path=/; Max-Age=31536000; SameSite=Lax; HttpOnly" + ("; Secure" if _req_https(self) else ""),  # sec-20261110
            )
            self._ms_cid_is_new = False
        if getattr(self, "_ms_auth_set", False) and getattr(self, "_ms_auth_val", None):
            self.send_header(
                "Set-Cookie",
                f"ms_auth={self._ms_auth_val}; Path=/; Max-Age={_AUTH_MAX_AGE}; SameSite=Lax; HttpOnly" + ("; Secure" if _req_https(self) else ""),  # cookie-20261110
            )
            self._ms_auth_set = False
        for _hk, _hv in (getattr(self, "_ms_hdrs", None) or ()): self.send_header(_hk, _hv)  # login-20261110
        self._ms_hdrs = []
        self.send_header("Referrer-Policy", "no-referrer"); self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("X-Frame-Options", "SAMEORIGIN"); self.send_header("Cache-Control", getattr(self, "_cc", None) or "no-store")
        super().end_headers()
    def guard(self):
        # sec-20261110: decide network trust for THIS request first (thread-local; keep-alive safe)
        try: _REQ.trusted = bool(_trust_reason(self))
        except Exception: _REQ.trusted = False
        try: _REQ.user = _MSU.request_user(self)  # login-20261110: validate + slide the ms_sess session
        except Exception: _REQ.user = None
        try:
            path = urllib.parse.urlparse(self.path).path or "/"
        except Exception:
            path = "/"
        # Mint/bind ms_cid on any keyed request (incl. exempt /) so real players get a cookie
        # without sending X-MS-Client from player.html.
        if _request_has_valid_key(self):
            _ensure_client_id(self)
        # cookie-20261110: set the auth cookie only when a real key is presented (not LAN-trust alone).
        try:
            _pk = _presented_key(self)
            if _pk and _keyok(_pk):
                self._ms_auth_val = _auth_token(_pk)
                self._ms_auth_set = True
        except Exception:
            pass
        if path in ("/recover", "/api/auth/recover", "/api/auth/login") and (_rc_local(self) or (path == "/api/auth/login" and TRUST_LAN and _is_local_client(self))):
            return True  # recover-20261111: sign-in/recovery at home is never rate-limited
        if _rate_limit_exempt(path):
            return True
        ip_key, client_key = _limit_bucket_keys(self)
        if path == "/api/radio":
            # v69: radio refill gets its own per-client bucket (prewarm separate) so search/prefetch/lyrics bursts during
            # rapid skipping can't 429 the Next refill (root cause of the v68 "silent Next" stalls).
            client_key += ":radio:" + ("pre" if "phase=prewarm" in (self.path or "") else "q")
        method = (self.command or "GET").upper()
        n, win = _rate_limit_budget(path, method)
        # Global per-IP ceiling first (shared Wi‑Fi still protected from stampede/abuse).
        if limited("ipceil:" + ip_key, n=_RL_IP_CEIL_N, win=_RL_IP_CEIL_WIN):
            self.send(429, "slow down", "text/plain"); return False
        if limited(client_key, n=n, win=win):
            self.send(429, "slow down", "text/plain"); return False
        return True
    def log_message(self, *a): pass
    def send(self, code, body, ctype="text/html; charset=utf-8"):
        b = body.encode() if isinstance(body, str) else body
        if code == 200 and len(b) > 1024 and ctype.startswith(("text/html", "text/javascript", "application/json", "text/css")) and "gzip" in (self.headers.get("Accept-Encoding") or ""):
            import gzip as _gz, hashlib as _hl
            _GZ = globals().setdefault("_GZC", {}); ck = (len(b), _hl.sha1(b).digest())
            if ck not in _GZ:
                if len(_GZ) > 16: _GZ.clear()
                _GZ[ck] = _gz.compress(b, 6)
            z = _GZ[ck]; self.send_response(code); self.send_header("Content-Type", ctype); self.send_header("Content-Encoding", "gzip"); self.send_header("Vary", "Accept-Encoding")
            self.send_header("Content-Length", str(len(z))); self.end_headers(); self.wfile.write(z); return
        self.send_response(code); self.send_header("Content-Type", ctype); self.send_header("Content-Length", str(len(b))); self.end_headers(); self.wfile.write(b)
    def skin(self, path):
        """Serve skin pack assets (css/svg/woff2/json/png) — public, no auth."""
        if ".." in path or path.count("/") < 2: return self.send(404, "", "text/plain")
        f = (ROOT / path.lstrip("/")).resolve()
        try: f.relative_to((ROOT / "skins").resolve())
        except ValueError: return self.send(403, "", "text/plain")
        if not f.is_file(): return self.send(404, "", "text/plain")
        ext = f.suffix.lower()
        ctype = {".css":"text/css; charset=utf-8",".svg":"image/svg+xml",".json":"application/json",
                 ".woff2":"font/woff2",".woff":"font/woff",".png":"image/png",".txt":"text/plain; charset=utf-8"}.get(ext,"application/octet-stream")
        self._cc = "public, max-age=604800" if ext in (".woff2",".woff",".png",".svg") else "public, max-age=3600"
        return self.send(200, f.read_bytes(), ctype)

    def vendor(self, path):
        """v65: vendored MIT libs (butterchurn + presets) — public static, path-confined, gzip, long cache."""
        if ".." in path: return self.send(404, "", "text/plain")
        if _ms_adult_path(path):
            if not _ms_adult_allowed(self):
                return self.send(404, "", "text/plain")  # adult-viz-20261111
        f = (ROOT / path.lstrip("/")).resolve()
        try: f.relative_to((ROOT / path.lstrip("/").split("/")[0]).resolve())
        except ValueError: return self.send(403, "", "text/plain")
        if not f.is_file(): return self.send(404, "", "text/plain")
        ext = f.suffix.lower(); ctype = {".js": "text/javascript; charset=utf-8", ".mjs": "text/javascript; charset=utf-8", ".txt": "text/plain; charset=utf-8", ".json": "application/json", ".md": "text/plain; charset=utf-8", ".html": "text/html; charset=utf-8", ".png": "image/png", ".webp": "image/webp", ".svg": "image/svg+xml", ".jpg": "image/jpeg", ".gif": "image/gif", ".vrma": "model/gltf-binary", ".vrm": "model/gltf-binary", ".moc3": "application/octet-stream"}.get(ext, "application/octet-stream")
        if ext == ".png" and path.startswith("/assets/chars/") and "image/webp" in (self.headers.get("Accept") or "") and f.stat().st_size > 150000:
            try:
                import hashlib as _hl
                wd = ROOT / "cache" / "webp"; wd.mkdir(parents=True, exist_ok=True)
                wf = wd / (_hl.sha1(f"{f}|{f.stat().st_mtime}|{f.stat().st_size}".encode()).hexdigest() + ".webp")
                if not wf.exists():
                    from PIL import Image as _Im
                    _Im.open(f).save(str(wf) + ".tmp", "WEBP", quality=90, alpha_quality=100, method=4); Path(str(wf) + ".tmp").replace(wf)
                wb = wf.read_bytes(); self.send_response(200); self.send_header("Content-Type", "image/webp"); self.send_header("Vary", "Accept")
                self.send_header("Cache-Control", "public, max-age=86400"); self.send_header("Content-Length", str(len(wb))); self.end_headers(); self.wfile.write(wb); return
            except Exception: pass  # no Pillow / bad file -> original PNG below
        self._cc = "private, no-store" if _ms_adult_path(path) else ("public, max-age=2592000" if path.startswith(("/vendor/", "/assets/")) else "public, max-age=300")
        size = f.stat().st_size
        rg = re.match(r"bytes=(\d*)-(\d*)", self.headers.get("Range", "") or "")
        # gzip whole text assets only when the client did not ask for a byte range
        if (not rg) and ext in (".js", ".json", ".txt", ".svg", ".md", ".moc3") and "gzip" in (self.headers.get("Accept-Encoding") or ""):
            import gzip as _gz
            b = f.read_bytes()
            ck = (str(f), f.stat().st_mtime); _VZ = globals().setdefault("_VZ", {})
            if ck not in _VZ: _VZ[ck] = _gz.compress(b, 6)
            z = _VZ[ck]; self.send_response(200); self.send_header("Content-Type", ctype); self.send_header("Content-Encoding", "gzip"); self.send_header("Vary", "Accept-Encoding")
            self.send_header("Cache-Control", getattr(self, "_cc", "public, max-age=300")); self.send_header("Content-Length", str(len(z))); self.end_headers(); self.wfile.write(z); return
        a, b = 0, max(0, size - 1)
        if rg:
            if rg.group(1): a = int(rg.group(1))
            if rg.group(2): b = int(rg.group(2))
            if not rg.group(1) and rg.group(2):
                a, b = max(0, size - int(rg.group(2))), size - 1
            if size == 0 or a >= size:
                self.send_response(416); self.send_header("Content-Range", f"bytes */{size}"); self.send_header("Accept-Ranges", "bytes"); self.end_headers(); return
            b = min(b, size - 1)
        self.send_response(206 if rg else 200)
        self.send_header("Content-Type", ctype); self.send_header("Accept-Ranges", "bytes")
        self.send_header("Cache-Control", getattr(self, "_cc", "public, max-age=300"))
        self.send_header("Content-Length", str(b - a + 1 if size else 0))
        if rg: self.send_header("Content-Range", f"bytes {a}-{b}/{size}")
        self.end_headers()
        try:
            with f.open("rb") as fh:
                fh.seek(a)
                left = b - a + 1 if size else 0
                while left > 0:
                    chunk = fh.read(min(65536, left))
                    if not chunk: break
                    self.wfile.write(chunk); left -= len(chunk)
        except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError, OSError):
            pass
        return

    def vizdemo(self, path):
        """Serve isolated viz-demo/game assets — public static, path-confined."""
        if ".." in path: return self.send(404, "", "text/plain")
        rel = path.lstrip("/")
        if rel in ("viz-demo", "viz-demo/"):
            f = (ROOT / "viz-demo" / "index.html").resolve()
        else:
            f = (ROOT / rel).resolve()
        try: f.relative_to((ROOT / "viz-demo").resolve())
        except ValueError: return self.send(403, "", "text/plain")
        if f.is_dir():
            idx = f / "index.html"
            if idx.is_file(): f = idx
            else: return self.send(404, "", "text/plain")
        if not f.is_file(): return self.send(404, "", "text/plain")
        ext = f.suffix.lower()
        ctype = {".html":"text/html; charset=utf-8",".js":"text/javascript; charset=utf-8",".css":"text/css; charset=utf-8",
                 ".svg":"image/svg+xml",".json":"application/json",".png":"image/png",".wav":"audio/wav",".txt":"text/plain; charset=utf-8",
                 ".woff2":"font/woff2",".map":"application/json",".md":"text/plain; charset=utf-8",".cjs":"text/javascript; charset=utf-8",
                 ".ts":"text/plain; charset=utf-8"}.get(ext, "application/octet-stream")
        self._cc = "public, max-age=3600"
        return self.send(200, f.read_bytes(), ctype)

    def pwa(self, path, qs):
        if path == "/manifest.webmanifest":
            uu = re.sub(r"[^\w-]", "", qs.get("u", ""))[:24]; su = ("/?u=" + uu) if uu else "/"  # cookie-20261110: start_url without embedding k=
            m = {"name": "Music", "short_name": "Music", "start_url": su, "scope": "/", "display": "standalone", "background_color": "#17140f", "theme_color": "#17140f",
                 "description": "Ad-free music", "icons": [{"src": "/icon.svg", "sizes": "any", "type": "image/svg+xml", "purpose": "any"}, {"src": "/icon-192.png", "sizes": "192x192", "type": "image/png", "purpose": "any"}, {"src": "/icon-512.png", "sizes": "512x512", "type": "image/png", "purpose": "any maskable"}]}
            return self.send(200, json.dumps(m), "application/manifest+json")
        f = ROOT / ("icon-192.png" if path == "/favicon.ico" else path.lstrip("/"))
        if not f.exists(): return self.send(404, "", "text/plain")
        if path.endswith((".png", ".ico", ".svg")): self._cc = "public, max-age=604800"
        return self.send(200, f.read_bytes(), "text/javascript; charset=utf-8" if path.endswith(".js") else ("image/svg+xml" if path.endswith(".svg") else "image/png"))
    def do_POST(self):
        if not self.guard(): return
        u = urllib.parse.urlparse(self.path); qs = {k: v[0] for k, v in urllib.parse.parse_qs(u.query).items()}
        if u.path.startswith("/api/auth/") or u.path in ("/api/users", "/api/state"):  # login-20261110 / login-state-20261110
            return _MSU.handle_post(self, u.path, getattr(_REQ, "user", None), getattr(_REQ, "trusted", False))
        if not _req_authok(self): return _MSU.deny(self)  # login-20261110
        body = self.rfile.read(min(int(self.headers.get("Content-Length", 0)), 500000)).decode("utf-8", "replace")
        if u.path == "/api/played":
            try: j = json.loads(body) if body else {}
            except Exception: j = {}
            return self.send(200, json.dumps(record_play(j.get("id") or qs.get("id", ""), j.get("title") or qs.get("title") or "", j.get("channel") or qs.get("channel") or "", j.get("dur") if j.get("dur") is not None else qs.get("dur"), j.get("c") or "")), "application/json")

        if u.path == "/api/admin/update-ytdlp":
            if not _owner_authok(self): return self.send(403, "forbidden", "text/plain")  # cookie-20261110: key or owner cookie
            return self.send(200, json.dumps(ytdlp_update_nightly("manual")), "application/json")
        if u.path == "/api/import":
            try: return self.send(200, json.dumps(import_safe(body)), "application/json")
            except Exception as e: return self.send(500, json.dumps({"error": type(e).__name__}), "application/json")
        if u.path == "/api/translate":
            try:
                j = json.loads(body); tl = re.sub(r"[^a-zA-Z-]", "", j.get("tl", "en"))[:8] or "en"
                return self.send(200, json.dumps(translate([str(x)[:300] for x in j.get("lines", [])][:400], tl)), "application/json")
            except Exception: return self.send(200, "[]", "application/json")
        self.send(404, "no", "text/plain")
    def do_HEAD(self):
        """Lightweight HEAD for static/media probes (Range clients, offline checks)."""
        if not self.guard(): return
        u = urllib.parse.urlparse(self.path)
        # Reuse GET handlers that only need headers when possible; for media return Accept-Ranges.
        if u.path.startswith(("/vendor/", "/assets/", "/skins/")) or u.path in ("/THEMES.md", "/themes.md") or u.path.endswith((".js",".css",".svg",".json",".md",".vrm",".vrma")):
            # Delegate by temporarily swapping send to header-only
            _send = self.send
            def _head_send(code, body, ctype="text/html; charset=utf-8"):
                try:
                    raw = body if isinstance(body, (bytes, bytearray)) else str(body).encode("utf-8", "replace")
                except Exception:
                    raw = b""
                self.send_response(code)
                self.send_header("Content-Type", ctype)
                self.send_header("Content-Length", str(len(raw)))
                self.send_header("Accept-Ranges", "bytes")
                self.end_headers()
            self.send = _head_send
            try:
                return self.do_GET()
            finally:
                self.send = _send
        self.send_response(200); self.send_header("Accept-Ranges","bytes"); self.end_headers()

    def do_GET(self):
        if not self.guard(): return
        u = urllib.parse.urlparse(self.path); qs = {k: v[0] for k, v in urllib.parse.parse_qs(u.query).items()}
        if u.path == "/health":
                body = "ok"
                if qs.get("ytdlp") == "1":
                    body = json.dumps({"ok": _ytdlp_state.get("ok", True), "ver": _ytdlp_state.get("ver", ""), "heal": _ytdlp_state.get("heal", ""), "heal_ts": _ytdlp_state.get("heal_ts", 0)})
                    return self.send(200, body, "application/json")
                return self.send(200, "ok", "text/plain")
        if u.path in _AUTH_PATHS:  # login-20261110
            return _MSU.handle_get(self, u.path, qs, getattr(_REQ, "user", None), getattr(_REQ, "trusted", False))
        if u.path in ("/THEMES.md", "/themes.md"):
            f = ROOT / "THEMES.md"
            if f.is_file():
                return self.send(200, f.read_text(encoding="utf-8", errors="replace"), "text/plain; charset=utf-8")
            return self.send(404, "missing", "text/plain")
        if u.path == "/viz-demo" or u.path.startswith("/viz-demo/"): return self.vizdemo(u.path)
        if u.path.startswith("/skins/"): return self.skin(u.path)
        if u.path.startswith(("/vendor/", "/assets/")): return self.vendor(u.path)
        if u.path in PWA: return self.pwa(u.path, qs)
        if u.path == "/api/admin/ytdlp":
            if not _req_authok(self): return _MSU.deny(self)  # login-20261110
            return self.send(200, json.dumps(ytdlp_status()), "application/json")
        if not _req_authok(self): return _MSU.deny(self)  # login-20261110
        k = qs.get("k", "") if _keyok(qs.get("k", "")) else ""  # sec-20261110: never embed KEY for keyless/trusted clients
        try:
            if u.path == "/api/vinfo":
                vid = resolve(qs.get("id", "") or "")
                if not vid: return self.send(404, "{}", "application/json")
                vc = "a" if qs.get("c") == "av1" else "h"
                x = _VINFO.get((vid, vc))
                if not x:
                    threading.Thread(target=lambda: _quiet_call(_vwarm, vid, vc), daemon=True).start()  # perf2-20261112
                    return self.send(200, json.dumps({"id": vid, "c": vc, "res": {}, "pending": 1}), "application/json")
                try: return self.send(200, json.dumps({"id": vid, "c": vc, "res": x["res"]}), "application/json")
                except Exception as e: return self.send(200, json.dumps({"id": vid, "c": vc, "res": {}, "err": str(e)[:120]}), "application/json")
            if u.path == "/api/dl/start": return self.send(200, json.dumps(dl_start(qs)), "application/json")
            if u.path == "/api/dl/status": return self.send(200, json.dumps(dl_public(qs.get("job", ""))), "application/json")
            if u.path == "/dlfile": return self._dlfile(qs.get("job", ""))
            if u.path == "/api/ytdlp": return self.send(200, json.dumps({"ok": _ytdlp_state.get("ok", True), "ver": _ytdlp_state.get("ver", ""), "heal": _ytdlp_state.get("heal", ""), "heal_ts": int(_ytdlp_state.get("heal_ts") or 0), "ads": "never — bestaudio pipe; breakage = extractor"}), "application/json")
            if u.path == "/api/suggest": return self.send(200, json.dumps(suggest(qs.get("q", ""))), "application/json")
            if u.path == "/art":
                vid = qs.get("id", "")
                if not VID.match(vid): return self.send(400, "", "text/plain")
                sz = {"m": "mqdefault", "hi": "maxresdefault"}.get(qs.get("s"), "hqdefault"); b = _art.get((vid, sz))
                if b is None:
                    # v63: s=hi -> 1280x720 maxres (no letterbox bars); fall back to hqdefault when missing
                    for cand in ([sz, "hqdefault"] if sz == "maxresdefault" else [sz]):
                        try:
                            b = urllib.request.urlopen(f"https://i.ytimg.com/vi/{vid}/{cand}.jpg", timeout=6 if cand == "maxresdefault" else 10).read()
                            if cand == "maxresdefault" and len(b) < 2500: b = None; continue  # grey placeholder
                            break
                        except Exception: b = None
                    if b is None: return self.send(404, "", "text/plain")
                    if len(_art) > 200: _art.pop(next(iter(_art)))
                    _art[(vid, sz)] = b
                self._cc = "private, max-age=604800, immutable"
                return self.send(200, b, "image/jpeg")
            if u.path == "/api/list":
                lid = qs.get("id", "")
                if not re.match(r"^[A-Za-z0-9_-]{10,64}$", lid): return self.send(400, "[]", "application/json")
                return self.send(200, json.dumps(ytlist(lid)), "application/json")
            if u.path == "/api/radio":
                vid = qs.get("id", ""); ex = [x for x in qs.get("ex", "").split(",") if VID.match(x)][:400]
                _CH.ids = [x for x in qs.get("ch", "").split(",") if VID.match(x)][:6] or [x for x in reversed(ex) if x != vid][:3]
                exf = [tuple((y.split("\t") + [""])[:2]) for y in qs.get("exf", "")[:12000].split("\n") if y.strip()][:120]
                phase = (qs.get("phase") or ("fast" if qs.get("fast") == "1" else "full")).lower()
                if phase == "prewarm":
                    return self.send(200, json.dumps(radio_prewarm(vid)), "application/json")
                if phase == "fast":
                    return self._radio_out(radio_fast(vid, ex, exf, qs.get("mix", "")[:12], qs.get("ta", "")[:600].split("|"), qs.get("sk", "")[:1500].split("|"), qs.get("lk", "")[:1500].split("|"), [x for x in qs.get("lk_ids", "").split(",") if VID.match(x)][:80], qs.get("sch", "")[:120]))
                return self._radio_out(radio(vid, ex, qs.get("ta", "")[:600].split("|"), qs.get("sk", "")[:1500].split("|"), qs.get("lk", "")[:1500].split("|"), qs.get("lang", "")[:60], qs.get("mix", "")[:12], [x for x in qs.get("lk_ids", "").split(",") if VID.match(x)][:80], qs.get("sch", "")[:120], exf))
            if u.path == "/api/chips": return self.send(200, json.dumps(chips(qs.get("a", "").split("|")[:3])), "application/json")
            if u.path == "/api/import": return self.send(200, json.dumps(import_safe(qs.get("t", ""))), "application/json")
            if u.path == "/api/lyrics":
                # v64: hard ~4 s cap per request; lookup keeps running in background and lands in the disk cache for next time
                _la = (qs.get("t", "")[:200], qs.get("a", "")[:100], int(float(qs.get("d", "0") or 0))) + ((qs.get("l"),) if qs.get("l") in _LYN else ()); _lb = {}  # lyrics2-20261111: optional language
                _LYF = globals().setdefault("_LYF", {}); _lf = _LYF.get(_la)
                if _lf is None or not _lf[0].is_alive():
                    _lt = threading.Thread(target=lambda: (_lb.update(r=(lyrics_l if len(_la) > 3 else lyrics)(*_la)), _LYF.pop(_la, None)), daemon=True); _LYF[_la] = (_lt, _lb); _lt.start()
                else: _lt, _lb = _lf  # singleflight: join the lookup already running for this song
                _lt.join(4.0)
                if "r" not in _lb: return self.send(200, json.dumps({"timeout": 1}), "application/json")
                try: return self.send(200, json.dumps(_lb["r"] or {}), "application/json")
                except Exception: return self.send(200, "{}", "application/json")
            if u.path == "/api/playable":  # ms-v77: is this id a live/upcoming stream? (metadata only, cached)
                vid = qs.get("id", "")
                if not VID.match(vid): return self.send(400, json.dumps({"ok": False, "err": "bad id"}), "application/json")
                st = live_check(vid)
                return self.send(200, json.dumps({"id": vid, "live_status": st or "unknown", "live": st in _LIVE_BAD}), "application/json")
            if u.path == "/api/busy":  # perf2-20261112
                v = qs.get("id", ""); return self.send(200, json.dumps({"busy": bool(v) and time.time() - _BUSYV.get(v, 0) < 15, "retry": 2}), "application/json")
            if u.path == "/api/warm":
                # URL-resolve only (no media download). ids=comma list, max 8; q= format key.
                ids = [x for x in (qs.get("ids") or qs.get("id") or "").split(",") if VID.match(x)][:8]
                fq = ("v" + qs.get("r", "360")) if qs.get("v") else qs.get("q", "std")
                if not ids: return self.send(200, json.dumps({"ok": False, "err": "no ids"}), "application/json")
                n = _warm_enqueue(ids, fq, front=True)
                return self.send(200, json.dumps({"ok": True, "queued": n}), "application/json")
            if u.path == "/api/prefetch":
                vid = qs.get("id", ""); fq = ("v" + qs.get("r", "360")) if qs.get("v") else qs.get("q", "std")
                if VID.match(vid) and ((vid, fq) in _blobs or active_dls() + _pend[0] < MAX_ACTIVE):
                    def _pf(vid=vid, fq=fq):
                        try:
                            _fg_wait(15)  # speed-20261110
                            bl = get_blob(vid, fq)
                            # pull ~3MB into disk cache so Next/autoplay starts in ~1s
                            try: bl.read(0, min(bl.size - 1, (3 << 20) - 1))
                            except Exception: pass
                        finally: _pend[0] -= 1
                    _pend[0] += 1; threading.Thread(target=_pf, daemon=True).start()
                else: return self.send(200, '{"skipped":"busy"}', "application/json")
                return self.send(200, "{}", "application/json")
            if u.path == "/api/segments":
                vid = qs.get("id", "")
                if not VID.match(vid): return self.send(400, "[]", "application/json")
                fl = qs.get("filler") == "1"
                _SBA = ["sponsor","intro","outro","selfpromo","interaction","music_offtopic","preview","filler"]
                _uc = [c for c in (qs.get("cats") or "").split(",") if c in _SBA]
                C = (_uc or ["sponsor","intro","outro","selfpromo","interaction","music_offtopic","preview"]); C = [c for c in C if c != "filler"] + (["filler"] if fl else [])
                if not C: return self.send(200, "[]", "application/json")
                _ck = hashlib.sha1(",".join(sorted(C)).encode()).hexdigest()[:8]
                sbd = ROOT.resolve() / "cache" / "sb"; cf = sbd / f"{vid}_{int(fl)}_{_ck}.json"
                # disk cache ~1h; miss/failure never breaks playback (always 200 + JSON list)
                if cf.exists() and time.time() - cf.stat().st_mtime < 3600:
                    try: return self.send(200, cf.read_text(), "application/json")
                    except Exception: pass
                data, ok = [], False
                try:
                    r = urllib.request.urlopen(urllib.request.Request(
                        "https://sponsor.ajay.app/api/skipSegments?" + urllib.parse.urlencode({"videoID": vid, "categories": json.dumps(C)}),
                        headers={"User-Agent": "music-stream"}), timeout=4)
                    raw = json.load(r)
                    data = []
                    for x in (raw or []):
                        try:
                            seg = x.get("segment") or []
                            if len(seg) < 2: continue
                            s, e = float(seg[0]), float(seg[1])
                            if e > s and x.get("actionType", "skip") == "skip": data.append({"s": s, "e": e, "c": x.get("category") or "segment", "vd": float(x.get("videoDuration") or 0)})
                        except (TypeError, ValueError, AttributeError): continue
                    ok = True
                except urllib.error.HTTPError as e:
                    data, ok = [], (e.code == 404)  # 404 = no segments (cache empty)
                except Exception:
                    data, ok = [], False  # timeout/DNS/etc — do not cache; client keeps playing
                if ok:
                    try: sbd.mkdir(parents=True, exist_ok=True); cf.write_text(json.dumps(data))
                    except Exception: pass
                return self.send(200, json.dumps(data), "application/json")
            _noff_dl = False
            if u.path == "/stream" and (self.headers.get("Range") or not HAVE_FFMPEG):  # seekable fallback: serve the ranged m4a blob instead of a non-seekable mp3 pipe
                u = u._replace(path="/audio"); qs["q"] = "std"                      # ms-v75: also the no-ffmpeg path (direct m4a/AAC, no transcode)
            elif u.path == "/dl" and not HAVE_FFMPEG:  # ms-v75: no ffmpeg -> download the original m4a/AAC (or webm) instead of an mp3
                u = u._replace(path="/audio"); qs["q"] = "std"; _noff_dl = True
            if u.path in ("/audio", "/video"):
                vid = resolve(qs.get("id", ""))
                if not vid: return self.send(404, "not found", "text/plain")
                fq = ("v" + qs.get("r", "360")) if u.path == "/video" else qs.get("q", "std")
                if u.path == "/video":
                    vc = "a" if qs.get("c") == "av1" else "h"; fq += vc
                    try:
                        with _fg(vid): _vwarm(vid, vc, need=_q_video_h(fq) or 720)  # play4-20261111
                    except LiveUnsupported as e: return self._live409(vid, e.status)
                    except ExtractBusy: return self._busy503(vid)  # perf-20261112
                    except Exception: pass  # fall back to the per-rendition extraction below
                bl = None
                for _try in range(3):
                    try:
                        with _fg(vid): bl = get_blob(vid, fq)  # speed-20261110 play4-20261111
                        break
                    except LiveUnsupported as e:
                        return self._live409(vid, e.status)
                    except ExtractBusy: return self._busy503(vid)  # perf-20261112
                    except Exception:
                        if _try == 2: return self.send(502, "upstream error", "text/plain")
                        time.sleep(0.4 * (_try + 1))
                rg = re.match(r"bytes=(\d*)-(\d*)", self.headers.get("Range", "") or "")
                a = int(rg.group(1)) if rg and rg.group(1) else 0
                b = int(rg.group(2)) if rg and rg.group(2) else bl.size - 1
                if rg and not rg.group(1) and rg.group(2): a, b = max(0, bl.size - int(rg.group(2))), bl.size - 1
                if a >= bl.size: self.send_response(416); self.send_header("Content-Range", f"bytes */{bl.size}"); self.end_headers(); return
                b = min(b, bl.size - 1)
                self.send_response(206 if rg else 200); self.send_header("Content-Type", bl.ctype); self.send_header("Accept-Ranges", "bytes")
                self.send_header("Content-Length", str(b - a + 1))
                if rg: self.send_header("Content-Range", f"bytes {a}-{b}/{bl.size}")
                if _noff_dl:
                    ext = "m4a" if "mp4" in (bl.ctype or "") else ("webm" if "webm" in (bl.ctype or "") else "audio")
                    self.send_header("Content-Disposition", f'attachment; filename="{re.sub(r"[^A-Za-z0-9_-]", "_", vid)[:40]}.{ext}"')
                self.end_headers()
                try:
                    p = a
                    while p <= b:
                        d = bl.read(p, b); self.wfile.write(d); p += len(d)
                except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError, IOError): pass
                return
            if u.path == "/api/search": return self.send(200, json.dumps(search(qs.get("q", ""), int(qs.get("n", "15")))), "application/json")
            if u.path == "/" and not qs.get("q"): return self.send(200, _MSU.with_boot(_page(), getattr(_REQ, "user", None)))  # login-state-20261110
            if u.path == "/":
                q = qs.get("q", ""); rows = ""
                if q:
                    for r in search(q):
                        i = r["id"]; rows += (f'<li>{html.escape(r["title"])}<br><a href="#" onclick="a.src=\'/stream?k={k}&id={i}\';return false">play here</a> | '
                                              f'<a href="/dl?k={k}&id={i}">download mp3</a></li>')
                return self.send(200, PAGE % {"k": k, "q": html.escape(q), "rows": rows, "st": status(), "src": ""})
            if u.path in ("/stream", "/dl"):
                vid = resolve(qs.get("id") or qs.get("q", ""))
                if not vid: return self.send(404, "not found", "text/plain")
                if live_known(vid): return self._live409(vid, live_known(vid))
                if not _FF.acquire(timeout=8): return self.send(503, "busy: too many downloads, retry shortly", "text/plain")
                try: return self._ffstream(u, vid)
                finally: _FF.release()
            if u.path in ("/pc/play", "/pc/stop"): local_stop(); return self.send(410, "PC speaker playback is disabled", "text/plain")
            if u.path == "/cmd" and not (_keyok(qs.get("k", "")) or _auth_cookie_ok(self)): return self.send(403, "forbidden", "text/plain")  # sec-20261110
            if u.path == "/cmd": return self.send(200, music_cmd(qs.get("c", ""), qs.get("a", "").strip()), "text/plain; charset=utf-8")
            if u.path == "/status": return self.send(200, status(), "text/plain")
            if u.path == "/api/stats":
                _cl = {}
                try:
                    import ms_cluster as _msc
                    _cl = json.loads((_msc.CLUSTER_JSON).read_text(encoding="utf-8")) if _msc.CLUSTER_JSON.exists() else {}
                except Exception:
                    _cl = {}
                return self.send(200, json.dumps({"active_dl": active_dls(), "blobs": len(_blobs), "max_fetch": MAX_FETCH, "max_active": MAX_ACTIVE, "xt": _XG.info(), "ucache": len(_ucache), "lookup_helper": {k: v for k, v in _LK.items() if k not in ("key", "url")} | {"on": bool(_LK["url"]), "up": bool(_LK["url"]) and time.time() >= _LK["down_until"]}, "quiet_warm": dict(_QW), "rooms": len(ROOMS),
                    "worker": os.environ.get("MUSIC_WORKER_ID"), "workers": _cl.get("n") or 1, "worker_ports": _cl.get("ports") or []}), "application/json")
            if u.path == "/api/home":
                return self.send(200, json.dumps(home_feed(qs.get("langs", "")[:40], qs.get("lk_ids", "")[:900], qs.get("seed", "")[:20], qs.get("hist", "")[:900])), "application/json")
            if u.path == "/api/played":
                # GET also accepted for beacons
                return self.send(200, json.dumps(record_play(qs.get("id", ""), qs.get("title", "")[:200], qs.get("channel", "")[:120], qs.get("dur"), qs.get("c", "")[:40])), "application/json")
            if u.path == "/api/karaoke":
                return self.send(200, json.dumps(karaoke(qs.get("t", "")[:200], qs.get("a", "")[:100])), "application/json")
            if u.path == "/api/similar":
                try: return self.send(200, json.dumps(similar(qs.get("t", "")[:200], qs.get("a", "")[:100])), "application/json")
                except Exception: return self.send(200, "[]", "application/json")
            if u.path == "/api/room": return self.send(200, json.dumps(room(qs)), "application/json")
        except Exception as e:
            return self.send(500, "error: " + type(e).__name__, "text/plain")
        self.send(404, "no", "text/plain")
    def _radio_out(self, res):  # perf-20261112: send the list, then warm the next 2 songs' stream URLs in the background
        r = self.send(200, json.dumps(res), "application/json")
        try:
            items = res if isinstance(res, list) else next((v for v in (res or {}).values() if isinstance(v, list) and v and isinstance(v[0], dict) and v[0].get("id")), [])
            ids = [x["id"] for x in items if isinstance(x, dict) and VID.match(str(x.get("id") or ""))][:2]
            if ids: _warm_enqueue(ids, "std")
        except Exception: pass
        return r
    def _busy503(self, vid=""):  # perf-20261112: too many lookups at once -> quick, retryable answer instead of a 20 s hang
        if vid: _BUSYV[vid] = time.time()  # perf2-20261112: /api/busy tells the player why its media request failed
        self.send_response(503); self.send_header("Retry-After", "2"); self.send_header("Content-Type", "application/json")
        self.send_header("Cache-Control", "no-store"); b = json.dumps({"busy": True, "retry": 2, "msg": "busy, retrying"}).encode()
        self.send_header("Content-Length", str(len(b))); self.end_headers()
        try: self.wfile.write(b)
        except Exception: pass
    def _live409(self, vid, st):
        self.send_response(409); self.send_header("Content-Type", "application/json"); self.send_header("X-MS-Unsupported", "live")
        b = json.dumps({"error": "live_unsupported", "id": vid, "live_status": st,
                        "msg": "Live and upcoming streams are not supported (no finite audio file). Recordings of past streams play normally."}).encode()
        self.send_header("Content-Length", str(len(b))); self.end_headers()
        try: self.wfile.write(b)
        except Exception: pass
    def _dlfile(self, j):
        x = DLJOBS.get(j)
        if not x or x.get("state") != "done" or not Path(x.get("file", "")).exists(): return self.send(404, "not ready", "text/plain")
        f = Path(x["file"]); size = f.stat().st_size; name = x.get("name") or f.name
        asc = re.sub(r'[^A-Za-z0-9 ._()\-]', '_', name) or f.name
        rg = re.match(r"bytes=(\d*)-(\d*)", self.headers.get("Range", "") or "")
        a, b = 0, size - 1
        if rg:
            if rg.group(1): a = int(rg.group(1))
            if rg.group(2): b = min(size - 1, int(rg.group(2)))
            if a >= size: self.send_response(416); self.send_header("Content-Range", f"bytes */{size}"); self.end_headers(); return
        self.send_response(206 if rg else 200); self.send_header("Content-Type", x.get("ctype") or "application/octet-stream"); self.send_header("Accept-Ranges", "bytes")
        self.send_header("Content-Length", str(b - a + 1)); self.send_header("Content-Disposition", f"attachment; filename=\"{asc}\"; filename*=UTF-8''{urllib.parse.quote(name)}")
        if rg: self.send_header("Content-Range", f"bytes {a}-{b}/{size}")
        self.end_headers()
        try:
            with f.open("rb") as fh:
                fh.seek(a); left = b - a + 1
                while left > 0:
                    c = fh.read(min(65536, left))
                    if not c: break
                    self.wfile.write(c); left -= len(c)
        except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError, OSError): pass
    def _ffstream(self, u, vid):
                if not HAVE_FFMPEG:  # ms-v75: honest 501 instead of a 200 with an empty body when ffmpeg is absent
                    return self.send(501, json.dumps({"error": "ffmpeg not installed on this server: mp3 transcode (/stream, /dl) unavailable; direct /audio playback still works"}), "application/json")
                # Respond with headers immediately so Range/HEAD clients and UAT don't hang on yt-dlp/title resolve.
                self.send_response(200); self.send_header("Content-Type", "audio/mpeg")
                if u.path == "/dl":
                    _q = urllib.parse.parse_qs(u.query); _t = (_q.get("t") or [""])[0]
                    fn = (re.sub(r'[^\w\- .()]', '_', _dl_name(_t, (_q.get("ar") or [""])[0]))[:100] if _t else re.sub(r'[^\w\- .]', '_', (vid or "track"))[:80]) + ".mp3"
                    self.send_header("Content-Disposition", f'attachment; filename="{fn}"')
                self.send_header("X-Accel-Buffering", "no")
                self.end_headers()
                try:
                    src = audio_url(vid)
                except Exception as e:
                    print(f"dl audio_url fail {vid}: {type(e).__name__}", flush=True)
                    return
                if not src:
                    print(f"dl empty url {vid}", flush=True); return
                p = subprocess.Popen([FFMPEG, "-loglevel", "quiet", "-i", src, "-vn", "-c:a", "libmp3lame", "-b:a", "192k", "-f", "mp3", "-"],
                                     stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, creationflags=NOFLAGS)
                try:
                    # Hard wall clock so a stuck upstream can't pin a worker forever
                    deadline = time.time() + 1200   # dancefix: was 90 s, which truncated songs on ~50-70 KB/s Wi-Fi
                    while time.time() < deadline:
                        c = p.stdout.read(16384)
                        if not c: break
                        self.wfile.write(c)
                except (BrokenPipeError, ConnectionResetError): pass
                finally:
                    try: p.kill()
                    except Exception: pass
                return
# ---- Telegram (only if a DEDICATED MUSIC_BOT_TOKEN is set; never polls the V10 bot token) ----
def tg_loop(tok, allowed):
    api = f"https://api.telegram.org/bot{tok}/"; off = 0
    def send(chat, text):
        urllib.request.urlopen(api + "sendMessage", urllib.parse.urlencode({"chat_id": chat, "text": text}).encode(), timeout=30)
    while True:
        try:
            r = json.load(urllib.request.urlopen(api + f"getUpdates?timeout=50&offset={off}", timeout=60))
            for upd in r.get("result", []):
                off = upd["update_id"] + 1; m = upd.get("message") or {}; chat = str(m.get("chat", {}).get("id", "")); t = (m.get("text") or "").strip()
                if allowed and chat not in allowed: continue
                cmd, _, arg = t.partition(" "); cmd = cmd.split("@")[0].lower(); base = public_url()
                try:
                    if cmd in ("/play", "/music_on"): send(chat, local_play(arg) if arg else "usage: /play <song or url>")
                    elif cmd in ("/stop", "/music_off"): local_stop(); send(chat, "stopped")
                    elif cmd in ("/status", "/music_status"): send(chat, status())
                    elif cmd in ("/link", "/music_link"): send(chat, f"{base}/?k={KEY}")
                    elif cmd == "/search":
                        rs = search(arg, 5); send(chat, "\n\n".join(f"{x['title']}\n/play {x['id']}\nstream: {base}/stream?k={KEY}&id={x['id']}\ndownload: {base}/dl?k={KEY}&id={x['id']}" for x in rs) or "nothing")
                    elif cmd in ("/dl", "/stream"):
                        v = resolve(arg); send(chat, f"{base}{cmd}?k={KEY}&id={v}" if v else "not found")
                    else: send(chat, "/search q | /play q | /stop | /status | /link | /dl q | /stream q")
                except Exception as e: send(chat, f"error: {e}")
        except Exception: time.sleep(5)
if __name__ == "__main__":
    # ms-v75: background yt-dlp jobs start only when the server runs, never on `import music_server` (tests/tools).
    # ensure_ytdlp honours YTDLP_AUTO_UPDATE; the hourly smoke watch still runs (read-only unless auto-update is on).
    # cluster-20261113: workers 1..n-1 skip background jobs; worker 0 (or a single process) keeps them.
    import ms_cluster
    ms_cluster.watch_parent()
    _bg = os.environ.get("MUSIC_WORKER_BG", "1") != "0"
    if _bg:
        ensure_ytdlp(background=True)
        ytdlp_watch()
        ytdlp_daily()
        tok = cfg.get("MUSIC_BOT_TOKEN")
        if tok: threading.Thread(target=tg_loop, args=(tok, set(filter(None, cfg.get("MUSIC_ALLOWED_CHATS", "").split(","))),), daemon=True).start()
    class _Srv(ThreadingHTTPServer):  # perf2-20261112: no traceback spam for expected "busy" / client hang-ups
        # backlog-20261112: Python's default listen queue is 5; a login storm / burst of 100 new tunnel connections
        # overflowed it and cloudflared answered 502. MUSIC_BACKLOG (env or music.env), default 128.
        request_queue_size = max(16, int(__import__("os").environ.get("MUSIC_BACKLOG") or cfg.get("MUSIC_BACKLOG", "128") or 128))
        def handle_error(self, request, client_address):
            e = _sys.exc_info()[1]
            if isinstance(e, (ExtractBusy, BrokenPipeError, ConnectionResetError, ConnectionAbortedError)): return
            return super().handle_error(request, client_address)
    _bind = os.environ.get("MUSIC_BIND") or cfg.get("MUSIC_BIND", "0.0.0.0")
    _Srv((_bind, PORT), H).serve_forever()



