# users2-20261111 applied
# adult-viz-20261111 applied

"""login-20261110: username/password accounts + server-side sessions for Music Stream.

Files (next to music_server.py, owner-only permissions where the OS allows):
  users.json     {"version":1,"users":{name:{"role","hash","pwv","created","last_login"}}}
  sessions.json  {"version":1,"sessions":{sha256(token):{"u","exp","keep","ren","pwv","ct"}}}
Passwords: PBKDF2-HMAC-SHA256, 310k iterations, 16-byte per-user salt, constant-time compare.
Cookies: ms_sess (random 256-bit token; only its SHA-256 is stored), HttpOnly, SameSite=Lax, Secure over HTTPS.
Nothing here ever logs or returns a password, a hash or a session token."""
import base64, hashlib, json, os, re, secrets, subprocess, threading, time, urllib.parse
from pathlib import Path

MARK = "login-20261110"
USER_RE = re.compile(r"^[a-z0-9][a-z0-9._-]{1,31}$")
PW_MIN, PW_MAX = 8, 256
PBKDF2_ITERS = 310000
COOKIE = "ms_sess"
KEEP_TTL, SHORT_TTL = 365 * 86400, 12 * 3600      # kept-signed-in (1 year) / browser-session (12 h idle)
RENEW_KEEP, RENEW_SHORT = 86400, 600               # sliding renewal granularity
FAIL_MAX, FAIL_WIN = 10, 900                       # 10 failures / 15 min per IP and per username
FAIL_IP_MAX, FAIL_USER_MAX = 30, 30  # lock64-20261111: was 30, 100                # users3-20261111: non-LAN only
MAX_SESS_PER_USER = 50
_TOK_RE = re.compile(r"^[A-Za-z0-9_-]{32,64}$")
# login-state-20261110: per-user state that follows a user to every device (player localStorage keys + now playing)
SYNC_KEYS = ("q", "lk", "lpl", "off", "h", "pc", "sk", "dlJobs", "rseed", "mood", "lang", "mixRule", "theme", "skin", "skinSolid",
             "npLayout", "art", "sbCats", "sbFiller", "sb", "rad", "rmode", "xf", "norm", "vol", "qual", "vresPick", "vcodec",
             "lytl", "lyf", "lyLead", "lyMan", "ly", "viz", "ms.viz", "vizMode65", "vizPreset", "vizFavs", "vizFavOnly", "vizCyc", "vfit", "vinyl", "enh")
STATE_MAX, KEY_MAX = 3_000_000, 1_000_000
# users2-20261111: settings sync is generic. Every localStorage key the player writes follows the user, except these
# device-local ones (device id, sync bookkeeping, link-speed estimates, migration flags). New features need no list edit.
SYNC_DENY = ("msDev", "__msSync", "__msStash", "iosHint", "msRadioTest", "sbMig1", "vBwEst", "vUsedAt", "vres", "vresV2", "msAdultViz")  # adult-viz-20261111
_SYNC_RE = re.compile(r"^[A-Za-z0-9_.:-]{1,64}$"); SYNC_MAX_KEYS = 600
def sync_ok(k):
    return isinstance(k, str) and (k in SYNC_KEYS or (bool(_SYNC_RE.match(k)) and k not in SYNC_DENY and not k.startswith(("__", "local.", "dev."))))
LIB_KEYS = ("q", "lk", "lpl", "off", "h", "pc", "dlJobs")  # kept by "Reset settings" (library, not settings)
_VID_RE = re.compile(r"^[\w-]{11}$"); _DEV_RE = re.compile(r"^[\w-]{1,40}$")

# ---------------------------------------------------------------- password hashing
def _b64e(b): return base64.b64encode(b).decode()
def _b64d(s): return base64.b64decode(s.encode())
def hash_pw(pw, iters=PBKDF2_ITERS, salt=None):
    salt = salt or secrets.token_bytes(16)
    dk = hashlib.pbkdf2_hmac("sha256", pw.encode("utf-8"), salt, iters)
    return f"pbkdf2_sha256${iters}${_b64e(salt)}${_b64e(dk)}"
def verify_pw(pw, stored):
    try:
        alg, it, s, h = stored.split("$")
        if alg != "pbkdf2_sha256": return False
        it = int(it)
        if it < 100000 or it > 5000000: return False
        dk = hashlib.pbkdf2_hmac("sha256", (pw or "").encode("utf-8"), _b64d(s), it)
        return secrets.compare_digest(dk, _b64d(h))
    except Exception:
        return False
_DUMMY = {}
def _dummy_hash():
    if "h" not in _DUMMY: _DUMMY["h"] = hash_pw(secrets.token_urlsafe(16))
    return _DUMMY["h"]
def _th(tok): return hashlib.sha256(tok.encode()).hexdigest()
def norm_user(u): return (u or "").strip().lower()
def pw_problem(pw):
    if not isinstance(pw, str) or len(pw) < PW_MIN: return f"Password must be at least {PW_MIN} characters."
    if len(pw) > PW_MAX: return "Password is too long."
    return None
def user_problem(u):
    if not USER_RE.match(u or ""): return "Username: 2-32 letters, numbers, dot, dash or underscore."
    return None

# ---------------------------------------------------------------- file helpers
def _secure(path):
    try: os.chmod(path, 0o600)
    except Exception: pass
    if os.name == "nt":
        try:
            who = os.environ.get("USERNAME") or ""
            if who:
                subprocess.run(["icacls", str(path), "/inheritance:r", "/grant:r", f"{who}:F", "/grant:r", "SYSTEM:F"],
                               capture_output=True, timeout=15, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        except Exception: pass
def _secure_dir(path):
    try: os.chmod(path, 0o700)
    except Exception: pass
    if os.name == "nt":
        try:
            who = os.environ.get("USERNAME") or ""
            if who:
                subprocess.run(["icacls", str(path), "/inheritance:r", "/grant:r", f"{who}:(OI)(CI)F", "/grant:r", "SYSTEM:(OI)(CI)F"],
                               capture_output=True, timeout=15, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        except Exception: pass
def _atomic_write(path, obj, secure=True):
    path = Path(path); tmp = path.with_name(path.name + f".tmp{os.getpid()}")
    data = json.dumps(obj, indent=1, sort_keys=True).encode()
    fd = os.open(str(tmp), os.O_WRONLY | os.O_CREAT | os.O_TRUNC | getattr(os, "O_BINARY", 0), 0o600)
    try: os.write(fd, data)
    finally: os.close(fd)
    os.replace(str(tmp), str(path))
    if secure: _secure(path)
    else:
        try: os.chmod(path, 0o600)
        except Exception: pass

def _lock_net(ipkey):  # lock64-20261111: "cf:2001:db8:1:2:aa::5" -> "cf:2001:db8:1:2::/64"; IPv4 unchanged (/32)
    k = ipkey or "?"
    try:
        pre, _, ip = k.partition(":")
        if not ip or ":" not in ip: return k
        import ipaddress as _ia
        a = _ia.ip_address(ip.split("%")[0])
        if a.version == 6:
            if a.ipv4_mapped: return pre + ":" + str(a.ipv4_mapped)
            return pre + ":" + str(_ia.ip_network(str(a) + "/64", strict=False))
    except Exception: pass
    return k

class Store:
    def __init__(self, d):
        self.d = Path(d); self.uf = self.d / "users.json"; self.sf = self.d / "sessions.json"
        self.lock = threading.RLock(); self._u = None; self._um = None; self._s = None; self._sm = None
        self._fails = {}; self._flock = threading.Lock(); self._dirty_s = 0.0
    # ---- load/save (reloads when the file changed on disk)
    def _mt(self, f):
        try: return f.stat().st_mtime_ns
        except FileNotFoundError: return None
    def _users(self):
        m = self._mt(self.uf)
        if self._u is None or m != self._um:
            try:
                _d = json.loads(self.uf.read_text(encoding="utf-8")) if m else {}
                self._u = _d.get("users", {})
                _ua = _d.get("unlock_at")  # recover-20261111
                if _ua and _ua != getattr(self, "_ua_seen", None):
                    self._ua_seen = _ua; self._fails.clear()
            except Exception: self._u = self._u or {}
            self._um = m
        return self._u
    def _sess(self):
        m = self._mt(self.sf)
        if self._s is None or m != self._sm:
            try: self._s = json.loads(self.sf.read_text(encoding="utf-8")).get("sessions", {}) if m else {}
            except Exception: self._s = self._s or {}
            self._sm = m
        return self._s
    def _save_users(self):
        _atomic_write(self.uf, {"version": 1, "users": self._u}); self._um = self._mt(self.uf)
    def _save_sess(self):
        now = time.time()
        self._s = {k: v for k, v in self._s.items() if v.get("exp", 0) > now and v.get("u") in self._users()}
        _atomic_write(self.sf, {"version": 1, "sessions": self._s}); self._sm = self._mt(self.sf)
    # ---- users
    def has_users(self):
        with self.lock: return bool(self._users())
    def admins(self):
        with self.lock: return [n for n, x in self._users().items() if x.get("role") == "admin"]
    def get(self, u):
        with self.lock:
            x = self._users().get(norm_user(u)); return dict(x) if x else None
    def list_users(self):
        with self.lock:
            ss = self._sess(); now = time.time(); seen = {}; devs = {}
            for v in ss.values():
                if v.get("exp", 0) <= now: continue
                uu = v.get("u"); devs[uu] = devs.get(uu, 0) + 1; seen[uu] = max(seen.get(uu, 0), int(v.get("seen") or v.get("ct") or 0))
            return [{"u": n, "role": x.get("role", "user"), "created": x.get("created"), "last_login": x.get("last_login"),
                     "name": x.get("name") or "", "disabled": bool(x.get("disabled")), "adult_viz": bool(x.get("adult_viz")), "devices": devs.get(n, 0),  # users2-20261111 / adult-viz-20261111
                     "last_seen": max(seen.get(n, 0), int(x.get("last_seen") or 0), int(x.get("last_login") or 0)) or None}
                    for n, x in sorted(self._users().items())]
    # users2-20261111 ---------------------------------------------------------------------------------------------
    def set_name(self, u, name):
        u = norm_user(u); name = "".join(c for c in str(name or "") if c.isprintable()).strip()[:40]
        with self.lock:
            us = self._users()
            if u not in us: return False, "No such user."
            if name: us[u]["name"] = name
            else: us[u].pop("name", None)
            self._save_users()
        return True, None
    def set_disabled(self, u, off):
        u = norm_user(u)
        with self.lock:
            us = self._users()
            if u not in us: return False, "No such user."
            if off and us[u].get("role") == "admin" and len([n for n in self.admins() if not us[n].get("disabled")]) <= 1:
                return False, "You can't turn off the last admin."
            if off: us[u]["disabled"] = True
            else: us[u].pop("disabled", None)
            self._save_users()
            if off: self.drop_user_sessions(u)
        return True, None

    def set_adult_viz(self, u, on):  # adult-viz-20261111
        """Admin-only per-user 18+ visuals flag, off by default (missing key)."""
        u = norm_user(u)
        with self.lock:
            us = self._users()
            if u not in us: return False, "No such user."
            if on: us[u]["adult_viz"] = True
            else: us[u].pop("adult_viz", None)
            self._save_users()
        try:
            self.put_state(u, {"msAdultViz": "1" if on else "0"}, allow={"msAdultViz"})
        except Exception:
            pass
        return True, None
    def sessions_of(self, u, cur_tok=""):
        u = norm_user(u); now = time.time(); ch = _th(cur_tok) if cur_tok else ""
        with self.lock:
            L = [{"id": k[:12], "device": v.get("ua") or "Browser", "signed_in": int(v.get("ct") or 0), "last_active": int(v.get("seen") or v.get("ct") or 0),
                  "keep": bool(v.get("keep")), "current": k == ch} for k, v in self._sess().items() if v.get("u") == u and v.get("exp", 0) > now]
        return sorted(L, key=lambda x: -x["last_active"])
    def drop_session_id(self, u, sid, keep_tok=""):
        u = norm_user(u); keep = _th(keep_tok) if keep_tok else ""
        with self.lock:
            ss = self._sess(); dead = [k for k, v in ss.items() if v.get("u") == u and (k.startswith(sid) if sid else k != keep)]
            if sid and len(dead) != 1: return False, "No such device."
            for k in dead: ss.pop(k, None)
            self._save_sess()
        return True, len(dead)
    def reset_settings(self, u):
        u = norm_user(u)
        with self.lock:
            if u not in self._users(): return False, "No such user."
            j = self.get_state(u); j["ls"] = {k: v for k, v in j["ls"].items() if k in LIB_KEYS}
            j["rev"] = int(j["rev"]) + 1; j["ts"] = time.time(); self.udir(); _atomic_write(self.state_path(u), j, secure=False)
        return True, j["rev"]
    def create(self, u, pw, role="user", only_if_empty=False, must_change=False):
        u = norm_user(u); e = user_problem(u) or pw_problem(pw)
        if e: return False, e
        if role not in ("admin", "user"): return False, "Bad role."
        h = hash_pw(pw)  # slow part outside the lock
        with self.lock:
            us = self._users()
            if only_if_empty and us: return False, "Setup is already done. Sign in instead."
            if u in us: return False, "That username already exists."
            us[u] = {"role": role, "hash": h, "pwv": 1, "created": int(time.time()), "last_login": None}
            if must_change: us[u]["mcp"] = True  # must change password at first sign-in
            self._save_users()
        return True, None
    def recover(self, u, pw):  # recover-20261111: new admin password + turn on + clear every lockout
        u = norm_user(u); e = pw_problem(pw)
        if e: return False, e
        x = self.get(u)
        if not x: return False, "No such user."
        if x.get("role") != "admin": return False, "That account is not an admin."
        ok, e = self.set_password(u, pw)
        if not ok: return ok, e
        with self.lock:
            us = self._users(); us[u].pop("disabled", None); us[u].pop("mcp", None); self._save_users()
        with self._flock: self._fails.clear()
        return True, None
    def set_password(self, u, pw):
        u = norm_user(u); e = pw_problem(pw)
        if e: return False, e
        h = hash_pw(pw)
        with self.lock:
            us = self._users()
            if u not in us: return False, "No such user."
            us[u]["hash"] = h; us[u]["pwv"] = int(us[u].get("pwv", 1)) + 1; us[u].pop("mcp", None)
            self._save_users(); self.drop_user_sessions(u)
        return True, None
    def set_role(self, u, role):
        u = norm_user(u)
        if role not in ("admin", "user"): return False, "Bad role."
        with self.lock:
            us = self._users()
            if u not in us: return False, "No such user."
            if role == "user" and us[u].get("role") == "admin" and len(self.admins()) <= 1:
                return False, "You can't remove the last admin."
            us[u]["role"] = role; self._save_users()
        return True, None
    def remove(self, u):
        u = norm_user(u)
        with self.lock:
            us = self._users()
            if u not in us: return False, "No such user."
            if us[u].get("role") == "admin" and len(self.admins()) <= 1: return False, "You can't remove the last admin."
            us.pop(u); self._save_users(); self.drop_user_sessions(u)
            for f in (self.state_path(u), self.plays_path(u)):
                try: f.unlink()
                except FileNotFoundError: pass
                except Exception: pass
        return True, None
    # ---- login throttling
    def _recent(self, key, now):
        L = [t for t in self._fails.get(key, []) if now - t < FAIL_WIN]
        if L: self._fails[key] = L
        else: self._fails.pop(key, None)
        return L
    # users3-20261111: per user+IP lock; IP spray + per-user ceilings only for non-LAN clients
    @staticmethod
    def _lan(ipkey):
        k = ipkey or ""
        if not k.startswith("peer:"): return False
        ip = k[5:]
        if ip.startswith("127.") or ip in ("::1", "localhost") or ip.startswith("10.") or ip.startswith("192.168.") or ip.startswith("fe80:") or ip.startswith("fd"): return True
        m = re.match(r"^172\.(\d+)\.", ip)
        return bool(m and 16 <= int(m.group(1)) <= 31)
    def _fkeys(self, ipkey, u):
        u = norm_user(u); ip = _lock_net(ipkey)  # lock64-20261111
        ks = [("ui:" + u + "|" + ip, FAIL_MAX)]
        if not self._lan(ipkey): ks += [("ip:" + ip, FAIL_IP_MAX), ("u:" + u, FAIL_USER_MAX)]
        return ks
    def locked_for(self, ipkey, u, now=None):
        now = time.time() if now is None else now
        with self._flock:
            wait = 0
            for k, mx in self._fkeys(ipkey, u):
                L = self._recent(k, now)
                if len(L) >= mx: wait = max(wait, int(L[-mx] + FAIL_WIN - now) + 1)
            return wait
    def _fail(self, ipkey, u, now):
        with self._flock:
            for k, _ in self._fkeys(ipkey, u):
                self._fails.setdefault(k, []).append(now)
            if len(self._fails) > 5000:
                for k in [k for k, v in self._fails.items() if not v or now - v[-1] > FAIL_WIN][:2500]: self._fails.pop(k, None)
    def check_login(self, u, pw, ipkey, now=None, trusted=False):
        """-> ("ok", name) | ("bad", None) | ("locked", seconds)"""
        now = time.time() if now is None else now; u = norm_user(u)
        x = self.get(u) if USER_RE.match(u or "") else None
        adm_t = bool(trusted and x and x.get("role") == "admin")  # recover-20261111: admin at home is never locked out
        w = 0 if adm_t else self.locked_for(ipkey, u, now)
        if w: return "locked", w
        ok = verify_pw(pw or "", x["hash"] if x else _dummy_hash())
        if not (ok and x):
            if not adm_t: self._fail(ipkey, u, now)
            return "bad", None
        with self._flock: self._fails.pop("ui:" + u + "|" + _lock_net(ipkey), None)  # users3-20261111
        if x.get("disabled"): return "disabled", None  # users2-20261111
        with self.lock:
            us = self._users()
            if u in us: us[u]["last_login"] = int(now); self._save_users()
        return "ok", u
    # ---- sessions
    def new_session(self, u, keep, now=None, ua=""):
        now = time.time() if now is None else now; u = norm_user(u)
        tok = secrets.token_urlsafe(32)
        with self.lock:
            x = self._users().get(u)
            if not x: return None
            ss = self._sess()
            mine = sorted([(v.get("ct", 0), k) for k, v in ss.items() if v.get("u") == u])
            for _, k in mine[:max(0, len(mine) - MAX_SESS_PER_USER + 1)]: ss.pop(k, None)
            ss[_th(tok)] = {"u": u, "keep": bool(keep), "exp": now + (KEEP_TTL if keep else SHORT_TTL), "ren": now, "ct": now, "pwv": x.get("pwv", 1), "seen": now}
            if ua: ss[_th(tok)]["ua"] = str(ua)[:60]  # users2-20261111
            self._save_sess()
        return tok
    def session(self, tok, now=None):
        """-> (user_info_dict, renewed_keep_flag_or_None) ; (None, None) if invalid."""
        if not tok or not _TOK_RE.match(tok): return None, None
        now = time.time() if now is None else now
        with self.lock:
            ss = self._sess(); h = _th(tok); s = ss.get(h)
            if not s: return None, None
            x = self._users().get(s.get("u"))
            if not x or s.get("exp", 0) <= now or s.get("pwv") != x.get("pwv", 1) or x.get("disabled"):  # users2-20261111
                ss.pop(h, None); self._save_sess(); return None, None
            ren = None
            if now - (s.get("seen") or 0) >= 300: s["seen"] = now; self._dirty_s = now  # users2-20261111: last active (5-min grain)
            if now - s.get("ren", 0) >= (RENEW_KEEP if s.get("keep") else RENEW_SHORT):
                s["exp"] = now + (KEEP_TTL if s.get("keep") else SHORT_TTL); s["ren"] = now; self._save_sess(); self._dirty_s = 0
                ren = bool(s.get("keep"))
            elif self._dirty_s and now - self._dirty_s < 1: self._save_sess(); self._dirty_s = 0
            return {"u": s["u"], "role": x.get("role", "user"), "keep": bool(s.get("keep")), "mcp": bool(x.get("mcp")), "name": x.get("name") or "", "adult_viz": bool(x.get("adult_viz"))}, ren
    def drop_session(self, tok):
        if not tok: return
        with self.lock:
            if self._sess().pop(_th(tok), None) is not None: self._save_sess()
    def drop_user_sessions(self, u):
        u = norm_user(u)
        with self.lock:
            ss = self._sess(); dead = [k for k, v in ss.items() if v.get("u") == u]
            for k in dead: ss.pop(k, None)
            if dead or self.sf.exists(): self._save_sess()

    # ---- per-user state (login-state-20261110)
    def udir(self):
        d = self.d / "user_data"
        if not d.is_dir():
            d.mkdir(parents=True, exist_ok=True); _secure_dir(d)
        return d
    def state_path(self, u):
        u = norm_user(u)
        if not USER_RE.match(u): raise ValueError("bad user")
        return self.d / "user_data" / f"{u}.json"
    def plays_path(self, u):
        u = norm_user(u)
        if not USER_RE.match(u): raise ValueError("bad user")
        self.udir(); return self.d / "user_data" / f"{u}.plays.json"
    def get_state(self, u):
        with self.lock:
            try: j = json.loads(self.state_path(u).read_text(encoding="utf-8"))
            except Exception: j = {}
            j.setdefault("rev", 0); j.setdefault("ts", 0); j.setdefault("ls", {}); j.setdefault("now", None)
            return j
    def put_state(self, u, set_=None, dele=None, now=None, allow=None):
        """Per-key merge (last write wins per key). -> (ok, rev_or_error)"""
        allow = set(allow or ())
        set_ = {k: v for k, v in (set_ or {}).items() if isinstance(v, str) and (k in allow or sync_ok(k))}  # users2-20261111 / adult-viz-20261111
        dele = [k for k in (dele or []) if k in allow or sync_ok(k)]
        if any(len(v) > KEY_MAX for v in set_.values()): return False, "value too large"
        with self.lock:
            if norm_user(u) not in self._users(): return False, "no such user"
            j = self.get_state(u); ls = j["ls"]
            ls.update(set_)
            for k in dele: ls.pop(k, None)
            if now is not None: j["now"] = now
            if sum(len(k) + len(v) for k, v in ls.items()) > STATE_MAX: return False, "state too large"
            if len(ls) > SYNC_MAX_KEYS: return False, "too many keys"
            j["rev"] = int(j["rev"]) + 1; j["ts"] = time.time()
            self.udir(); _atomic_write(self.state_path(u), j, secure=False)
            return True, j["rev"]
def clean_now(n, now=None):
    if not isinstance(n, dict) or not _VID_RE.match(str(n.get("id") or "")): return None
    f = lambda x, d=0.0: float(x) if isinstance(x, (int, float)) and x == x and abs(x) < 1e7 else d
    return {"id": n["id"], "title": str(n.get("title") or "")[:200], "channel": str(n.get("channel") or "")[:120],
            "dur": max(0.0, f(n.get("dur"))), "t": max(0.0, f(n.get("t"))), "playing": bool(n.get("playing")),
            "dev": n["dev"] if isinstance(n.get("dev"), str) and _DEV_RE.match(n["dev"]) else "",
            "ts": time.time() if now is None else now}

# ---------------------------------------------------------------- HTTP glue
STORE = None
HOOKS = {}
def init(root, is_local, ipkey, https, origins=""):
    """is_local(handler) -> bool (LAN/Tailscale/loopback peer and no proxy/tunnel headers); ipkey(handler) -> str; https(handler) -> bool
    origins: optional comma list of extra public hosts allowed as Origin for POSTs (e.g. "music.example.com")."""
    global STORE
    STORE = Store(root); HOOKS.update(is_local=is_local, ipkey=ipkey, https=https, plays_global=Path(root) / "lcache" / "plays" / "plays.json",
                                      origins={x.strip().lower() for x in (origins or "").split(",") if x.strip()})
    return STORE

def _cookie_tok(handler):
    raw = handler.headers.get("Cookie") or ""
    m = re.search(r"(?:^|;\s*)" + COOKIE + r"=([A-Za-z0-9_-]{32,64})(?:;|$)", raw)
    return m.group(1) if m else ""
def _cookie_hdr(handler, tok, keep):
    c = f"{COOKIE}={tok}; Path=/; HttpOnly; SameSite=Lax"
    if keep: c += f"; Max-Age={KEEP_TTL}"
    if HOOKS["https"](handler): c += "; Secure"
    return c
def _clear_hdr(handler):
    return f"{COOKIE}=; Path=/; Max-Age=0; HttpOnly; SameSite=Lax" + ("; Secure" if HOOKS["https"](handler) else "")
def _add_hdr(handler, k, v):
    L = getattr(handler, "_ms_hdrs", None)
    if L is None: L = []; handler._ms_hdrs = L
    L.append((k, v))

def request_user(handler):
    """Called from H.guard() for every request: validates ms_sess, slides its expiry. -> user dict or None."""
    handler._ms_hdrs = []; handler._ms_full = None
    if STORE is None: return None
    tok = _cookie_tok(handler)
    if not tok: return None
    info, ren = STORE.session(tok)
    if info is None:
        _add_hdr(handler, "Set-Cookie", _clear_hdr(handler)); return None
    if ren: _add_hdr(handler, "Set-Cookie", _cookie_hdr(handler, tok, True))
    handler._ms_full = info
    return None if info.get("mcp") else info  # must-change-password: only the change page works until then
def _full(handler, user): return getattr(handler, "_ms_full", None) or user
def can_setup(handler):
    """First-run setup: home network, or a browser that already holds the owner key / its ms_auth cookie."""
    if HOOKS["is_local"](handler): return True
    k = HOOKS.get("keyauth")
    try: return bool(k and k(handler))
    except Exception: return False

def _safe_next(n):
    n = (n or "/").strip()
    if not n.startswith("/") or n.startswith("//") or "\\" in n or any(c in n for c in "\r\n\t"): return "/"
    if n.startswith(("/login", "/setup", "/api/")): return "/"
    return n[:600]
def _send_page(handler, code, body):
    _add_hdr(handler, "Content-Security-Policy", "default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'; form-action 'self'; base-uri 'none'")
    handler._cc = "no-store"
    return handler.send(code, body, "text/html; charset=utf-8")
def _json(handler, code, obj):
    handler._cc = "no-store"
    return handler.send(code, json.dumps(obj), "application/json")
def _redirect(handler, to):
    handler.send_response(302); handler.send_header("Location", to); handler.send_header("Content-Length", "0"); handler.end_headers()

def deny(handler):
    """Unauthenticated request: 401 JSON for API/non-GET, login page for pages, 401 text for media."""
    try: u = urllib.parse.urlparse(handler.path)
    except Exception: u = urllib.parse.urlparse("/")
    p = u.path or "/"
    full = getattr(handler, "_ms_full", None)
    if p.startswith("/api/") or (handler.command or "GET").upper() != "GET":
        return _json(handler, 401, {"error": "password change required" if full else "login required", "login": "/login"})
    acc = handler.headers.get("Accept") or ""
    if full and (p in ("/", "/index.html", "/users") or "text/html" in acc):
        return _send_page(handler, 401, change_page(full["u"], _safe_next(handler.path)))
    if p in ("/", "/index.html", "/users") or "text/html" in acc:
        return _send_page(handler, 401, login_page(handler, _safe_next(handler.path)))
    handler._cc = "no-store"
    return handler.send(401, "login required", "text/plain")

def _js(obj): return json.dumps(obj, separators=(",", ":")).replace("<", "\\u003c").replace("\u2028", "\\u2028").replace("\u2029", "\\u2029")
def with_boot(page, user):
    """Player page with window.__msBoot (signed-in user + their saved state) injected before every other script."""
    boot = {"user": None, "keys": list(SYNC_KEYS), "deny": list(SYNC_DENY), "generic": True}  # users2-20261111
    if user and STORE is not None:
        st = STORE.get_state(user["u"])
        boot.update(user=user["u"], role=user["role"], adultViz=bool(user.get("adult_viz")), state={"rev": st["rev"], "ls": st["ls"], "now": st["now"]})  # adult-viz-20261111
        try: boot["name"] = (STORE.get(user["u"]) or {}).get("name") or ""
        except Exception: pass
    tag = ("<script>/* login-state-20261110 */window.__msBoot=" + _js(boot) + "</script>").encode("utf-8")
    b = page if isinstance(page, (bytes, bytearray)) else str(page).encode("utf-8")
    anchor = b"<meta charset=utf-8>"
    i = b.find(anchor)
    return b[:i + len(anchor)] + tag + b[i + len(anchor):] if i >= 0 else tag + b
def state_get(handler, user, qs):
    if not user: return _json(handler, 200, {"user": None})
    st = STORE.get_state(user["u"])
    try: since = int(qs.get("since", "-1"))
    except Exception: since = -1
    out = {"user": user["u"], "rev": st["rev"], "ts": st["ts"], "now": st["now"]}
    if since != st["rev"]: out["ls"] = st["ls"]
    return _json(handler, 200, out)
def migrate_to(u, ls):
    """First admin: copy this browser's existing (shared default profile) data + the server play history."""
    ls = {k: v for k, v in (ls or {}).items() if sync_ok(k) and isinstance(v, str)} if isinstance(ls, dict) else {}
    if ls: STORE.put_state(u, ls, [], None)
    g = HOOKS.get("plays_global")
    try:
        if g and Path(g).is_file():
            dst = STORE.plays_path(u)
            if not dst.exists():
                dst.write_bytes(Path(g).read_bytes())
                try: os.chmod(dst, 0o600)
                except Exception: pass
    except Exception: pass
def me(handler, user, trusted):
    has = STORE.has_users()
    return {"user": user["u"] if user else None, "role": user["role"] if user else None, "keep": user["keep"] if user else None,
            "trusted": bool(trusted), "setup_needed": not has, "can_setup": (not has) and can_setup(handler),
            "must_change": bool(user and user.get("mcp")), "name": (user.get("name") or "") if user else "",
            "adult_viz": bool(user.get("adult_viz")) if user else False}

def _ua_label(handler):  # users2-20261111: "Chrome on Android" style device label (no fingerprinting, just the UA family)
    ua = handler.headers.get("User-Agent") or ""
    osn = next((n for k, n in (("Android", "Android"), ("iPhone", "iPhone"), ("iPad", "iPad"), ("Windows", "Windows"), ("Mac OS", "Mac"), ("CrOS", "ChromeOS"), ("Linux", "Linux")) if k in ua), "")
    br = next((n for k, n in (("Edg/", "Edge"), ("OPR/", "Opera"), ("SamsungBrowser", "Samsung Internet"), ("Firefox/", "Firefox"), ("Chrome/", "Chrome"), ("Safari/", "Safari")) if k in ua), "Browser")
    return br + (" on " + osn if osn else "")
def handle_get(handler, path, qs, user, trusted):
    user = _full(handler, user)
    if user and user.get("mcp"):
        if path in ("/login", "/users"): return _send_page(handler, 200, change_page(user["u"], _safe_next(qs.get("next")) if path == "/login" else "/users"))
        if path in ("/api/users", "/api/state"): return _json(handler, 403, {"error": "Change your password first."})
    if path == "/recover":  # recover-20261111
        if not _loopback_only(handler): return _send_page(handler, 403, notice_page("Not available here", "Account recovery only opens on the server device itself, at http://127.0.0.1:8121/recover."))
        return _send_page(handler, 200, recover_page())
    if path == "/login":
        nx = _safe_next(qs.get("next"))
        if user: return _redirect(handler, nx)
        if not STORE.has_users() and can_setup(handler): return _redirect(handler, "/setup")
        return _send_page(handler, 200, login_page(handler, nx))
    if path == "/setup":
        if STORE.has_users(): return _redirect(handler, "/login")
        if not can_setup(handler): return _send_page(handler, 403, notice_page("Setup is only available at home", "To keep your account safe, the first admin account can only be created from your home Wi-Fi. Open the app at home and try again."))
        return _send_page(handler, 200, setup_page())
    if path == "/users":
        if not user: return _send_page(handler, 401, login_page(handler, "/users"))
        return _send_page(handler, 200, users_page())
    if path == "/api/auth/me": return _json(handler, 200, me(handler, user, trusted))
    if path == "/api/auth/sessions":  # users2-20261111: my devices
        if not user: return _json(handler, 401, {"error": "login required", "login": "/login"})
        return _json(handler, 200, {"sessions": STORE.sessions_of(user["u"], _cookie_tok(handler))})
    if path == "/api/state": return state_get(handler, user, qs)
    if path == "/api/users":
        if not user: return _json(handler, 401, {"error": "login required", "login": "/login"})
        if user["role"] != "admin": return _json(handler, 403, {"error": "Admins only."})
        return _json(handler, 200, {"users": STORE.list_users(), "me": user["u"]})
    return _json(handler, 404, {"error": "not found"})

def _same_origin(handler):
    o = handler.headers.get("Origin")
    if not o: return True  # non-browser client; cookies are SameSite=Lax anyway
    try: on = urllib.parse.urlparse(o).netloc.lower()
    except Exception: return False
    hosts = {(handler.headers.get("Host") or "").lower(), (handler.headers.get("X-Forwarded-Host") or "").lower()}
    return bool(on) and (on in hosts or on in HOOKS.get("origins", ()))

def handle_post(handler, path, user, trusted):
    user = _full(handler, user)
    try: n = min(int(handler.headers.get("Content-Length", 0) or 0), STATE_MAX + 65536 if path in ("/api/state", "/api/auth/setup") else 16384)
    except Exception: n = 0
    raw = handler.rfile.read(n) if n > 0 else b""
    if not _same_origin(handler): return _json(handler, 403, {"error": "Bad origin."})
    if "application/json" not in (handler.headers.get("Content-Type") or "").lower(): return _json(handler, 415, {"error": "JSON required."})
    try: j = json.loads(raw.decode("utf-8") or "{}"); j = j if isinstance(j, dict) else {}
    except Exception: j = {}
    s = lambda k: j.get(k) if isinstance(j.get(k), str) else ""
    if path == "/api/auth/recover":  # recover-20261111: this device only
        if not _loopback_only(handler): return _json(handler, 403, {"error": "Recovery only works on the server device itself (http://127.0.0.1)."})
        if s("p") != s("p2"): return _json(handler, 400, {"error": "The two passwords don't match."})
        ok, e = STORE.recover(s("u"), s("p"))
        return _json(handler, 200, {"ok": True}) if ok else _json(handler, 400, {"error": e})
    if path == "/api/auth/login":
        st, v = STORE.check_login(s("u"), s("p"), HOOKS["ipkey"](handler), trusted=_admin_trusted(handler))
        if st == "locked":
            mins = max(1, (v + 59) // 60)
            return _json(handler, 429, {"error": f"Too many attempts. Try again in {mins} minute{'s' if mins != 1 else ''}."})
        if st == "disabled": return _json(handler, 403, {"error": "This account is turned off. Ask the admin to turn it back on."})  # users2-20261111
        if st != "ok": return _json(handler, 401, {"error": "Wrong username or password."})
        keep = j.get("keep", True) is not False
        old = _cookie_tok(handler)
        if old: STORE.drop_session(old)
        tok = STORE.new_session(v, keep, ua=_ua_label(handler))
        _add_hdr(handler, "Set-Cookie", _cookie_hdr(handler, tok, keep))
        x = STORE.get(v)
        return _json(handler, 200, {"ok": True, "user": v, "role": x.get("role") if x else "user", "must_change": bool(x and x.get("mcp")), "adult_viz": bool(x.get("adult_viz")) if x else False})
    if path == "/api/auth/logout":
        STORE.drop_session(_cookie_tok(handler)); _add_hdr(handler, "Set-Cookie", _clear_hdr(handler))
        return _json(handler, 200, {"ok": True})
    if path == "/api/auth/setup":
        if not can_setup(handler): return _json(handler, 403, {"error": "Setup is only available on your home network."})
        if STORE.has_users(): return _json(handler, 409, {"error": "Setup is already done. Sign in instead."})
        if s("p") != s("p2"): return _json(handler, 400, {"error": "The two passwords don't match."})
        ok, e = STORE.create(s("u"), s("p"), "admin", only_if_empty=True)
        if not ok: return _json(handler, 400, {"error": e})
        u = norm_user(s("u"))
        try: migrate_to(u, j.get("ls"))
        except Exception: pass
        tok = STORE.new_session(u, True)
        _add_hdr(handler, "Set-Cookie", _cookie_hdr(handler, tok, True))
        return _json(handler, 200, {"ok": True, "user": u, "role": "admin"})
    if not user: return _json(handler, 401, {"error": "login required", "login": "/login"})
    if user.get("mcp") and path != "/api/auth/password": return _json(handler, 403, {"error": "Change your password first."})
    if path == "/api/state":
        st, d = j.get("set"), j.get("del")
        ok, rv = STORE.put_state(user["u"], st if isinstance(st, dict) else {}, d if isinstance(d, list) else [],
                                 clean_now(j.get("now")) if j.get("now") is not None else None)
        if not ok: return _json(handler, 413 if "large" in str(rv) else 400, {"error": rv})
        return _json(handler, 200, {"ok": True, "rev": rv})
    if path == "/api/auth/sessions":  # users2-20261111: my devices (POST: every /api/auth/* POST reaches this module)
        return _json(handler, 200, {"sessions": STORE.sessions_of(user["u"], _cookie_tok(handler))})
    if path == "/api/auth/name":  # users2-20261111
        ok, e = STORE.set_name(user["u"], s("name"))
        return _json(handler, 200, {"ok": True}) if ok else _json(handler, 400, {"error": e})
    if path == "/api/auth/signout":  # users2-20261111: {"sid": id} one device, {"others": true} every other device, {} everywhere
        tok = _cookie_tok(handler)
        if s("sid"): ok, n = STORE.drop_session_id(user["u"], s("sid"))
        elif j.get("others"): ok, n = STORE.drop_session_id(user["u"], "", keep_tok=tok)
        else:
            STORE.drop_user_sessions(user["u"]); _add_hdr(handler, "Set-Cookie", _clear_hdr(handler)); return _json(handler, 200, {"ok": True, "self": True})
        if not ok: return _json(handler, 400, {"error": n})
        return _json(handler, 200, {"ok": True, "n": n, "sessions": STORE.sessions_of(user["u"], tok)})
    if path == "/api/auth/reset-settings":  # users2-20261111: my settings back to defaults (likes/playlists/history kept)
        ok, rv = STORE.reset_settings(user["u"])
        return _json(handler, 200, {"ok": True, "rev": rv}) if ok else _json(handler, 400, {"error": rv})
    if path == "/api/auth/password":
        st, v = STORE.check_login(user["u"], s("old"), HOOKS["ipkey"](handler), trusted=_admin_trusted(handler))
        if st == "locked": return _json(handler, 429, {"error": "Too many attempts. Try again later."})
        if st != "ok": return _json(handler, 401, {"error": "Current password is wrong."})
        ok, e = STORE.set_password(user["u"], s("new"))
        if not ok: return _json(handler, 400, {"error": e})
        tok = STORE.new_session(user["u"], user.get("keep", True))
        _add_hdr(handler, "Set-Cookie", _cookie_hdr(handler, tok, user.get("keep", True)))
        return _json(handler, 200, {"ok": True})
    if path == "/api/users":
        if user["role"] != "admin": return _json(handler, 403, {"error": "Admins only."})
        op, t = s("op"), norm_user(s("u"))
        if op == "add": ok, e = STORE.create(t, s("p"), "admin" if s("role") == "admin" else "user")
        elif op == "reset": ok, e = STORE.set_password(t, s("p"))
        elif op == "remove": ok, e = STORE.remove(t)
        elif op == "role": ok, e = STORE.set_role(t, s("role"))
        elif op in ("disable", "enable"):  # users2-20261111
            ok, e = (False, "You can't turn off your own account.") if op == "disable" and t == user["u"] else STORE.set_disabled(t, op == "disable")
        elif op == "signout":
            if t == user["u"]: ok, e = STORE.drop_session_id(t, "", keep_tok=_cookie_tok(handler)); ok, e = ok, None
            else: STORE.drop_user_sessions(t) if STORE.get(t) else None; ok, e = (True, None) if STORE.get(t) else (False, "No such user.")
        elif op == "name": ok, e = STORE.set_name(t, s("name"))
        elif op == "reset_settings": ok, e = STORE.reset_settings(t); e = None if ok else e
        elif op == "adult_viz":  # adult-viz-20261111
            on = j.get("on")
            if isinstance(on, str): on = on.strip().lower() in ("1", "true", "on", "yes")
            ok, e = STORE.set_adult_viz(t, bool(on))
        else: return _json(handler, 400, {"error": "Unknown action."})
        if not ok: return _json(handler, 400, {"error": e})
        out = {"ok": True, "users": STORE.list_users()}
        if op == "reset" and t == user["u"]:  # own password reset from the list: keep this browser signed in
            tok = STORE.new_session(t, user.get("keep", True)); _add_hdr(handler, "Set-Cookie", _cookie_hdr(handler, tok, user.get("keep", True)))
        if op == "remove" and t == user["u"]: out["self_removed"] = True
        return _json(handler, 200, out)
    return _json(handler, 404, {"error": "not found"})

# ---------------------------------------------------------------- pages (app look: dark, Inter/system, tomato accent)
CSS = """:root{--tom:#ff4f2b;--mus:#f5b700;--cob:#3d5afe;--bg:#0b0b10;--card:rgba(255,255,255,.06);--line:rgba(255,255,255,.12);--txt:#fff;--sub:rgba(235,235,245,.66);--bad:#ff6b6b;--ok:#4ade80}
*{box-sizing:border-box}html,body{margin:0;min-height:100%}body{background:var(--bg);color:var(--txt);font:15px/1.45 Inter,system-ui,-apple-system,Segoe UI,Roboto,sans-serif;min-height:100vh;min-height:100dvh;display:flex;flex-direction:column;align-items:center;padding:max(24px,env(safe-area-inset-top)) 16px 32px}
body:before{content:"";position:fixed;inset:0;z-index:-1;background:radial-gradient(at 15% 10%,#ff4f2b55 0,transparent 55%),radial-gradient(at 90% 20%,#f5b70040 0,transparent 55%),radial-gradient(at 50% 100%,#3d5afe55 0,transparent 60%),linear-gradient(#0b0b10cc,#0b0b10f2)}
.brand{display:flex;align-items:center;gap:10px;margin:4vh 0 18px;font-weight:800;font-size:22px;letter-spacing:.2px}.brand img{width:40px;height:40px;border-radius:12px}
.card{width:100%;max-width:400px;background:var(--card);border:1px solid var(--line);border-radius:20px;padding:24px 22px;backdrop-filter:blur(18px);-webkit-backdrop-filter:blur(18px);box-shadow:0 20px 60px #0008}
.wide{max-width:760px}h1{font-size:21px;margin:0 0 6px}p.sub{margin:0 0 18px;color:var(--sub);font-size:14px}
label.f{display:block;font-size:13px;font-weight:600;margin:14px 0 6px;color:var(--sub)}
input[type=text],input[type=password]{width:100%;height:46px;border-radius:12px;border:1px solid var(--line);background:rgba(0,0,0,.35);color:var(--txt);padding:0 14px;font:inherit;outline:none}
input[type=text]:focus,input[type=password]:focus{border-color:var(--tom);box-shadow:0 0 0 3px #ff4f2b33}
.chk{display:flex;align-items:center;gap:10px;margin:16px 0 4px;font-size:14px;cursor:pointer;user-select:none}.chk input{width:20px;height:20px;accent-color:var(--tom);margin:0}.chk.adultviz{margin:0;min-height:44px;padding:0 12px;border:1px solid var(--line);border-radius:999px;background:rgba(255,255,255,.06);font-size:13px;font-weight:600}
.btn{display:inline-flex;align-items:center;justify-content:center;min-height:44px;padding:0 18px;border-radius:999px;border:1px solid var(--line);background:rgba(255,255,255,.08);color:var(--txt);font:600 14px Inter,system-ui,sans-serif;cursor:pointer;text-decoration:none;white-space:nowrap}
.btn:hover{background:rgba(255,255,255,.14)}.btn:disabled{opacity:.6;cursor:progress}
.btn.pri{width:100%;margin-top:18px;height:48px;background:var(--tom);border-color:var(--tom);color:#fff;font-size:15px}.btn.pri:hover{filter:brightness(1.08)}
.btn.sm{min-height:36px;padding:0 12px;font-size:13px}.btn.danger{border-color:#ff6b6b88;color:#ffb3b3}
.err{min-height:20px;margin-top:12px;color:var(--bad);font-size:14px;font-weight:600}.err:empty{display:none}.msg{margin-top:12px;color:var(--ok);font-size:14px;font-weight:600}.msg:empty{display:none}
.note{margin-top:16px;padding:12px 14px;border-radius:12px;background:rgba(255,255,255,.05);color:var(--sub);font-size:13px}
.foot{margin-top:18px;color:var(--sub);font-size:12.5px;text-align:center}.foot a{color:var(--txt)}
.top{width:100%;max-width:760px;display:flex;align-items:center;justify-content:space-between;gap:10px;margin:0 0 16px;flex-wrap:wrap}.top .brand{margin:0}
.u{display:grid;grid-template-columns:1fr auto;gap:10px;align-items:center;padding:14px 0;border-top:1px solid var(--line)}.u:first-of-type{border-top:0}
.u .n{font-weight:700;font-size:15px;overflow-wrap:anywhere}.u .m{color:var(--sub);font-size:12.5px;margin-top:2px}
.badge{display:inline-block;margin-left:8px;padding:1px 8px;border-radius:999px;font-size:11px;font-weight:700;letter-spacing:.3px;vertical-align:2px;background:rgba(255,255,255,.1);color:var(--sub)}.badge.admin{background:#ff4f2b33;color:#ffb3a3}.badge.me{background:#3d5afe33;color:#b9c3ff}
.acts{display:flex;gap:6px;flex-wrap:wrap;justify-content:flex-end}.inl{grid-column:1/-1;display:flex;gap:8px;flex-wrap:wrap}.inl input{flex:1 1 180px}
.sec{margin-top:18px}.sec h2{font-size:16px;margin:0 0 4px}.row{display:flex;gap:10px;flex-wrap:wrap;align-items:flex-end}.row>div{flex:1 1 200px}
.radio{display:flex;gap:14px;margin-top:12px;font-size:14px}.radio label{display:flex;gap:6px;align-items:center;cursor:pointer}.radio input{accent-color:var(--tom)}
.u{grid-template-columns:1fr}.u .acts{display:flex;flex-wrap:wrap;gap:6px;justify-content:flex-start}/* users2-20261111: actions under the name at every width */@media (max-width:520px){.u{grid-template-columns:1fr}.acts{justify-content:flex-start}.card{padding:20px 16px}}"""

def _shell(title, body, script="", wide=False):
    return ("<!doctype html><html lang=en><head><meta charset=utf-8><meta name=viewport content=\"width=device-width,initial-scale=1,viewport-fit=cover\">"
            f"<meta name=theme-color content=\"#0b0b10\"><meta name=robots content=noindex><title>{title} · Music</title><link rel=icon href=\"/icon.svg\">"
            f"<style>{CSS}</style></head><body>{body}<script>{script}</script></body></html>")
def _brand(): return '<div class=brand><img src="/icon.svg" alt=""><span>Music</span></div>'
_JS_POST = "async function post(u,b){const r=await fetch(u,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(b),credentials:'same-origin'});let j={};try{j=await r.json()}catch(e){}return [r,j]}"

def login_page(handler, nxt="/"):
    setup = STORE is not None and not STORE.has_users()
    local = bool(HOOKS.get("is_local") and HOOKS["is_local"](handler))
    if setup and not local:
        return notice_page("Sign-in isn't set up yet", "No accounts exist yet. Open the app on your home Wi-Fi once to create the admin account, then you can sign in here from anywhere.")
    nx = json.dumps(nxt).replace("<", "\\u003c")
    body = (_brand() + '<main class=card><h1>Sign in</h1><p class=sub>Sign in to listen from anywhere.</p>'
            '<form id=f novalidate><label class=f for=u>Username</label><input type=text id=u name=username autocomplete=username autocapitalize=none spellcheck=false required>'
            '<label class=f for=p>Password</label><input type=password id=p name=password autocomplete=current-password required>'
            '<label class=chk><input type=checkbox id=k checked> Keep me signed in</label>'
            '<button class="btn pri" id=b type=submit>Sign in</button><div class=err id=e role=alert aria-live=assertive></div></form></main>'
            '<div class=foot>Ask the admin if you need an account.</div>')
    js = _JS_POST + f"const NX={nx};" + """const $=i=>document.getElementById(i);$('u').focus();
$('f').onsubmit=async ev=>{ev.preventDefault();const u=$('u').value.trim(),p=$('p').value;if(!u||!p){$('e').textContent='Enter your username and password.';return}
$('b').disabled=true;$('b').textContent='Signing in…';$('e').textContent='';try{const [r,j]=await post('/api/auth/login',{u,p,keep:$('k').checked});
if(r.ok){location.replace(NX);return}$('e').textContent=j.error||'Sign-in failed. Try again.';$('p').value='';$('p').focus()}catch(e){$('e').textContent='Network error. Try again.'}
$('b').disabled=false;$('b').textContent='Sign in'}"""
    return _shell("Sign in", body, js)

def setup_page():
    body = (_brand() + '<main class=card><h1>Create admin account</h1><p class=sub>This is the first account. It can add and remove other users. Only available on your home network.</p>'
            '<form id=f novalidate><label class=f for=u>Username</label><input type=text id=u autocomplete=username autocapitalize=none spellcheck=false required>'
            f'<label class=f for=p>Password <span style="font-weight:400">(at least {PW_MIN} characters)</span></label><input type=password id=p autocomplete=new-password required>'
            '<label class=f for=p2>Confirm password</label><input type=password id=p2 autocomplete=new-password required>'
            '<button class="btn pri" id=b type=submit>Create account</button><div class=err id=e role=alert aria-live=assertive></div></form></main>'
            '<div class=foot>Your current likes, playlists, history and settings on this browser move into this account.<br><a href="/">Not now, open the player</a></div>')
    js = _JS_POST + "const KEYS=" + _js(list(SYNC_KEYS)) + ";" + """const $=i=>document.getElementById(i);$('u').focus();
$('f').onsubmit=async ev=>{ev.preventDefault();const u=$('u').value.trim(),p=$('p').value,p2=$('p2').value;if(!u||!p){$('e').textContent='Choose a username and password.';return}
if(p!==p2){$('e').textContent="The two passwords don't match.";return}$('b').disabled=true;$('e').textContent='';
const ls={};try{const m=JSON.parse(localStorage.getItem('__msSync')||'{}');if(!m.u)KEYS.forEach(k=>{const v=localStorage.getItem(k);if(v!==null)ls[k]=v})}catch(e){}
try{const [r,j]=await post('/api/auth/setup',{u,p,p2,ls});if(r.ok){location.replace('/users');return}$('e').textContent=j.error||'Could not create the account.'}catch(e){$('e').textContent='Network error. Try again.'}$('b').disabled=false}"""
    return _shell("Create admin account", body, js)

def notice_page(title, text):
    body = _brand() + f'<main class=card><h1>{title}</h1><p class=sub style="margin:0">{text}</p></main><div class=foot><a href="/login">Sign in</a></div>'
    return _shell(title, body)

def users_page():
    body = ('<div class=top>' + _brand() + '<div class=acts><a class="btn sm" href="/">&#8592; Back to player</a><button class="btn sm" id=lo type=button>Sign out</button></div></div>'
            '<main class="card wide"><h1 id=h>Account</h1><p class=sub id=who></p>'
            '<section id=adm hidden><div id=list></div>'
            '<div class=sec><h2>Add a user</h2><form id=af class=row novalidate><div><label class=f for=nu>Username</label><input type=text id=nu autocomplete=off autocapitalize=none spellcheck=false></div>'
            f'<div><label class=f for=np>Password <span style="font-weight:400">({PW_MIN}+ characters)</span></label><input type=password id=np autocomplete=new-password></div>'
            '<div style="flex:0 0 auto"><button class="btn" id=ab type=submit style="height:46px">Add user</button></div></form>'
            '<div class=radio><label><input type=radio name=nr value=user checked> User</label><label><input type=radio name=nr value=admin> Admin</label></div>'
            '<div class=err id=ae role=alert></div><div class=msg id=am aria-live=polite></div></div></section>'
            '<div class=sec><h2>My profile</h2><form id=nf class=row novalidate><div><label class=f for=nn>Display name</label><input type=text id=nn maxlength=40 autocomplete=nickname></div>'
            '<div style="flex:0 0 auto"><button class="btn" id=nb type=submit style="height:46px">Save</button></div></form>'
            '<div class=b style="display:flex;gap:8px;flex-wrap:wrap;margin-top:12px"><button class="btn sm" id=rs type=button>Reset my settings</button></div>'
            '<div class=err id=ne role=alert></div><div class=msg id=nm aria-live=polite></div></div>'
            '<div class=sec><h2>My devices</h2><div id=dv></div><div style="display:flex;gap:8px;flex-wrap:wrap;margin-top:10px"><button class="btn sm" id=dvo type=button>Sign out other devices</button><button class="btn sm danger" id=dva type=button>Sign out everywhere</button></div></div>'
            '<div class=sec><h2>Change my password</h2><form id=pf class=row novalidate><div><label class=f for=op>Current password</label><input type=password id=op autocomplete=current-password></div>'
            '<div><label class=f for=nw>New password</label><input type=password id=nw autocomplete=new-password></div>'
            '<div style="flex:0 0 auto"><button class="btn" id=pb type=submit style="height:46px">Change</button></div></form>'
            '<div class=err id=pe role=alert></div><div class=msg id=pm aria-live=polite></div></div></main>')
    js = _JS_POST + """const $=i=>document.getElementById(i);const E=s=>String(s).replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const when=t=>t?new Date(t*1000).toLocaleString([],{day:'numeric',month:'short',year:'numeric',hour:'2-digit',minute:'2-digit'}):'never';let ME=null,US=[];
function draw(){const admins=US.filter(x=>x.role==='admin').length;$('list').innerHTML=US.map(x=>`<div class=u data-u="${E(x.u)}"><div><div class=n>${E(x.u)}<span class="badge ${x.role}">${x.role==='admin'?'ADMIN':'USER'}</span>${x.u===ME?'<span class="badge me">YOU</span>':''}</div><div class=m>${x.name?E(x.name)+' · ':''}Last active: ${when(x.last_seen)} · ${x.devices} device${x.devices==1?'':'s'}${x.disabled?' · <b style="color:#ffb3b3">TURNED OFF</b>':''}</div></div>
<div class=acts><label class="chk adultviz"><input type=checkbox data-a=adult_viz ${x.adult_viz?'checked':''}> 18+ visuals</label><button class="btn sm" data-a=reset>Reset password</button><button class="btn sm" data-a=role ${x.role==='admin'&&admins<=1?'disabled title="You can\\'t demote the last admin"':''}>${x.role==='admin'?'Make user':'Make admin'}</button>${x.u===ME?'':`<button class="btn sm" data-a=${x.disabled?'enable':'disable'}>${x.disabled?'Turn on':'Turn off'}</button>`}<button class="btn sm" data-a=signout>${x.u===ME?'Sign out my other devices':'Sign out everywhere'}</button><button class="btn sm" data-a=reset_settings>Reset settings</button><button class="btn sm danger" data-a=remove ${x.role==='admin'&&admins<=1?'disabled title="You can\\'t remove the last admin"':''}>Remove</button></div></div>`).join('')}
async function load(){const r=await fetch('/api/auth/me',{credentials:'same-origin'});const m=await r.json();if(!m.user){location.replace('/login?next=/users');return}ME=m.user;
$('who').textContent=`Signed in as ${m.name?m.name+' ('+m.user+')':m.user} · ${m.role}.`;if(document.activeElement!==$('nn'))$('nn').value=m.name||'';devs();if(m.role==='admin'){$('h').textContent='Users';$('adm').hidden=false;const x=await (await fetch('/api/users',{credentials:'same-origin'})).json();US=x.users||[];draw()}}
function flash(e,m,err,msg){$(e).textContent=err||'';$(m).textContent=msg||''}
$('list').addEventListener('change',async ev=>{const c=ev.target.closest('input[data-a=adult_viz]');if(!c)return;const row=c.closest('.u'),u=row.dataset.u,on=c.checked;flash('ae','am');const [r,j]=await post('/api/users',{op:'adult_viz',u,on});if(!r.ok){c.checked=!on;flash('ae','am',j.error||'Failed');return}if(j.users)US=j.users;const x=US.find(y=>y.u===u);if(x)x.adult_viz=on;flash('ae','am','',on?`18+ visuals on for ${u}.`:`18+ visuals off for ${u}.`);if(u===ME){try{localStorage.setItem('msAdultViz',on?'1':'0')}catch(e){}}});
$('list').onclick=async ev=>{const b=ev.target.closest('button[data-a]');if(!b)return;const row=b.closest('.u'),u=row.dataset.u,a=b.dataset.a,x=US.find(y=>y.u===u);flash('ae','am');
if(a==='reset'){if(row.querySelector('.inl'))return;const d=document.createElement('form');d.className='inl';d.innerHTML=`<input type=password placeholder="New password for ${E(u)}" autocomplete=new-password aria-label="New password"><button class="btn sm" type=submit>Save</button><button class="btn sm" type=button data-x>Cancel</button>`;row.append(d);d.querySelector('input').focus();
 d.querySelector('[data-x]').onclick=()=>d.remove();d.onsubmit=async e=>{e.preventDefault();const [r,j]=await post('/api/users',{op:'reset',u,p:d.querySelector('input').value});if(r.ok){d.remove();US=j.users;draw();flash('ae','am','',`Password changed for ${u}. They were signed out everywhere.`)}else flash('ae','am',j.error||'Failed')};return}
if(a==='remove'&&!confirm(`Remove ${u}? They will be signed out everywhere.`))return;
if(a==='reset_settings'&&!confirm(`Reset ${u}'s settings to defaults? Likes, playlists and history are kept.`))return;
const body=a==='remove'?{op:'remove',u}:a==='role'?{op:'role',u,role:x.role==='admin'?'user':'admin'}:{op:a,u};
const [r,j]=await post('/api/users',body);if(!r.ok){flash('ae','am',j.error||'Failed');return}
if(a!=='remove'&&a!=='role'){const x2=await (await fetch('/api/users',{credentials:'same-origin'})).json();US=x2.users||US;draw();flash('ae','am','',{disable:`${u} is turned off and signed out.`,enable:`${u} can sign in again.`,signout:u===ME?'Your other devices were signed out.':`${u} was signed out everywhere.`,reset_settings:`${u}'s settings were reset.`}[a]);return}
if(j.self_removed){location.replace('/login');return}US=j.users;draw();flash('ae','am','',a==='remove'?`${u} removed.`:`${u} is now ${a==='role'&&x.role==='admin'?'a user':'an admin'}.`);if(u===ME)load()};
$('af').onsubmit=async ev=>{ev.preventDefault();flash('ae','am');const u=$('nu').value.trim(),p=$('np').value,role=document.querySelector('input[name=nr]:checked').value;if(!u||!p){flash('ae','am','Enter a username and password.');return}
$('ab').disabled=true;const [r,j]=await post('/api/users',{op:'add',u,p,role});$('ab').disabled=false;if(!r.ok){flash('ae','am',j.error||'Failed');return}$('nu').value='';$('np').value='';US=j.users;draw();flash('ae','am','',`Added ${u.toLowerCase()}. Share the link and their password with them privately.`)};
async function devs(){try{const [,j]=await post('/api/auth/sessions',{});$('dv').innerHTML=(j.sessions||[]).map(d=>`<div class=u><div><div class=n>${E(d.device)}${d.current?'<span class="badge me">THIS DEVICE</span>':''}</div><div class=m>Signed in ${when(d.signed_in)} · last active ${when(d.last_active)}</div></div><div class=acts>${d.current?'':`<button class="btn sm" data-sid="${E(d.id)}">Sign out</button>`}</div></div>`).join('')||'<p class=sub>No devices.</p>'}catch(e){}}
$('dv').onclick=async ev=>{const b=ev.target.closest('button[data-sid]');if(!b)return;const [r]=await post('/api/auth/signout',{sid:b.dataset.sid});if(r.ok)devs()};
$('dvo').onclick=async()=>{const [r,j]=await post('/api/auth/signout',{others:true});if(r.ok){devs();flash('ne','nm','',`Signed out ${j.n} other device${j.n==1?'':'s'}.`)}};
$('dva').onclick=async()=>{if(!confirm('Sign out on every device, including this one?'))return;await post('/api/auth/signout',{});location.replace('/login')};
$('nf').onsubmit=async ev=>{ev.preventDefault();flash('ne','nm');const [r,j]=await post('/api/auth/name',{name:$('nn').value});if(!r.ok){flash('ne','nm',j.error||'Failed');return}flash('ne','nm','','Name saved.');load()};
$('rs').onclick=async()=>{if(!confirm('Reset your settings to defaults on every device? Likes, playlists and history are kept.'))return;const [r]=await post('/api/auth/reset-settings',{});if(r.ok){try{const k=(window.__msBootKeys||[]);}catch(e){}flash('ne','nm','','Settings reset. Your other devices pick it up within a few seconds.')}};
$('pf').onsubmit=async ev=>{ev.preventDefault();flash('pe','pm');$('pb').disabled=true;const [r,j]=await post('/api/auth/password',{old:$('op').value,new:$('nw').value});$('pb').disabled=false;if(!r.ok){flash('pe','pm',j.error||'Failed');return}$('op').value='';$('nw').value='';flash('pe','pm','','Password changed. Other devices were signed out.')};
$('lo').onclick=async()=>{await post('/api/auth/logout',{});location.replace('/login')};load().catch(()=>flash('ae','am','Could not load users.'))"""
    return _shell("Users", body, js, wide=True)

def change_page(u, nxt="/"):
    nx = json.dumps(nxt or "/").replace("<", "\\u003c")
    body = (_brand() + f'<main class=card><h1>Choose a new password</h1><p class=sub>Signed in as <b>{html_esc(u)}</b>. This is a temporary password, so pick your own before you continue.</p>'
            '<form id=f novalidate><label class=f for=op>Temporary password</label><input type=password id=op autocomplete=current-password>'
            f'<label class=f for=nw>New password <span style="font-weight:400">(at least {PW_MIN} characters)</span></label><input type=password id=nw autocomplete=new-password>'
            '<label class=f for=n2>Confirm new password</label><input type=password id=n2 autocomplete=new-password>'
            '<button class="btn pri" id=b type=submit>Save and continue</button><div class=err id=e role=alert aria-live=assertive></div></form></main>'
            '<div class=foot><a href="#" id=lo>Sign out</a></div>')
    js = _JS_POST + f"const NX={nx};" + """const $=i=>document.getElementById(i);$('op').focus();
$('f').onsubmit=async ev=>{ev.preventDefault();const o=$('op').value,n=$('nw').value;if(n!==$('n2').value){$('e').textContent="The two new passwords don't match.";return}
if(n===o){$('e').textContent='Pick a password different from the temporary one.';return}$('b').disabled=true;$('e').textContent='';
try{const [r,j]=await post('/api/auth/password',{old:o,new:n});if(r.ok){location.replace(NX);return}$('e').textContent=j.error||'Could not change the password.'}catch(e){$('e').textContent='Network error. Try again.'}$('b').disabled=false};
$('lo').onclick=async e=>{e.preventDefault();await post('/api/auth/logout',{});location.replace('/login')}"""
    return _shell("New password", body, js)
def html_esc(x): return str(x).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")


# --- recover-20261111 -------------------------------------------------------------------------------------
_RC_HDRS = ("Cf-Connecting-IP", "Cf-Ray", "Cf-Visitor", "Cf-Access-Jwt-Assertion", "X-Forwarded-For", "X-Forwarded-Host",
            "X-Forwarded-Proto", "X-Real-IP", "Forwarded", "Tailscale-Funnel-Request", "Tailscale-User-Login", "Tailscale-Headers-Info", "Via")
def _peer(handler):
    try: return (handler.client_address[0] if handler.client_address else "") or ""
    except Exception: return ""
def _loopback_only(handler):
    """True only for a request made on this device (127.0.0.1 / ::1) with no tunnel or proxy header."""
    if any((handler.headers.get(h) or "").strip() for h in _RC_HDRS): return False
    pe = _peer(handler); pe = pe[7:] if pe.startswith("::ffff:") else pe
    return pe == "::1" or pe.startswith("127.")
def _admin_trusted(handler):
    """Admin sign-in is never locked out from this device, or from the home LAN when MUSIC_TRUST_LAN is on."""
    try:
        if _loopback_only(handler): return True
        f = HOOKS.get("lan_trusted")
        return bool(f and f(handler))
    except Exception: return False
def recover_page():
    adm = STORE.admins()
    opts = "".join(f'<option value="{html_esc(a)}">{html_esc(a)}</option>' for a in adm)
    body = (_brand() + '<main class=card><h1>Unlock the admin account</h1><p class=sub>This page only works on the server device itself. It clears every sign-in lockout, turns the admin account back on and sets a new password.</p>'
            '<form id=f novalidate><label class=f for=u>Admin account</label>' + (f'<select id=u style="width:100%;padding:12px;border-radius:12px;font-size:16px;background:#1c1b20;color:#fff;border:1px solid #ffffff2a">{opts}</select>' if adm else '<div class=err>No admin account exists. Use /setup instead.</div>') +
            f'<label class=f for=p>New password <span style="font-weight:400">(at least {PW_MIN} characters)</span></label><input type=password id=p autocomplete=new-password required>'
            '<label class=f for=p2>Confirm new password</label><input type=password id=p2 autocomplete=new-password required>'
            '<button class="btn pri" id=b type=submit>Unlock and set password</button><div class=err id=e role=alert aria-live=assertive></div></form></main>'
            '<div class=foot>Offline instead: run <b>ms-recover</b> in Termux.</div>')
    js = _JS_POST + """const $=i=>document.getElementById(i);
$('f').onsubmit=async ev=>{ev.preventDefault();const u=$('u')&&$('u').value,p=$('p').value,p2=$('p2').value;if(!u||!p){$('e').textContent='Pick the admin and type a new password.';return}
if(p!==p2){$('e').textContent="The two passwords don't match.";return}$('b').disabled=true;$('e').textContent='';
try{const [r,j]=await post('/api/auth/recover',{u,p,p2});$('p').value='';$('p2').value='';if(r.ok){$('e').style.color='#8ef0a8';$('e').textContent='Done. Lockouts cleared and the admin is on. Sign in with the new password.';setTimeout(()=>location.replace('/login'),1800);return}$('e').textContent=j.error||'Could not unlock.'}catch(e){$('e').textContent='Network error. Try again.'}$('b').disabled=false}"""
    return _shell("Unlock admin", body, js)
def _cli_recover(a):
    """python ms_users.py recover <server_dir> [username] [--password-file F]  (no echo; never prints the password)"""
    import getpass, sys as _s
    root = a[0]; rest = [x for x in a[1:] if not x.startswith("--")]
    st = Store(root); globals()["STORE"] = st
    adm = st.admins()
    if not adm: print("No admin account exists. Open http://127.0.0.1:<port>/setup in a browser on the server machine."); return 1
    u = norm_user(rest[0]) if rest else (adm[0] if len(adm) == 1 else "")
    if not u:
        print("Admins: " + ", ".join(adm)); u = norm_user(input("Admin to unlock: ").strip())
    if u not in adm: print("That account is not an admin."); return 1
    if "--password-file" in a:
        f = a[a.index("--password-file") + 1]; pw = Path(f).read_text(encoding="utf-8").strip(); pw2 = pw
    else:
        pw = getpass.getpass(f"New password for {u} (typing is hidden): "); pw2 = getpass.getpass("Type it again: ")
    if pw != pw2: print("The two passwords don't match. Nothing changed."); return 1
    ok, e = st.recover(u, pw); pw = pw2 = None
    if not ok: print("Not changed: " + str(e)); return 1
    with st.lock:  # stamp so a running server clears its in-memory lockouts on reload
        _atomic_write(st.uf, {"version": 1, "users": st._users(), "unlock_at": time.time()}); st._um = st._mt(st.uf)
    print(f"Unlocked: {u} is on, every lockout is cleared, new password set. Sign in at the app."); return 0

if __name__ == "__main__":
    # CLI: python ms_users.py create-admin <server_dir> <username> <password_file> [--must-change]
    # Reads the password from a file (never argv / stdout). Migrates the shared play history into the new admin.
    import sys as _s
    a = _s.argv[1:]
    if len(a) >= 2 and a[0] == "recover": _s.exit(_cli_recover(a[1:]))  # recover-20261111
    if len(a) >= 4 and a[0] == "create-admin":
        st = Store(a[1]); HOOKS["plays_global"] = Path(a[1]) / "lcache" / "plays" / "plays.json"
        globals()["STORE"] = st
        pwv = Path(a[3]).read_text(encoding="utf-8").strip()
        ok, e = st.create(a[2], pwv, "admin", must_change="--must-change" in a); pwv = None
        if ok:
            try: migrate_to(norm_user(a[2]), None)
            except Exception: pass
        print("created" if ok else f"failed: {e}"); _s.exit(0 if ok else 1)
    print("usage: python ms_users.py create-admin <server_dir> <username> <password_file> [--must-change]"); _s.exit(2)
