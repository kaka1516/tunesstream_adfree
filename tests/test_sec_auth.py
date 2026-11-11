"""sec-20261110: MUSIC_TRUST_LAN / Cloudflare Access JWT / strict /cmd / Secure cookie. Never prints MUSIC_KEY.
Run: python -m pytest -q tests/test_sec_auth.py   (or: python tests/test_sec_auth.py)"""
from __future__ import annotations
import importlib.util, sys, json, base64, hashlib, random, time
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
spec = importlib.util.spec_from_file_location("music_server_sec", ROOT / "music_server.py")
ms = importlib.util.module_from_spec(spec); spec.loader.exec_module(ms)
KEY = ms.KEY
# login-20261110: unauthenticated API calls now answer 401 JSON (login required) instead of 403; /cmd stays 403.
DENY = 401

# ---------- tiny deterministic RSA-2048 for signing test JWTs (pure python) ----------
def _isprime(n, rnd):
    if n < 2: return False
    for p in (2, 3, 5, 7, 11, 13, 17, 19, 23, 29, 31, 37):
        if n % p == 0: return n == p
    d, r = n - 1, 0
    while d % 2 == 0: d //= 2; r += 1
    for _ in range(24):
        x = pow(rnd.randrange(2, n - 2), d, n)
        if x in (1, n - 1): continue
        for _ in range(r - 1):
            x = pow(x, 2, n)
            if x == n - 1: break
        else: return False
    return True
def _prime(bits, rnd):
    while True:
        c = rnd.getrandbits(bits) | (1 << (bits - 1)) | (1 << (bits - 2)) | 1
        if _isprime(c, rnd): return c
_rnd = random.Random(20261110)
E = 65537
while True:
    P, Q = _prime(1024, _rnd), _prime(1024, _rnd)
    N = P * Q; PHI = (P - 1) * (Q - 1)
    if N.bit_length() == 2048 and PHI % E: break
D = pow(E, -1, PHI)
def _b64u(b): return base64.urlsafe_b64encode(b).rstrip(b"=").decode()
def sign(claims, kid="k1", alg="RS256", d=D):
    h = _b64u(json.dumps({"alg": alg, "kid": kid, "typ": "JWT"}).encode()); p = _b64u(json.dumps(claims).encode())
    t = bytes.fromhex("3031300d060960864801650304020105000420") + hashlib.sha256(f"{h}.{p}".encode()).digest()
    em = b"\x00\x01" + b"\xff" * (256 - len(t) - 3) + b"\x00" + t
    s = pow(int.from_bytes(em, "big"), d, N).to_bytes(256, "big")
    return f"{h}.{p}.{_b64u(s)}"
TEAM, AUD = "unit-team", "aud-123"
KEYS = {"k1": (N, E)}
def claims(**kw):
    now = int(time.time())
    c = {"aud": [AUD], "iss": f"https://{TEAM}.cloudflareaccess.com", "exp": now + 600, "iat": now, "nbf": now - 5, "email": "x@example.com"}
    c.update(kw); return c

class _Hdrs(dict):
    def get(self, k, default=None):
        for kk, v in self.items():
            if kk.lower() == k.lower(): return v
        return default

def _inst(peer="10.0.0.210", headers=None, path="/api/ytdlp"):
    inst = ms.H.__new__(ms.H)
    inst.client_address = (peer, 1)
    inst.headers = _Hdrs(headers or {})
    inst.path = path; inst.command = "GET"; inst._sent = None
    def send(code, body, ctype="text/plain"): inst._sent = (code, body)
    inst.send = send
    return inst

def _get(peer, headers=None, path="/api/ytdlp"):
    ms._hits.clear()
    i = _inst(peer, headers, path); ok = i.guard()
    assert ok is True
    i.do_GET()
    return i._sent[0]

def _setup(trust=True, team="", aud=""):
    ms.OPEN = False; ms.TRUST_LAN = trust; ms.CF_TEAM = team; ms.CF_AUD = aud
    ms._CF_OK.clear(); ms._CFK.update(keys=dict(KEYS), ts=time.time() + 10 ** 9)

# ---------------- network trust ----------------
def test_peer_classification():
    f = ms._peer_trusted_ip
    assert f("10.0.0.210") == "lan" and f("10.1.2.3") == "lan" and f("172.16.0.1") == "lan" and f("172.31.255.1") == "lan"
    assert f("100.64.0.1") == "lan" and f("100.127.255.254") == "lan"
    assert f("::ffff:10.0.0.5") == "lan" and f("127.0.0.1") == "loopback" and f("::1") == "loopback"
    for bad in ("8.8.8.8", "172.32.0.1", "100.128.0.1", "203.0.113.9", "", "garbage", "2001:db8::1"):
        assert f(bad) is None, bad

def test_trust_lan_keyless_allowed():
    _setup(True)
    assert _get("10.0.0.210") == 200
    assert _get("100.102.1.2") == 200
    assert _get("127.0.0.1") == 200            # local, no proxy headers

def test_public_and_proxied_need_key():
    _setup(True)
    assert _get("8.8.8.8") == DENY
    assert _get("127.0.0.1", {"Tailscale-Funnel-Request": "?1", "X-Forwarded-For": "203.0.113.9"}) == DENY  # Funnel
    assert _get("127.0.0.1", {"X-Forwarded-For": "10.0.0.5"}) == DENY  # spoofed XFF never trusted
    assert _get("127.0.0.1", {"Cf-Ray": "abc", "Cf-Connecting-IP": "203.0.113.9"}) == DENY  # CF tunnel, no Access config
    assert _get("10.0.0.210", {"Cf-Ray": "abc"}) == DENY  # tunnel pointed at a LAN IP still is a tunnel
    # with the key all of these work
    assert _get("8.8.8.8", path="/api/ytdlp?k=" + KEY) == 200
    assert _get("127.0.0.1", {"Tailscale-Funnel-Request": "?1"}, path="/api/ytdlp?k=" + KEY) == 200
    assert _get("8.8.8.8", path="/api/ytdlp?k=wrong") == DENY

def test_trust_lan_off_requires_key():
    _setup(False)
    assert _get("10.0.0.210") == DENY
    assert _get("127.0.0.1") == DENY
    assert _get("10.0.0.210", path="/api/ytdlp?k=" + KEY) == 200

def test_health_always_open():
    _setup(False)
    assert _get("8.8.8.8", path="/health") == 200

def test_cmd_requires_real_key_even_on_lan():
    _setup(True)
    assert _get("10.0.0.210", path="/cmd?c=link") == 403
    assert _get("127.0.0.1", path="/cmd?c=link") == 403
    assert _get("10.0.0.210", path="/cmd?c=link&k=" + KEY) == 200

def test_trust_flag_is_per_request():
    _setup(True)
    assert _get("10.0.0.210") == 200
    assert _get("8.8.8.8") == DENY  # same thread, previous trust must not leak

# ---------------- Cloudflare Access JWT ----------------
def test_jwt_verify():
    _setup(True, TEAM, AUD)
    ok = lambda t: ms.cf_access_ok(t, keys=KEYS, team=TEAM, aud=AUD)
    assert ok(sign(claims()))
    assert ok(sign(claims(aud=AUD)))
    assert not ok(sign(claims(aud=["other"])))
    assert not ok(sign(claims(iss="https://evil.cloudflareaccess.com")))
    assert not ok(sign(claims(exp=int(time.time()) - 120)))
    assert not ok(sign(claims(nbf=int(time.time()) + 600)))
    assert not ok(sign(claims(), kid="nope"))
    assert not ok(sign(claims(), alg="HS256"))
    assert not ok(sign(claims(), d=D + 2))           # wrong signature
    t = sign(claims()); h, p, s = t.split(".")
    assert not ok(f"{h}.{_b64u(json.dumps(claims(email='y@example.com')).encode())}.{s}")  # tampered payload
    assert not ok("") and not ok("a.b") and not ok("x.y.z")
    assert not ms.cf_access_ok(sign(claims()), keys=KEYS, team="", aud="")  # unset config -> never

def test_cf_tunnel_with_valid_access_jwt_is_keyless():
    _setup(True, TEAM, AUD)
    good = sign(claims())
    hdr = {"Cf-Ray": "abc", "Cf-Connecting-IP": "203.0.113.9", "Cf-Access-Jwt-Assertion": good}
    assert _get("127.0.0.1", hdr) == 200
    assert _get("127.0.0.1", dict(hdr, **{"Cf-Access-Jwt-Assertion": sign(claims(aud=["x"]))})) == DENY
    assert _get("127.0.0.1", {"Cf-Ray": "abc"}) == DENY
    _setup(False, TEAM, AUD)  # Access works even with TRUST_LAN off
    assert _get("127.0.0.1", hdr) == 200

# ---------------- cookies ----------------
def _cookie(peer, headers, path):
    ms._hits.clear()
    i = _inst(peer, headers, path); assert i.guard() is True
    out = []; i.send_header = lambda k, v: out.append((k, v))
    real = ms.BaseHTTPRequestHandler.end_headers; ms.BaseHTTPRequestHandler.end_headers = lambda self: None
    try: i.end_headers()
    finally: ms.BaseHTTPRequestHandler.end_headers = real
    return [v for k, v in out if k == "Set-Cookie"]

def test_secure_cookie_over_https_only():
    _setup(True)
    c = _cookie("127.0.0.1", {"Tailscale-Funnel-Request": "?1", "X-Forwarded-Proto": "https"}, "/?k=" + KEY)
    assert c and "Secure" in c[0] and "HttpOnly" in c[0]
    c = _cookie("127.0.0.1", {"Cf-Ray": "a", "Cf-Visitor": '{"scheme":"https"}'}, "/?k=" + KEY)
    assert c and "Secure" in c[0]
    c = _cookie("10.0.0.210", {}, "/")
    assert c and "Secure" not in c[0]


# ---------------- auth cookie (cookie-20261110) ----------------
def _ms_auth(cookies):
    for v in cookies:
        if v.startswith("ms_auth="):
            return v.split(";", 1)[0].split("=", 1)[1]
    return None

def test_auth_cookie_flags_and_lifetime():
    _setup(True)
    c = _cookie("8.8.8.8", {"X-Forwarded-Proto": "https", "Cf-Ray": "a", "Cf-Visitor": '{"scheme":"https"}'}, "/?k=" + KEY)
    auth = [v for v in c if v.startswith("ms_auth=")]
    assert auth, "valid key must Set-Cookie ms_auth"
    s = auth[0]
    assert "HttpOnly" in s and "SameSite=Lax" in s and "Secure" in s
    assert "Max-Age=31536000" in s and "Path=/" in s
    c2 = _cookie("8.8.8.8", {}, "/?k=" + KEY)
    auth2 = [v for v in c2 if v.startswith("ms_auth=")]
    assert auth2 and "Secure" not in auth2[0] and "HttpOnly" in auth2[0] and "SameSite=Lax" in auth2[0]

def test_auth_cookie_not_set_on_lan_keyless():
    _setup(True)
    c = _cookie("10.0.0.210", {}, "/")
    assert not any(v.startswith("ms_auth=") for v in c)

def test_auth_cookie_alone_allows_public_and_cf_proxy():
    _setup(True)
    tok = _ms_auth(_cookie("8.8.8.8", {"X-Forwarded-Proto": "https"}, "/?k=" + KEY))
    assert tok and len(tok) == 64
    hdr = {"Cookie": "ms_auth=" + tok, "Cf-Ray": "abc", "Cf-Connecting-IP": "203.0.113.9"}
    assert _get("127.0.0.1", hdr, path="/api/ytdlp") == 200
    assert _get("8.8.8.8", {"Cookie": "ms_auth=" + tok}, path="/api/ytdlp") == 200
    assert _get("8.8.8.8", {"Cookie": "ms_auth=" + ("0" * 64)}, path="/api/ytdlp") == DENY
    assert _get("8.8.8.8", path="/api/ytdlp") == DENY
    # cookie proves a prior valid key, so /cmd works; bare LAN still must not
    assert _get("8.8.8.8", {"Cookie": "ms_auth=" + tok}, path="/cmd?c=status") == 200
    assert _get("10.0.0.210", path="/cmd?c=status") == 403

if __name__ == "__main__":
    n = 0
    for name, fn in list(globals().items()):
        if name.startswith("test_") and callable(fn): fn(); n += 1; print("ok", name)
    print(f"{n} passed")
