"""Music Stream - optional LAN lookup helper (perf2-20261112).

Runs YouTube lookups (yt-dlp extract_info) for a Music Stream server on a weaker device (e.g. a phone) using several CPU
cores of a stronger PC on the same home network. The music server asks this helper first and falls back to its own
lookups when the helper is off, slow or unreachable. Off by default: nothing uses it unless the server has a lookup.env.

Config: lookup.env next to this file (KEY=VALUE lines):
  LOOKUP_KEY=<long random secret, same value as the server's lookup.env>   (required)
  LOOKUP_BIND=192.168.x.y   (this PC's LAN address; never 0.0.0.0 on an untrusted network)
  LOOKUP_PORT=8131
  LOOKUP_PROCS=4            (worker processes = parallel lookups)
  LOOKUP_ALLOW=192.168.,127.   (client address prefixes allowed, comma list)
  LOOKUP_JS_RUNTIME=node    (yt-dlp JS runtime on this PC; "none" to disable)
Run: python ms_lookup_service.py        Health: GET /health (no secret, says only "ok")."""
import gzip, hmac, json, os, sys, threading, time
from concurrent.futures import ProcessPoolExecutor, TimeoutError as FutTimeout
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
from pathlib import Path

HERE = Path(__file__).resolve().parent
def _cfg():
    c = {}
    f = HERE / "lookup.env"
    if f.exists():
        for ln in f.read_text(encoding="utf-8").splitlines():
            ln = ln.strip()
            if ln and not ln.startswith("#") and "=" in ln:
                k, v = ln.split("=", 1); c[k.strip()] = v.strip()
    return c
CFG = _cfg()
KEY = CFG.get("LOOKUP_KEY", ""); BIND = CFG.get("LOOKUP_BIND", "127.0.0.1"); PORT = int(CFG.get("LOOKUP_PORT", "8131"))
PROCS = max(1, int(CFG.get("LOOKUP_PROCS", "4"))); ALLOW = tuple(x.strip() for x in CFG.get("LOOKUP_ALLOW", "192.168.,127.").split(",") if x.strip())
JSRT = CFG.get("LOOKUP_JS_RUNTIME", "node").strip() or "node"
FMT_KEYS = ("format_id", "url", "ext", "protocol", "vcodec", "acodec", "height", "width", "fps", "tbr", "vbr", "abr", "asr",
            "filesize", "filesize_approx", "http_headers", "format_note", "container", "audio_channels", "dynamic_range", "language")
DROP = ("automatic_captions", "subtitles", "thumbnails", "heatmap", "requested_subtitles", "_format_sort_fields", "chapters")

# ---- worker process side -----------------------------------------------------------------------------------------
_W = {}
def _winit():
    import yt_dlp  # noqa: F401  (import once per worker)
    try:
        from yt_dlp.extractor.youtube.jsc._builtin import ejs as _ejs
        if hasattr(_ejs.EJSBaseJCP, "_ENABLE_PREPROCESSED_PLAYER_CACHE"): _ejs.EJSBaseJCP._ENABLE_PREPROCESSED_PLAYER_CACHE = True
    except Exception: pass
def _slim_fmt(f): return {k: f[k] for k in FMT_KEYS if k in f and f[k] is not None}
def _extract(url, opts):
    import yt_dlp
    opts = dict(opts or {}); opts.update(quiet=True, no_warnings=True, skip_download=True, noplaylist=True)
    opts.pop("js_runtimes", None)
    if JSRT.lower() != "none": opts["js_runtimes"] = {JSRT: {}}
    opts["source_address"] = "0.0.0.0"  # IPv4: stream URLs are bound to the address that asked; the home IPv4 is shared by the LAN
    k = json.dumps(opts, sort_keys=True); ent = _W.get(k)
    if ent is None or ent[1] >= 150:
        if ent:
            try: ent[0].close()
            except Exception: pass
        ent = _W[k] = [yt_dlp.YoutubeDL(opts), 0]
    ent[1] += 1
    try:
        info = ent[0].sanitize_info(ent[0].extract_info(url, download=False))
    except Exception as e:
        _W.pop(k, None)
        return {"err": str(e)[:2000], "etype": type(e).__name__}
    for d in DROP: info.pop(d, None)
    if isinstance(info.get("description"), str): info["description"] = info["description"][:3000]
    info["formats"] = [_slim_fmt(f) for f in (info.get("formats") or []) if f.get("protocol") in ("https", "http")]
    if info.get("requested_formats"): info["requested_formats"] = [_slim_fmt(f) for f in info["requested_formats"]]
    return {"info": info}

# ---- HTTP side ---------------------------------------------------------------------------------------------------
POOL = None; STAT = {"ok": 0, "err": 0, "busy": 0, "t0": time.time()}; _ACT = threading.BoundedSemaphore(PROCS * 2)
class H(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"; server_version = "ms-lookup"
    def log_message(self, *a): pass
    def _send(self, code, obj, gz=False):
        b = json.dumps(obj).encode()
        if gz and len(b) > 1024: b = gzip.compress(b, 4); enc = True
        else: enc = False
        self.send_response(code); self.send_header("Content-Type", "application/json"); self.send_header("Content-Length", str(len(b)))
        if enc: self.send_header("Content-Encoding", "gzip")
        self.end_headers(); self.wfile.write(b)
    def _allowed(self): return self.client_address[0].startswith(ALLOW)
    def do_GET(self):
        if not self._allowed(): return self._send(403, {"error": "forbidden"})
        if self.path == "/health": return self._send(200, {"ok": True, "procs": PROCS})
        if self.path == "/stats" and hmac.compare_digest(self.headers.get("X-MS-Lookup-Key", ""), KEY): return self._send(200, {**STAT, "up": int(time.time() - STAT["t0"])})
        return self._send(404, {"error": "not found"})
    def do_POST(self):
        if not self._allowed() or not KEY or not hmac.compare_digest(self.headers.get("X-MS-Lookup-Key", ""), KEY): return self._send(403, {"error": "forbidden"})
        try:
            n = min(int(self.headers.get("Content-Length", "0") or 0), 65536); rq = json.loads(self.rfile.read(n) or b"{}")
            url = str(rq.get("url") or "")
            if not url.startswith(("https://www.youtube.com/watch?v=", "https://music.youtube.com/watch?v=")): return self._send(400, {"error": "bad url"})
        except Exception: return self._send(400, {"error": "bad request"})
        if not _ACT.acquire(timeout=10): STAT["busy"] += 1; return self._send(503, {"error": "busy"})
        try:
            r = POOL.submit(_extract, url, rq.get("opts") or {}).result(timeout=60)
        except FutTimeout: STAT["err"] += 1; return self._send(504, {"error": "timeout"})
        except Exception as e: STAT["err"] += 1; return self._send(500, {"error": type(e).__name__})
        finally: _ACT.release()
        if "err" in r: STAT["err"] += 1; return self._send(422, r)
        STAT["ok"] += 1; return self._send(200, r, gz="gzip" in (self.headers.get("Accept-Encoding") or ""))

def main():
    global POOL
    if not KEY or len(KEY) < 24: sys.exit("lookup.env: LOOKUP_KEY missing or too short")
    POOL = ProcessPoolExecutor(max_workers=PROCS, initializer=_winit)
    for f in [POOL.submit(_winit) for _ in range(PROCS)]: f.result(timeout=120)  # start + import yt-dlp in every worker now
    srv = ThreadingHTTPServer((BIND, PORT), H); srv.daemon_threads = True
    print(f"ms-lookup on {BIND}:{PORT} procs={PROCS}", flush=True)
    srv.serve_forever()
if __name__ == "__main__":
    main()
