"""perf-20261112: yt-dlp lookup cap, busy answer, singleflight and stream-URL cache (offline, no YouTube).
Run: python tests/test_perf_gate.py"""
from __future__ import annotations
import importlib.util, sys, threading, time
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
spec = importlib.util.spec_from_file_location("music_server_perf", ROOT / "music_server.py")
ms = importlib.util.module_from_spec(spec); spec.loader.exec_module(ms)

def test_gate_caps_concurrency():
    g = ms._XGate(4); peak = [0]; cur = [0]; lk = threading.Lock()
    def work():
        assert g.acquire(True, 10)
        with lk: cur[0] += 1; peak[0] = max(peak[0], cur[0])
        time.sleep(0.15)
        with lk: cur[0] -= 1
        g.release()
    ts = [threading.Thread(target=work) for _ in range(16)]
    [t.start() for t in ts]; [t.join() for t in ts]
    assert peak[0] == 4, peak

def test_gate_busy_after_wait():
    g = ms._XGate(1); assert g.acquire(True, 1)
    t0 = time.time(); ok = g.acquire(True, 0.4)
    assert not ok and 0.3 < time.time() - t0 < 1.5 and g.info()["busy"] == 1
    g.release(); assert g.acquire(True, 0.1); g.release()

def test_background_keeps_a_slot_and_yields():
    g = ms._XGate(2)
    assert g.acquire(False, 0.1)                 # background takes 1 of 2
    assert not g.acquire(False, 0.2)             # ... but never the last slot
    assert g.acquire(True, 0.2)                  # a listener still gets it
    g.release(); g.release()
    g2 = ms._XGate(1); assert g2.acquire(True, 0.1)
    res = {}
    def fgw(): res["fg"] = g2.acquire(True, 2)
    def bgw(): time.sleep(0.1); res["bg"] = g2.acquire(False, 0.6)
    a, b = threading.Thread(target=fgw), threading.Thread(target=bgw); a.start(); b.start()
    time.sleep(0.3); g2.release(); a.join(); b.join()
    assert res["fg"] is True and res["bg"] is False   # waiting listener wins over background

def test_extract_busy_raises_and_is_not_a_client_failure():
    old_g, old_w = ms._XG, ms.XT_WAIT
    ms._XG = ms._XGate(1); ms.XT_WAIT = 0.3; ms._XG.acquire(True, 1)
    ms._TLF.fg = True; ms._KBAD.pop("aaaaaaaaaaa", None)
    try:
        try: ms._extract_inproc("aaaaaaaaaaa", "std"); raise AssertionError("no busy")
        except ms.ExtractBusy: pass
        assert "aaaaaaaaaaa" not in ms._KBAD, "busy was counted against the yt-dlp client"
    finally:
        ms._TLF.fg = False; ms._XG.release(); ms._XG, ms.XT_WAIT = old_g, old_w

def test_singleflight_one_extraction():
    calls = [0]
    def slow():
        calls[0] += 1; time.sleep(0.3); return "u"
    out = []
    ts = [threading.Thread(target=lambda: out.append(ms._single(("t", "x"), slow))) for _ in range(10)]
    [t.start() for t in ts]; [t.join() for t in ts]
    assert calls[0] == 1 and out == ["u"] * 10

def test_ucache_margin_and_fallback():
    vid, q = "bbbbbbbbbbb", "std"
    now = int(time.time())
    ms._ucache_save(vid, q, f"https://x.googlevideo.com/videoplayback?expire={now + 6 * 3600}&id=1", {})
    assert ms._ucache_load(vid, q)
    ms._ucache_save(vid, q, f"https://x.googlevideo.com/videoplayback?expire={now + 600}&id=1", {})   # < 15 min left -> re-extract
    assert ms._ucache_load(vid, q) is None
    c = ms._ucache_save(vid, q, "https://x.googlevideo.com/videoplayback?id=1", {})                 # no expire -> ~1 h
    assert 3600 <= c["expire"] - now <= 3600 + ms.UC_MARGIN + 5 and ms._ucache_load(vid, q)
    ms._ucache_invalidate(vid, q); assert ms._ucache_load(vid, q) is None

def test_lookup_helper_off_or_down_falls_back():
    old = dict(ms._LK)
    try:
        ms._LK.update(url="", key="")
        assert ms._remote_info("aaaaaaaaaaa", "bestaudio", "vis") is None          # not configured -> local
        ms._LK.update(url="http://127.0.0.1:9", key="x" * 32, down_until=0)       # nothing listens on :9
        t0 = time.time(); assert ms._remote_info("aaaaaaaaaaa", "bestaudio", "vis") is None
        assert time.time() - t0 < 3 and ms._LK["down_until"] > time.time()        # quick, and skipped for a while
        t0 = time.time(); assert ms._remote_info("aaaaaaaaaaa", "bestaudio", "vis") is None and time.time() - t0 < 0.1
    finally: ms._LK.clear(); ms._LK.update(old)

def test_v4_url_detection():
    assert ms._v4_url("https://r1.googlevideo.com/videoplayback?ip=203.0.113.5&id=1")
    assert not ms._v4_url("https://r1.googlevideo.com/videoplayback?ip=2001%3Adb8%3A%3A1&id=1")
    assert not ms._v4_url("https://r1.googlevideo.com/videoplayback?id=1")

if __name__ == "__main__":
    n = 0
    for k, f in list(globals().items()):
        if k.startswith("test_"): f(); n += 1; print("ok", k)
    print(f"{n} passed")
