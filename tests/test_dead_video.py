"""hunt-20261117: terminal YouTube errors must be cached as dead and not retried
across clients, qualities, or a CLI fallback. Offline; never prints secrets."""
from __future__ import annotations
import importlib.util, sys, tempfile, time, json
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
spec = importlib.util.spec_from_file_location("music_server_dead", ROOT / "music_server.py")
ms = importlib.util.module_from_spec(spec); spec.loader.exec_module(ms)
TMP = Path(tempfile.mkdtemp(prefix="ms-dead-"))
ms.CACHE = TMP
ms._DEAD.clear()
if (TMP / "dead-vids.json").exists():
    (TMP / "dead-vids.json").unlink()

MSGS_DEAD = [
    "ERROR: [youtube] ZZZZZdead01: This video is unavailable",
    "ERROR: [youtube] Yf5yBXFbXK4: Video unavailable. This video is not available",
    "ERROR: [youtube] vn7dKz7HcDY: This video requires payment to watch",
    "ERROR: [youtube] abcdefghijk: Private video",
    "ERROR: [youtube] abcdefghijk: This video has been removed by the uploader",
    "ERROR: [youtube] abcdefghijk: This video is members-only",
]
MSGS_LIVE = [
    "ERROR: [youtube] abcdefghijk: Sign in to confirm you’re not a bot",
    "HTTP Error 429: Too Many Requests",
    "timed out",
]

def test_dead_regex():
    for m in MSGS_DEAD:
        assert ms._DEAD_RE.search(m), m
    for m in MSGS_LIVE:
        assert not ms._DEAD_RE.search(m), m
    print("  regex ok")

def test_mark_and_shared_file():
    ms._DEAD.clear()
    ms._note_extract_err("ZZZZZdead01", RuntimeError(MSGS_DEAD[0]))
    assert ms._dead_until("ZZZZZdead01") > time.time()
    p = TMP / "dead-vids.json"
    assert p.is_file(), "dead ids should be persisted for other workers"
    data = json.loads(p.read_text())
    assert "ZZZZZdead01" in data
    # other process / cold memory
    ms._DEAD.clear()
    assert ms._dead_until("ZZZZZdead01") > time.time(), "reload from disk"
    print("  shared file ok")

def test_extract_stops_after_first_terminal_error():
    ms._DEAD.clear()
    if (TMP / "dead-vids.json").exists():
        (TMP / "dead-vids.json").unlink()
    kinds = []
    cli = []
    def ydl(vid, fmt, kind):
        kinds.append(kind)
        raise RuntimeError("ERROR: [youtube] ZZZZZdead01: This video is unavailable")
    real_ydl, real_kinds, real_run = ms._ydl_info, ms._kinds, __import__("subprocess").run
    ms._ydl_info = ydl
    ms._kinds = lambda vid: ("vis", "def")
    def boom(*a, **k):
        cli.append(1)
        return SimpleNamespace(stdout="", stderr="unavailable", returncode=1)
    import subprocess
    subprocess.run = boom
    try:
        t0 = time.time()
        try:
            ms._extract_inproc("ZZZZZdead01", "std")
            raise AssertionError("should have raised")
        except RuntimeError as e:
            assert "unavailable" in str(e).lower() or "extract" in str(e).lower()
        dt = time.time() - t0
        assert kinds == ["vis"], f"retried other clients: {kinds}"
        assert not cli, "CLI fallback ran after a terminal unavailability"
        assert dt < 2, f"took {dt:.1f}s"
        assert ms._dead_until("ZZZZZdead01") > time.time()
        # second quality / later call is instant
        kinds.clear()
        t1 = time.time()
        try:
            ms.cached_entry("ZZZZZdead01", "hi")
        except RuntimeError:
            pass
        assert kinds == [], f"second extract retried yt-dlp: {kinds}"
        assert time.time() - t1 < 0.5
        print(f"  first fail in {dt:.2f}s, later calls skipped")
    finally:
        ms._ydl_info = real_ydl
        ms._kinds = real_kinds
        subprocess.run = real_run

if __name__ == "__main__":
    test_dead_regex()
    test_mark_and_shared_file()
    test_extract_stops_after_first_terminal_error()
    print("OK")
