"""radio-20261111 regression: /api/radio must answer fast with playable songs even when YouTube is slow, failing or empty.
Run: python tests/test_radio_resilience.py        (offline, simulated YouTube)
     MS_LIVE=1 python tests/test_radio_resilience.py   (also 3 real seeds, light: one radio call each)"""
from __future__ import annotations
import importlib.util, json, os, sys, tempfile, time, shutil
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
spec = importlib.util.spec_from_file_location("music_server_radio", ROOT / "music_server.py")
ms = importlib.util.module_from_spec(spec); spec.loader.exec_module(ms)
TMP = Path(tempfile.mkdtemp(prefix="ms-radio-test-")); ms.RCACHE_DIR = TMP

WORDS = "amber river silent thunder velvet morning neon garden crystal shadow golden echo wild horizon paper moon desert rain ocean fire winter bloom midnight city lantern storm violet road".split()
def fake_songs(prefix, n, ch="Artist"):
    import hashlib
    out = []
    for i in range(n):
        vid = (hashlib.md5(f"{prefix}{i}".encode()).hexdigest()[:11]).replace("0", "a")
        w = WORDS[(i * 7 + len(prefix)) % len(WORDS)] + " " + WORDS[(i * 13 + 3) % len(WORDS)]
        out.append({"id": vid, "title": f"{w.title()} {prefix}{vid[:4]}", "dur": 150 + i * 9, "channel": f"{ch} {WORDS[i % len(WORDS)]}"})
    return out
SEED = "kffacxfA7G4"
real = {k: getattr(ms, k) for k in ("_yti_post", "flat", "_fast_search")}
def restore():
    for k, v in real.items(): setattr(ms, k, v)
    ms._rcache.clear(); ms._YTR.clear(); ms._YTREL.clear(); ms._RG.clear()
    for f in TMP.glob("*.json"): f.unlink()

def youtube_down(sleep=0.0):
    def post(*a, **k):
        time.sleep(sleep); raise OSError("simulated YouTube outage")
    def flat(*a, **k):
        time.sleep(min(sleep, k.get("timeout", 5))); return []
    def fs(*a, **k): raise OSError("simulated search outage")
    ms._yti_post = post; ms.flat = flat; ms._fast_search = fs

def test_empty_list_never_sticks():
    restore(); youtube_down()
    assert ms._rd_list(SEED) == []
    assert SEED not in ms._YTR, "empty RD list was cached (the 2 h sticky failure)"
    songs = fake_songs("rd", 25)
    ms.flat = lambda *a, **k: songs
    assert len(ms._rd_list(SEED)) == 25

def test_slow_youtube_uses_saved_list_inside_budget():
    restore()
    good = fake_songs("old", 22)
    ms._radio_disk_save(SEED, mix="balanced", fast_out=good)
    p = ms._radio_disk_path(SEED, "balanced"); d = json.loads(p.read_text()); d["t"] = time.time() - 5 * 86400; p.write_text(json.dumps(d))
    youtube_down(sleep=30)
    t0 = time.time(); out = ms.radio_fast(SEED, [], [], "balanced", [], [], [], [], "")
    dt = time.time() - t0
    assert dt < ms.RADIO_FAST_BUDGET + 4, f"took {dt:.1f}s"
    assert len(out) >= 15, f"only {len(out)} songs"
    print(f"  slow YouTube -> {len(out)} songs in {dt:.1f}s from the saved list")

def test_innertube_mix_parser_and_fallback_to_related():
    restore()
    mix = [{"playlistPanelVideoRenderer": {"videoId": x["id"], "title": {"simpleText": x["title"]}, "lengthText": {"simpleText": "3:20"},
            "longBylineText": {"runs": [{"text": x["channel"]}]}}} for x in fake_songs("mx", 3)]
    mix.append({"playlistPanelVideoRenderer": {"videoId": "LIVEstream1", "title": {"simpleText": "live now"}}})  # no length = live
    rel = [{"lockupViewModel": {"contentType": "LOCKUP_CONTENT_TYPE_VIDEO", "contentId": x["id"],
            "metadata": {"lockupMetadataViewModel": {"title": {"content": x["title"]}, "metadata": {"contentMetadataViewModel": {"metadataRows": [{"metadataParts": [{"text": {"content": x["channel"]}}]}]}}}},
            "contentImage": {"thumbnailViewModel": {"overlays": [{"b": {"badges": [{"x": {"text": "4:01"}}]}}]}}}} for x in fake_songs("rel", 18)]
    body = {"contents": {"twoColumnWatchNextResults": {"playlist": {"playlist": {"contents": mix}}, "secondaryResults": {"secondaryResults": {"results": rel}}}}}
    ms._yti_post = lambda *a, **k: json.dumps(body).encode()
    m, r = ms._yti_next(SEED)
    assert len(m) == 3 and all(x["dur"] == 200 for x in m) and len(r) == 18 and r[0]["dur"] == 241
    ms.flat = lambda *a, **k: []
    t0 = time.time(); out = ms.radio_fast(SEED, [], [], "balanced", [], [], [], [], ""); dt = time.time() - t0
    assert len(out) >= 15, f"only {len(out)}"
    print(f"  thin mix (3) + related -> {len(out)} songs in {dt:.1f}s")

def test_everything_down_returns_quickly_not_500():
    restore(); youtube_down(sleep=30)
    t0 = time.time(); out = ms.radio_fast("JGwWNGJdvx8", [], [], "balanced", [], [], [], [], ""); dt = time.time() - t0
    assert isinstance(out, list) and dt < ms.RADIO_FAST_BUDGET + 4, dt
    print(f"  total outage -> {len(out)} songs in {dt:.1f}s (player then uses liked/recent songs)")

def live():
    restore()
    seeds = {"English": "ed sheeran perfect", "Telugu": "samajavaragamana song", "Hindi": "kesariya song", "Tamil": "vaathi coming song"}
    for name, q in seeds.items():
        vid = next(e["id"] for e in ms._fast_search(q)["entries"] if ms.VID.match(e.get("id") or ""))
        t0 = time.time(); out = ms.radio_fast(vid, [], [], "balanced", [], [], [], [], ""); dt = time.time() - t0
        print(f"  live {name} {vid}: {len(out)} songs in {dt:.1f}s; first: {out[0]['title'][:50] if out else '-'}")
        assert len(out) >= 15

if __name__ == "__main__":
    for n, f in list(globals().items()):
        if n.startswith("test_"): print(n); f()
    if os.environ.get("MS_LIVE"): live()
    restore(); shutil.rmtree(TMP, ignore_errors=True); print("ALL OK")
