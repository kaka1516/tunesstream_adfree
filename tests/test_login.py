"""login-20261110: accounts, sessions, lockout, first-run (LAN only), admin-only users API. Never prints secrets.
Runs a real ThreadingHTTPServer on 127.0.0.1 with a temp users/sessions dir.
"External" requests are simulated with Cloudflare tunnel headers (Cf-Ray + Cf-Connecting-IP).
Run: python tests/test_login.py   (or python -m pytest -q tests/test_login.py)"""
from __future__ import annotations
import importlib.util, sys, json, time, secrets, tempfile, threading, http.client, os
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
spec = importlib.util.spec_from_file_location("music_server_login", ROOT / "music_server.py")
ms = importlib.util.module_from_spec(spec); spec.loader.exec_module(ms)
U = ms._MSU
TMP = Path(tempfile.mkdtemp(prefix="ms_login_test_"))
def fresh():
    import shutil
    for f in TMP.glob("*"):
        shutil.rmtree(f) if f.is_dir() else f.unlink()
    ms.PLAYS_FILE = TMP / "plays_global.json"   # never touch the real shared play history
    U.STORE = U.Store(TMP); U.HOOKS["plays_global"] = ms.PLAYS_FILE; ms._hits.clear()
    ms.OPEN = False; ms.TRUST_LAN = True; ms.CF_TEAM = ""; ms.CF_AUD = ""
    return U.STORE
fresh()
SRV = ms.ThreadingHTTPServer(("127.0.0.1", 0), ms.H); PORT = SRV.server_address[1]
threading.Thread(target=SRV.serve_forever, daemon=True).start()
_n = [0]
def EXT(ip=None, https=True):
    _n[0] += 1
    h = {"Cf-Ray": "t%d" % _n[0], "Cf-Connecting-IP": ip or "203.0.113.%d" % (_n[0] % 250 + 1), "Host": "music.example"}
    if https: h["Cf-Visitor"] = '{"scheme":"https"}'
    return h
class R:
    def __init__(self, st, hd, body): self.status, self.headers, self.body = st, hd, body
    def json(self): return json.loads(self.body or b"{}")
    def cookies(self): return [v for k, v in self.headers if k.lower() == "set-cookie"]
def req(method, path, headers=None, body=None, cookie=None):
    c = http.client.HTTPConnection("127.0.0.1", PORT, timeout=30)
    h = dict(headers or {})
    if cookie: h["Cookie"] = cookie
    if body is not None:
        body = json.dumps(body).encode(); h.setdefault("Content-Type", "application/json")
    c.request(method, path, body=body, headers=h); r = c.getresponse(); b = r.read(); c.close()
    return R(r.status, r.getheaders(), b)
def sess_of(r):
    for v in r.cookies():
        if v.startswith("ms_sess=") and not v.startswith("ms_sess=;"): return v.split(";")[0]
    return None
def pw(): return secrets.token_urlsafe(18)

# ---------------- hashing ----------------
def test_hashing():
    h = U.hash_pw("correct horse battery")
    alg, it, salt, dk = h.split("$")
    assert alg == "pbkdf2_sha256" and int(it) >= 200000
    assert "correct" not in h
    assert U.verify_pw("correct horse battery", h) and not U.verify_pw("correct horse batterY", h) and not U.verify_pw("", h)
    assert U.hash_pw("same") != U.hash_pw("same")  # per-user random salt
    assert not U.verify_pw("x", "garbage") and not U.verify_pw("x", "pbkdf2_sha256$10$AA==$AA==")  # too few iterations rejected

def test_store_never_holds_plaintext():
    st = fresh(); p = pw(); assert st.create("Alice", p, "admin")[0]
    raw = (TMP / "users.json").read_text()
    assert p not in raw and "alice" in raw and "Alice" not in raw
    if os.name != "nt": assert (TMP / "users.json").stat().st_mode & 0o077 == 0
    assert not st.create("alice", pw())[0]               # duplicate (case-insensitive)
    assert not st.create("a b", pw())[0] and not st.create("bob", "short")[0]

# ---------------- first run ----------------
def test_first_run_lan_only():
    fresh()
    assert req("GET", "/setup").status == 200 and b"Create admin account" in req("GET", "/setup").body
    r = req("GET", "/setup", EXT()); assert r.status == 403 and b"only available at home" in r.body
    r = req("POST", "/api/auth/setup", EXT(), {"u": "evil", "p": "x" * 12, "p2": "x" * 12}); assert r.status == 403
    r = req("POST", "/api/auth/setup", {"X-Forwarded-For": "1.2.3.4"}, {"u": "evil", "p": "x" * 12, "p2": "x" * 12}); assert r.status == 403
    r = req("GET", "/", EXT(), cookie=None); assert r.status == 401 and b"isn't set up yet" in r.body
    assert not U.STORE.has_users()
    # LAN client creates the admin
    p = pw(); r = req("POST", "/api/auth/setup", None, {"u": "Alice", "p": p, "p2": p}); assert r.status == 200, r.body
    assert sess_of(r) and U.STORE.get("alice")["role"] == "admin"
    r = req("POST", "/api/auth/setup", None, {"u": "second", "p": p, "p2": p}); assert r.status == 409
    assert req("GET", "/setup").status == 302
    r = req("POST", "/api/auth/setup", None, {"u": "x2", "p": "a" * 10, "p2": "b" * 10})
    assert r.status in (400, 409)

def test_me_reports_setup_state():
    fresh()
    j = req("GET", "/api/auth/me").json(); assert j["setup_needed"] and j["can_setup"] and j["trusted"] and j["user"] is None
    j = req("GET", "/api/auth/me", EXT()).json(); assert j["setup_needed"] and not j["can_setup"] and not j["trusted"]

# ---------------- login + sessions ----------------
def _mk(name="alice", role="admin"):
    p = pw(); assert U.STORE.create(name, p, role)[0]; return p
def login(u, p, keep=True, h=None):
    return req("POST", "/api/auth/login", h or EXT(), {"u": u, "p": p, "keep": keep})

def test_external_needs_login_and_gets_login_page():
    fresh(); _mk()
    r = req("GET", "/", dict(EXT(), Accept="text/html")); assert r.status == 401 and b"Sign in" in r.body and b"Keep me signed in" in r.body
    assert b"checked" in r.body
    r = req("GET", "/api/search?q=x", EXT()); assert r.status == 401 and r.json()["login"] == "/login"
    r = req("GET", "/audio?id=dQw4w9WgXcQ", EXT()); assert r.status == 401
    r = req("POST", "/api/played", EXT(), {"id": "x"}); assert r.status == 401
    assert req("GET", "/health", EXT()).status == 200
    assert req("GET", "/sw.js", EXT()).status == 200
    m = req("GET", "/manifest.webmanifest", EXT()); assert m.status == 200 and m.json()["start_url"] == "/"
    assert req("GET", "/login", EXT()).status == 200

def test_login_wrong_password_and_success():
    fresh(); p = _mk()
    r = login("alice", "nope-nope"); assert r.status == 401 and r.json()["error"] == "Wrong username or password."
    r = login("nobody", "nope-nope"); assert r.status == 401 and r.json()["error"] == "Wrong username or password."
    assert not sess_of(r)
    r = login("ALICE", p); assert r.status == 200 and r.json()["role"] == "admin"
    ck = [c for c in r.cookies() if c.startswith("ms_sess=")][0]
    assert "HttpOnly" in ck and "SameSite=Lax" in ck and "Secure" in ck and "Max-Age=31536000" in ck
    s = sess_of(r)
    raw = (TMP / "sessions.json").read_text(); assert s.split("=", 1)[1] not in raw  # only the token hash is stored
    assert req("GET", "/api/ytdlp", EXT(), cookie=s).status == 200
    assert req("GET", "/api/auth/me", EXT(), cookie=s).json()["user"] == "alice"
    assert req("GET", "/api/ytdlp", EXT(), cookie="ms_sess=" + "A" * 43).status == 401
    assert U.STORE.get("alice")["last_login"]

def test_session_cookie_without_keep_and_over_http():
    fresh(); p = _mk()
    r = login("alice", p, keep=False, h=EXT(https=False)); ck = [c for c in r.cookies() if c.startswith("ms_sess=")][0]
    assert "Max-Age" not in ck and "Secure" not in ck and "HttpOnly" in ck
    s = sess_of(r); assert req("GET", "/api/ytdlp", EXT(), cookie=s).status == 200

def test_sliding_renewal():
    fresh(); p = _mk(); s = sess_of(login("alice", p)); tok = s.split("=", 1)[1]
    h = U._th(tok); U.STORE._sess()[h]["ren"] -= 2 * 86400; U.STORE._sess()[h]["exp"] -= 2 * 86400
    old = U.STORE._sess()[h]["exp"]
    r = req("GET", "/api/ytdlp", EXT(), cookie=s); assert r.status == 200
    assert any(c.startswith("ms_sess=" + tok) and "Max-Age=31536000" in c for c in r.cookies())
    assert U.STORE._sess()[h]["exp"] > old + 86400
    r = req("GET", "/api/ytdlp", EXT(), cookie=s); assert not any(c.startswith("ms_sess=") for c in r.cookies())  # no churn

def test_expired_session_rejected():
    fresh(); p = _mk(); s = sess_of(login("alice", p)); h = U._th(s.split("=", 1)[1])
    U.STORE._sess()[h]["exp"] = time.time() - 1
    r = req("GET", "/api/ytdlp", EXT(), cookie=s); assert r.status == 401 and any(c.startswith("ms_sess=;") for c in r.cookies())

def test_logout():
    fresh(); p = _mk(); s = sess_of(login("alice", p))
    r = req("POST", "/api/auth/logout", EXT(), {}, cookie=s); assert r.status == 200 and any("Max-Age=0" in c for c in r.cookies())
    assert req("GET", "/api/ytdlp", EXT(), cookie=s).status == 401

# ---------------- lockout ----------------
def test_lockout_per_ip_and_user():
    fresh(); p = _mk()
    ip = "198.51.100.7"
    for i in range(10): assert login("alice", "wrong-%d" % i, h=EXT(ip)).status == 401
    r = login("alice", p, h=EXT(ip)); assert r.status == 429 and "Too many attempts" in r.json()["error"]  # correct pw still refused
    r = login("alice", p, h=EXT("198.51.100.8")); assert r.status == 429  # per-username lock applies from another IP too
    # per IP: spraying different usernames from one IP
    fresh(); p = _mk(); ip2 = "198.51.100.9"
    for i in range(10): login("user%d" % i, "wrong-pass", h=EXT(ip2))
    assert login("alice", p, h=EXT(ip2)).status == 429
    assert login("alice", p, h=EXT("198.51.100.10")).status == 200
    # window expiry
    st = U.STORE
    assert st.locked_for("cf:" + ip2, "zzz") > 0 and st.locked_for("cf:" + ip2, "zzz", now=time.time() + U.FAIL_WIN + 1) == 0

def test_success_resets_user_counter():
    fresh(); p = _mk()
    for i in range(9): login("alice", "bad-%d" % i, h=EXT("192.0.2.%d" % (i + 1)))
    assert login("alice", p, h=EXT("192.0.2.50")).status == 200
    assert login("alice", "bad-x", h=EXT("192.0.2.51")).status == 401 and login("alice", p, h=EXT("192.0.2.52")).status == 200

# ---------------- users API ----------------
def test_users_api_admin_only_even_on_lan():
    fresh(); pa = _mk("alice", "admin"); pu = _mk("guest", "user")
    assert req("GET", "/api/users").status == 401                     # LAN keyless is NOT enough
    assert req("POST", "/api/users", None, {"op": "add", "u": "x", "p": pw()}).status == 401
    r = req("GET", "/users", {"Accept": "text/html"}); assert r.status == 401 and b"Sign in" in r.body
    sg = sess_of(login("guest", pu))
    assert req("GET", "/api/users", EXT(), cookie=sg).status == 403
    assert req("POST", "/api/users", EXT(), {"op": "role", "u": "guest", "role": "admin"}, cookie=sg).status == 403
    assert req("GET", "/users", EXT(), cookie=sg).status == 200      # own-account page (change password)
    sa = sess_of(login("alice", pa))
    j = req("GET", "/api/users", EXT(), cookie=sa).json(); assert [x["u"] for x in j["users"]] == ["guest", "alice"]
    assert all("hash" not in x for x in j["users"]) and "pbkdf2" not in json.dumps(j)
    assert req("GET", "/users", EXT(), cookie=sa).status == 200
    # key still works for the app, but never for the users API
    assert req("GET", "/api/ytdlp?k=" + ms.KEY, EXT()).status == 200
    assert req("GET", "/api/users?k=" + ms.KEY, EXT()).status == 401

def test_users_crud_and_last_admin():
    fresh(); pa = _mk(); sa = sess_of(login("alice", pa)); P = lambda b: req("POST", "/api/users", EXT(), b, cookie=sa)
    np = pw(); r = P({"op": "add", "u": "Mom", "p": np}); assert r.status == 200 and U.STORE.get("mom")["role"] == "user"
    assert P({"op": "add", "u": "mom", "p": pw()}).status == 400
    assert P({"op": "add", "u": "kid", "p": "short"}).status == 400
    assert P({"op": "remove", "u": "alice"}).status == 400              # last admin
    assert P({"op": "role", "u": "alice", "role": "user"}).status == 400
    assert P({"op": "role", "u": "mom", "role": "admin"}).status == 200 and U.STORE.get("mom")["role"] == "admin"
    assert P({"op": "role", "u": "mom", "role": "user"}).status == 200
    assert P({"op": "bogus", "u": "mom"}).status == 400

def test_remove_and_reset_invalidate_sessions():
    fresh(); pa = _mk(); sa = sess_of(login("alice", pa)); P = lambda b: req("POST", "/api/users", EXT(), b, cookie=sa)
    pm = pw(); P({"op": "add", "u": "mom", "p": pm}); sm = sess_of(login("mom", pm)); sm2 = sess_of(login("mom", pm))
    assert req("GET", "/api/ytdlp", EXT(), cookie=sm).status == 200
    pm2 = pw(); assert P({"op": "reset", "u": "mom", "p": pm2}).status == 200
    assert req("GET", "/api/ytdlp", EXT(), cookie=sm).status == 401 and req("GET", "/api/ytdlp", EXT(), cookie=sm2).status == 401
    assert login("mom", pm).status == 401 and login("mom", pm2).status == 200
    sm3 = sess_of(login("mom", pm2)); assert P({"op": "remove", "u": "mom"}).status == 200
    assert req("GET", "/api/ytdlp", EXT(), cookie=sm3).status == 401 and U.STORE.get("mom") is None
    assert "mom" not in (TMP / "sessions.json").read_text()
    assert req("GET", "/api/ytdlp", EXT(), cookie=sa).status == 200     # admin unaffected

def test_change_own_password():
    fresh(); pa = _mk(); pu = _mk("guest", "user"); s1 = sess_of(login("guest", pu)); s2 = sess_of(login("guest", pu))
    assert req("POST", "/api/auth/password", EXT(), {"old": "wrong-one", "new": pw()}, cookie=s1).status == 401
    assert req("POST", "/api/auth/password", EXT(), {"old": pu, "new": "short"}, cookie=s1).status == 400
    n = pw(); r = req("POST", "/api/auth/password", EXT(), {"old": pu, "new": n}, cookie=s1); assert r.status == 200
    s1b = sess_of(r); assert s1b and req("GET", "/api/ytdlp", EXT(), cookie=s1b).status == 200   # this browser stays in
    assert req("GET", "/api/ytdlp", EXT(), cookie=s1).status == 401 and req("GET", "/api/ytdlp", EXT(), cookie=s2).status == 401
    assert login("guest", n).status == 200
    assert req("POST", "/api/auth/password", EXT(), {"old": n, "new": pw()}).status == 401   # no session

def test_csrf_guards():
    fresh(); p = _mk()
    r = req("POST", "/api/auth/login", dict(EXT(), Origin="https://evil.example"), {"u": "alice", "p": p}); assert r.status == 403
    r = req("POST", "/api/auth/login", dict(EXT(), Origin="https://music.example"), {"u": "alice", "p": p}); assert r.status == 200
    c = http.client.HTTPConnection("127.0.0.1", PORT, timeout=10)
    c.request("POST", "/api/auth/login", body=b"u=alice", headers=dict(EXT(), **{"Content-Type": "application/x-www-form-urlencoded"}))
    assert c.getresponse().status == 415

def test_lan_still_keyless_and_key_fallback():
    fresh(); _mk()
    assert req("GET", "/api/ytdlp").status == 200                     # loopback / LAN with MUSIC_TRUST_LAN=1
    r = req("GET", "/", {"Accept": "text/html"}); assert r.status == 200 and b"<html" in r.body[:400].lower()  # the player itself, no login
    assert req("GET", "/?k=" + ms.KEY, dict(EXT(), Accept="text/html")).status == 200
    r = req("GET", "/api/ytdlp?k=" + ms.KEY, EXT()); ac = [c for c in r.cookies() if c.startswith("ms_auth=")]
    assert r.status == 200 and ac
    assert req("GET", "/api/ytdlp", EXT(), cookie=ac[0].split(";")[0]).status == 200   # old 1-year key cookie still works

def test_is_local_classification():
    class Hd(dict):
        def get(self, k, d=None):
            for kk, v in self.items():
                if kk.lower() == k.lower(): return v
            return d
    class X: pass
    def mk(peer, h=None): x = X(); x.client_address = (peer, 1); x.headers = Hd(h or {}); return x
    f = ms._is_local_client
    assert f(mk("10.0.0.210")) and f(mk("100.101.2.3")) and f(mk("127.0.0.1"))
    assert not f(mk("8.8.8.8")) and not f(mk("127.0.0.1", {"Cf-Ray": "a"})) and not f(mk("127.0.0.1", {"Tailscale-Funnel-Request": "?1"}))
    assert not f(mk("10.0.0.5", {"X-Forwarded-For": "1.1.1.1"}))
    ms.TRUST_LAN = False; assert f(mk("10.0.0.210")); ms.TRUST_LAN = True   # setup gating is independent of TRUST_LAN

def test_safe_next():
    s = U._safe_next
    assert s("/users") == "/users" and s("/?u=x") == "/?u=x" and s("//evil.com") == "/" and s("https://evil.com") == "/"
    assert s("/login?next=/") == "/" and s("/\\evil") == "/" and s(None) == "/"

# ---------------- per-user state (login-state-20261110) ----------------
import re as _re
def _boot(body):
    m = _re.search(rb"window.__msBoot=(\{.*?\})</script>", body); assert m, "no boot"
    return json.loads(m.group(1))
def _plays_tmp():
    ms.PLAYS_FILE = TMP / "plays_global.json"; U.HOOKS["plays_global"] = ms.PLAYS_FILE
def test_state_isolated_per_user():
    fresh(); pa = _mk("alice", "admin"); pb = _mk("bob", "user")
    sa = sess_of(login("alice", pa)); sb = sess_of(login("bob", pb))
    r = req("POST", "/api/state", EXT(), {"set": {"lk": '[{"id":"AAAAAAAAAAA"}]', "theme": "mint", "evil": "x"}, "del": []}, cookie=sa)
    assert r.status == 200 and r.json()["rev"] == 1
    ja = req("GET", "/api/state", EXT(), cookie=sa).json(); jb = req("GET", "/api/state", EXT(), cookie=sb).json()
    assert ja["user"] == "alice" and ja["ls"]["theme"] == "mint" and "evil" not in ja["ls"]
    assert jb["user"] == "bob" and jb["ls"] == {} and "AAAAAAAAAAA" not in json.dumps(jb)
    assert req("GET", "/api/state?since=1", EXT(), cookie=sa).json().get("ls") is None   # unchanged -> no payload
    assert req("POST", "/api/state", EXT(), {"set": {"theme": "x"}}).status == 401        # no session
    assert req("GET", "/api/state").json() == {"user": None}                              # LAN keyless: shared profile, no sync
    assert req("POST", "/api/state", EXT(), {"del": ["theme"]}, cookie=sa).json()["rev"] == 2
    assert "theme" not in req("GET", "/api/state", EXT(), cookie=sa).json()["ls"]
    f = TMP / "user_data" / "alice.json"; assert f.exists()
    if os.name != "nt": assert f.stat().st_mode & 0o077 == 0
def test_state_now_playing_and_limits():
    fresh(); pa = _mk(); sa = sess_of(login("alice", pa))
    n = {"id": "dQw4w9WgXcQ", "title": "Song <b>", "channel": "Ch", "dur": 213, "t": 95.4, "playing": False, "dev": "dPC1"}
    assert req("POST", "/api/state", EXT(), {"now": n}, cookie=sa).status == 200
    j = req("GET", "/api/state", EXT(), cookie=sa).json()["now"]
    assert j["id"] == n["id"] and j["t"] == 95.4 and j["dev"] == "dPC1" and j["ts"] > 0
    req("POST", "/api/state", EXT(), {"now": {"id": "../../etc", "t": 1}}, cookie=sa)
    assert req("GET", "/api/state", EXT(), cookie=sa).json()["now"]["id"] == n["id"]          # bad id ignored
    big = "x" * (U.KEY_MAX + 1)
    assert req("POST", "/api/state", EXT(), {"set": {"h": big}}, cookie=sa).status == 413
def test_boot_injected_only_for_own_user():
    fresh(); pa = _mk("alice", "admin"); pb = _mk("bob", "user")
    sa = sess_of(login("alice", pa)); sb = sess_of(login("bob", pb))
    req("POST", "/api/state", EXT(), {"set": {"lk": "ALICE_SECRET_LIKES"}, "now": {"id": "dQw4w9WgXcQ", "t": 30, "dev": "dA"}}, cookie=sa)
    ra = req("GET", "/", dict(EXT(), Accept="text/html"), cookie=sa); ba = _boot(ra.body)
    assert ra.status == 200 and ba["user"] == "alice" and ba["state"]["ls"]["lk"] == "ALICE_SECRET_LIKES" and ba["state"]["now"]["t"] == 30
    rb = req("GET", "/", dict(EXT(), Accept="text/html"), cookie=sb); bb = _boot(rb.body)
    assert bb["user"] == "bob" and b"ALICE_SECRET_LIKES" not in rb.body
    rl = req("GET", "/", {"Accept": "text/html"}); bl = _boot(rl.body)
    assert bl["user"] is None and "state" not in bl and b"ALICE_SECRET_LIKES" not in rl.body
    assert "q" in bl["keys"] and "lk" in bl["keys"]
    assert req("GET", "/", dict(EXT(), Accept="text/html"), cookie=sa).body.index(b"__msBoot") < req("GET", "/", dict(EXT(), Accept="text/html"), cookie=sa).body.index(b"<script type=importmap")
def test_state_removed_with_user():
    fresh(); pa = _mk(); sa = sess_of(login("alice", pa)); P = lambda b: req("POST", "/api/users", EXT(), b, cookie=sa)
    pm = pw(); P({"op": "add", "u": "mom", "p": pm}); sm = sess_of(login("mom", pm))
    req("POST", "/api/state", EXT(), {"set": {"lk": "MOMS"}}, cookie=sm); assert (TMP / "user_data" / "mom.json").exists()
    P({"op": "remove", "u": "mom"}); assert not (TMP / "user_data" / "mom.json").exists()
    pm2 = pw(); P({"op": "add", "u": "mom", "p": pm2}); sm2 = sess_of(login("mom", pm2))
    assert req("GET", "/api/state", EXT(), cookie=sm2).json()["ls"] == {}
def test_first_admin_migration():
    fresh(); _plays_tmp()
    ms.PLAYS_FILE.write_text(json.dumps({"counts": {"dQw4w9WgXcQ": 7}, "recent": [], "meta": {}}))
    p = pw(); ls = {"lk": "OLD_LIKES", "lpl": "OLD_PLAYLISTS", "h": "OLD_HISTORY", "theme": "mint", "junk": "nope"}
    r = req("POST", "/api/auth/setup", None, {"u": "alice", "p": p, "p2": p, "ls": ls}); assert r.status == 200
    st = U.STORE.get_state("alice")["ls"]; assert st == {"lk": "OLD_LIKES", "lpl": "OLD_PLAYLISTS", "h": "OLD_HISTORY", "theme": "mint"}
    assert json.loads((TMP / "user_data" / "alice.plays.json").read_text())["counts"]["dQw4w9WgXcQ"] == 7
    assert json.loads(ms.PLAYS_FILE.read_text())["counts"]["dQw4w9WgXcQ"] == 7          # shared LAN profile keeps its copy
def test_play_history_per_user():
    fresh(); _plays_tmp(); pa = _mk("alice", "admin"); sa = sess_of(login("alice", pa))
    assert req("GET", "/api/played?id=dQw4w9WgXcQ&title=A", EXT(), cookie=sa).status == 200
    assert req("GET", "/api/played?id=9bZkp7q19f0&title=L").status == 200                   # LAN keyless -> shared
    pa_ = json.loads((TMP / "user_data" / "alice.plays.json").read_text())["counts"]; g = json.loads(ms.PLAYS_FILE.read_text())["counts"]
    assert pa_ == {"dQw4w9WgXcQ": 1} and g == {"9bZkp7q19f0": 1}

# ---------------- temporary admin password (must change) + key-holder setup ----------------
def test_must_change_password_flow():
    fresh(); tmp = pw(); assert U.STORE.create("admin", tmp, "admin", must_change=True)[0]
    r = login("admin", tmp); assert r.status == 200 and r.json()["must_change"] is True; s = sess_of(r)
    r = req("GET", "/", dict(EXT(), Accept="text/html"), cookie=s); assert r.status == 401 and b"Choose a new password" in r.body
    assert req("GET", "/api/ytdlp", EXT(), cookie=s).status == 401
    assert req("GET", "/api/users", EXT(), cookie=s).status == 403 and req("POST", "/api/users", EXT(), {"op": "add", "u": "x", "p": pw()}, cookie=s).status == 403
    assert req("GET", "/api/auth/me", EXT(), cookie=s).json()["must_change"] is True
    assert req("POST", "/api/auth/password", EXT(), {"old": "nope-nope", "new": pw()}, cookie=s).status == 401
    n = pw(); r = req("POST", "/api/auth/password", EXT(), {"old": tmp, "new": n}, cookie=s); assert r.status == 200
    s2 = sess_of(r); assert req("GET", "/api/ytdlp", EXT(), cookie=s2).status == 200 and req("GET", "/api/users", EXT(), cookie=s2).status == 200
    assert "mcp" not in json.loads((TMP / "users.json").read_text())["users"]["admin"]
    assert login("admin", tmp).status == 401 and login("admin", n).status == 200
def test_cli_create_admin():
    fresh(); f = TMP / "pwfile.txt"; tmp = pw(); f.write_text(tmp)
    import subprocess
    r = subprocess.run([sys.executable, str(ROOT / "ms_users.py"), "create-admin", str(TMP), "admin", str(f), "--must-change"], capture_output=True, text=True)
    assert r.returncode == 0 and r.stdout.strip() == "created" and tmp not in r.stdout + r.stderr
    f.unlink(); U.STORE = U.Store(TMP)
    x = U.STORE.get("admin"); assert x["role"] == "admin" and x["mcp"] is True and tmp not in (TMP / "users.json").read_text()
    assert login("admin", tmp).json()["must_change"] is True
def test_setup_allowed_for_key_holders():
    fresh()
    assert req("GET", "/setup", EXT()).status == 403
    assert req("GET", "/setup?k=" + ms.KEY, EXT()).status == 200
    ac = [c for c in req("GET", "/api/ytdlp?k=" + ms.KEY, EXT()).cookies() if c.startswith("ms_auth=")][0].split(";")[0]
    assert req("GET", "/setup", EXT(), cookie=ac).status == 200
    p = pw(); assert req("POST", "/api/auth/setup", EXT(), {"u": "boss", "p": p, "p2": p}, cookie=ac).status == 200

if __name__ == "__main__":
    n = 0
    for name, fn in list(globals().items()):
        if name.startswith("test_") and callable(fn): fn(); n += 1; print("ok", name)
    print(f"{n} passed")
    SRV.shutdown()
    import shutil; shutil.rmtree(TMP, ignore_errors=True)
