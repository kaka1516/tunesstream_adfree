"""listen-20261114: shared control, 10 permanent rooms, chat, guest cookie isolation, signaling inbox.
Never prints MUSIC_KEY or passwords. Run: python -m pytest -q tests/test_together.py
"""
from __future__ import annotations
import importlib.util, sys, json, time, secrets, tempfile, threading, http.client, os
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
spec = importlib.util.spec_from_file_location("music_server_together", ROOT / "music_server.py")
ms = importlib.util.module_from_spec(spec); spec.loader.exec_module(ms)
U = ms._MSU
TMP = Path(tempfile.mkdtemp(prefix="ms_together_test_"))

def fresh():
    import shutil
    for f in TMP.glob("*"):
        shutil.rmtree(f) if f.is_dir() else f.unlink()
    ms.PLAYS_FILE = TMP / "plays_global.json"
    U.STORE = U.Store(TMP); U.HOOKS["plays_global"] = ms.PLAYS_FILE; ms._hits.clear()
    ms.OPEN = False; ms.TRUST_LAN = True; ms.CF_TEAM = ""; ms.CF_AUD = ""
    ms._ROOMS_F = TMP / "rooms.json"; ms._rooms_fl = None
    ms.ROOMS.clear()
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
    raw = None
    if body is not None:
        raw = json.dumps(body).encode(); h.setdefault("Content-Type", "application/json")
    c.request(method, path, body=raw, headers=h); r = c.getresponse(); b = r.read(); c.close()
    return R(r.status, r.getheaders(), b)
def sess_of(r):
    for v in r.cookies():
        if v.startswith("ms_sess=") and not v.startswith("ms_sess=;"): return v.split(";", 1)[0]
    return None
def guest_of(r, prior=None):
    found = None
    for v in r.cookies():
        if v.startswith("ms_guest="):
            found = v.split(";", 1)[0]
            if found == "ms_guest=" or "Max-Age=0" in v:
                return None
    return found or prior
def pw():
    return secrets.token_urlsafe(18)
def _mk(name="alice", role="admin"):
    p = pw(); assert U.STORE.create(name, p, role)[0]; return p
def login(u, p, h=None):
    return req("POST", "/api/auth/login", h or EXT(), {"u": u, "p": p, "keep": True})

def test_ten_permanent_rooms_public_list():
    fresh(); ms._hits.clear()
    r = req("GET", "/api/room?op=list", EXT())
    assert r.status == 200, r.body
    j = r.json(); assert j.get("ok") and j.get("shared") == 1
    codes = [x["r"] for x in j["rooms"]]
    assert codes[:10] == [c for c, _n in ms._PERM_ROOMS]
    assert all(x.get("perm") == 1 for x in j["rooms"][:10])
    assert any(x["name"] == "Main Stage" for x in j["rooms"])
    assert "hk" not in json.dumps(j)

def test_slash_still_requires_login_listen_is_public():
    fresh(); _mk()
    r = req("GET", "/", dict(EXT(), Accept="text/html"))
    assert r.status == 401 and b"Sign in" in r.body
    r = req("GET", "/?room=MAIN", dict(EXT(), Accept="text/html"))
    assert r.status == 302
    loc = dict((k.lower(), v) for k, v in r.headers).get("location", "")
    assert loc == "/listen?room=MAIN"
    r = req("GET", "/listen?room=MAIN", dict(EXT(), Accept="text/html"))
    assert r.status == 200 and b"__msListen" in r.body and b"ms-guest" in r.body
    assert b"Listen together" in r.body and b"id=rmp" in r.body

def test_shared_control_last_writer_wins():
    fresh(); pa = _mk("alice", "admin"); pb = _mk("bob", "user")
    sa, sb = sess_of(login("alice", pa)), sess_of(login("bob", pb))
    a = req("POST", "/api/room", EXT(), {"op": "set", "r": "MAIN", "id": "dQw4w9WgXcQ", "t": 11, "p": 1, "title": "A", "channel": "X"}, cookie=sa)
    assert a.status == 200 and a.json().get("ok") == 1 and a.json()["v"] == 1
    b = req("POST", "/api/room", EXT(), {"op": "set", "r": "MAIN", "id": "oHg5SJYRHA0", "t": 4, "p": 0, "title": "B", "channel": "Y"}, cookie=sb)
    assert b.json()["v"] == 2 and b.json()["by"].lower() == "bob"
    g = req("GET", "/api/room?op=get&r=MAIN", EXT(), cookie=sa).json()
    assert g["id"] == "oHg5SJYRHA0" and g["v"] == 2 and g["p"] is False and g["title"] == "B"
    assert "bob" in (g.get("members") or []) and "alice" in (g.get("members") or [])

def test_set_without_host_key():
    fresh(); p = _mk(); s = sess_of(login("alice", p))
    r = req("GET", "/api/room?op=set&r=CHILL&id=dQw4w9WgXcQ&t=1&p=1&title=x", EXT(), cookie=s)
    assert r.status == 200 and r.json().get("ok") == 1

def test_guest_join_chat_and_isolation():
    fresh(); _mk()
    assert req("GET", "/api/search?q=x", EXT()).status == 401
    r = req("POST", "/api/room", EXT("198.51.100.20"), {"op": "guest", "r": "NIGHT", "name": "Sam"})
    assert r.status == 200 and r.json().get("ok") == 1 and r.json()["r"] == "NIGHT"
    ck = [c for c in r.cookies() if c.startswith("ms_guest=")][0]
    assert "HttpOnly" in ck and "SameSite=Lax" in ck and "Secure" in ck
    g = guest_of(r)
    # guest can control and chat in NIGHT
    s = req("POST", "/api/room", EXT("198.51.100.20"), {"op": "set", "r": "NIGHT", "id": "dQw4w9WgXcQ", "t": 3, "p": 1, "title": "Song", "channel": "Ch"}, cookie=g)
    assert s.json().get("ok") == 1
    c = req("POST", "/api/room", EXT("198.51.100.20"), {"op": "chat", "r": "NIGHT", "m": "hello <script>alert(1)</script>"}, cookie=g)
    assert c.json().get("ok") == 1
    got = req("GET", "/api/room?op=get&r=NIGHT", EXT("198.51.100.20"), cookie=g).json()
    assert got["id"] == "dQw4w9WgXcQ" and any("<script>" in (m.get("m") or "") for m in got["chat"])
    assert got["chat"][-1]["u"] == "Sam"
    # cannot touch other room
    other = req("POST", "/api/room", EXT("198.51.100.20"), {"op": "set", "r": "MAIN", "id": "oHg5SJYRHA0", "t": 1, "p": 1, "title": "nope"}, cookie=g)
    assert other.json().get("error") == "join first"
    # cannot create private room
    assert req("POST", "/api/room", EXT("198.51.100.20"), {"op": "new"}, cookie=g).json().get("error") == "login required"
    # no library / search / admin / settings
    stt = req("GET", "/api/state", dict(EXT("198.51.100.20"), Accept="application/json"), cookie=g)
    assert stt.status == 200 and not stt.json().get("user")
    for path in ("/api/search?q=x", "/api/home", "/api/radio?id=dQw4w9WgXcQ", "/api/users", "/api/shorts",
                 "/api/similar?t=a", "/api/import?t=x", "/api/stats", "/"):
        st = req("GET", path, dict(EXT("198.51.100.20"), Accept="application/json"), cookie=g).status
        assert st in (401, 403), path + " " + str(st)
    # cannot stream a track that is not the room's current/recent id
    assert req("GET", "/audio?id=oHg5SJYRHA0", EXT("198.51.100.20"), cookie=g).status == 401
    assert req("GET", "/art?id=oHg5SJYRHA0", EXT("198.51.100.20"), cookie=g).status == 401
    # allowed id is gated true (do not fetch media in this test)
    assert ms._guest_allowed(_hdr(g, "/audio?id=dQw4w9WgXcQ", "198.51.100.20"), "/audio", {"id": "dQw4w9WgXcQ"})
    assert not ms._guest_allowed(_hdr(g, "/audio?id=oHg5SJYRHA0", "198.51.100.20"), "/audio", {"id": "oHg5SJYRHA0"})

def _hdr(cookie, path, ip):
    inst = ms.H.__new__(ms.H)
    class Hdr(dict):
        def get(self, k, default=None):
            for kk, v in self.items():
                if kk.lower() == k.lower(): return v
            return default
    inst.headers = Hdr({"Cookie": cookie, **EXT(ip)})
    inst.path = path; inst.command = "GET"; inst.client_address = ("127.0.0.1", 1)
    return inst

def test_guest_leave_clears_cookie_and_empty_name_rejected():
    fresh()
    assert req("POST", "/api/room", EXT(), {"op": "guest", "r": "MAIN", "name": "x"}).json().get("error") == "name required"
    r = req("POST", "/api/room", EXT(), {"op": "guest", "r": "MAIN", "name": "Riley"})
    g = guest_of(r)
    lv = req("POST", "/api/room", EXT(), {"op": "leave", "r": "MAIN"}, cookie=g)
    assert lv.json().get("left") == 1
    assert any("ms_guest=" in c and "Max-Age=0" in c for c in lv.cookies())
    after = req("POST", "/api/room", EXT(), {"op": "set", "r": "MAIN", "id": "dQw4w9WgXcQ", "t": 1, "p": 1}, cookie=g)
    assert after.status in (200, 401) and after.json().get("error") in ("join first", "login required")

def test_permanent_rooms_do_not_expire_adhoc_does():
    fresh(); p = _mk(); s = sess_of(login("alice", p))
    n = req("POST", "/api/room", EXT(), {"op": "new"}, cookie=s).json()
    assert n.get("r") and n.get("hk")
    code = n["r"]
    R = json.loads(ms._ROOMS_F.read_text())
    R["MAIN"]["ts"] = 1; R["MAIN"]["n"] = {}
    R[code]["ts"] = 1; R[code]["n"] = {}
    ms._ROOMS_F.write_text(json.dumps(R))
    lst = req("GET", "/api/room?op=list", EXT(), cookie=s).json()
    codes = [x["r"] for x in lst["rooms"]]
    assert "MAIN" in codes and code not in codes

def test_chat_rate_limit_and_signaling_inbox():
    fresh(); p = _mk(); s = sess_of(login("alice", p)); ms._hits.clear()
    ip = EXT("198.51.100.40")
    last = None
    hits = 0
    for i in range(12):
        last = req("POST", "/api/room", ip, {"op": "chat", "r": "BEATS", "m": "msg-%d" % i}, cookie=s)
        if last.json().get("error") == "slow down":
            hits += 1
            break
    assert hits == 1 and last.json()["error"] == "slow down"
    ms._hits.clear()
    pa = _mk("cara", "user"); sa = sess_of(login("cara", pa))
    # alice offers to cara's member id after both get
    ga = req("GET", "/api/room?op=get&r=FOCUS&vc=1", ip, cookie=s).json()
    gc = req("GET", "/api/room?op=get&r=FOCUS&vc=1", EXT("198.51.100.41"), cookie=sa).json()
    assert "alice" in ga["members"] or "cara" in gc["members"]
    # find cara id from voice after get - voice lists ids. Use set from a known mid by posting sig to the other.
    # Send a signal addressed to a fake id, then get as that... easier: use who ids from a second get after listing isn't ids.
    # Post offer to "uCara-like": get doesn't reveal ids in public list, but voice does.
    voice = set(ga.get("voice") or []) | set(gc.get("voice") or [])
    # If voice empty, still post and pull
    to = [x for x in (gc.get("voice") or ga.get("voice") or ["x"]) if x][0]
    # alice -> to
    sig = req("POST", "/api/room", ip, {"op": "sig", "r": "FOCUS", "to": to if to != "ualice" else "ucara", "typ": "offer", "data": "v=0 FAKE_SDP"}, cookie=s)
    assert sig.json().get("ok") == 1
    # cara should receive if to matches her id
    mid_c = None
    # issue get as cara; if we guessed wrong, still ok= inbox mechanics: send to exact cara id
    # Recover cara id: touch via set and inspect file
    store = json.loads(ms._ROOMS_F.read_text())
    ids = list((store["FOCUS"].get("n") or {}).keys())
    assert len(ids) >= 2
    cara_id = [i for i in ids if i != [j for j in ids if j.startswith("u")][0] or True]
    # pick the non-alice id
    alice_id = [i for i in ids if "alice" in ((store["FOCUS"]["n"][i] or {}).get("u","").lower() if isinstance(store["FOCUS"]["n"][i], dict) else "")][0]
    cara_id = [i for i in ids if i != alice_id][0]
    req("POST", "/api/room", ip, {"op": "sig", "r": "FOCUS", "to": cara_id, "typ": "offer", "data": "v=0 OFFER"}, cookie=s)
    got = req("GET", "/api/room?op=get&r=FOCUS&vc=1", EXT("198.51.100.41"), cookie=sa).json()
    assert any(s.get("typ") == "offer" and s.get("data") == "v=0 OFFER" for s in got.get("sig") or [])
    # delivered signals are popped
    got2 = req("GET", "/api/room?op=get&r=FOCUS&vc=1", EXT("198.51.100.41"), cookie=sa).json()
    assert not any(s.get("data") == "v=0 OFFER" for s in got2.get("sig") or [])

def test_guest_name_sanitized():
    fresh()
    r = req("POST", "/api/room", EXT(), {"op": "guest", "r": "PARTY", "name": "<b>Eve</b>"})
    # angle brackets stripped; remaining may be too short or "bEve/b" -> "bEve/b"? < > stripped => "bEve/b"
    j = r.json()
    assert "error" not in j or j.get("ok") == 1
    if j.get("ok"):
        assert "<" not in j.get("n","") and ">" not in j.get("n","")
