#!/usr/bin/env python3
"""Public URL: lyrics hit-rate on popular songs, and Shorts first-open time. Never prints secrets."""
import json, os, time
from pathlib import Path
from playwright.sync_api import sync_playwright

BASE = os.environ.get("MS_BASE", "https://tunestream.dpdns.org")
CHROME = os.environ.get("CHROME", "/usr/bin/google-chrome")
SONGS = [
    ("Blinding Lights", "The Weeknd", 200),
    ("Shape of You", "Ed Sheeran", 233),
    ("Someone Like You", "Adele", 285),
    ("Bohemian Rhapsody", "Queen", 354),
    ("Smells Like Teen Spirit", "Nirvana", 301),
    ("Old Town Road", "Lil Nas X", 157),
    ("Sorry", "Justin Bieber", 200),
    ("Cheap Thrills", "Sia", 211),
    ("Lean On", "Major Lazer", 176),
    ("See You Again", "Wiz Khalifa", 229),
]

def pw():
    return Path(os.environ.get("MS_PW_FILE", "/tmp/loadtest.pw")).read_text(encoding="utf-8").strip()

def main():
    out = {"lyrics": [], "shorts": {}}
    with sync_playwright() as p:
        b = p.chromium.launch(executable_path=CHROME, headless=True,
                              args=["--autoplay-policy=no-user-gesture-required", "--disable-dev-shm-usage"])
        ctx = b.new_context(viewport={"width": 390, "height": 844}, is_mobile=True, has_touch=True)
        pg = ctx.new_page()
        pg.goto(BASE + "/login", wait_until="domcontentloaded", timeout=45000)
        st = pg.evaluate(
            """async p => {
              const r = await fetch('/api/auth/login', {method:'POST', headers:{'Content-Type':'application/json'},
                body: JSON.stringify({u:'loadtest', p}), credentials:'same-origin'});
              return r.status;
            }""",
            pw(),
        )
        if st != 200:
            raise SystemExit("login failed %s" % st)
        pg.goto(BASE + "/", wait_until="domcontentloaded", timeout=45000)
        pg.wait_for_function("() => typeof lyClean === 'function' || typeof loadLyrics === 'function'", timeout=30000)

        hits = 0
        for t, a, d in SONGS:
            t0 = time.time()
            j = pg.evaluate(
                """async ({t,a,d}) => {
                  const t0 = performance.now();
                  const r = await fetch('/api/lyrics?k='+(window.K||'')+'&t='+encodeURIComponent(t)+'&a='+encodeURIComponent(a)+'&d='+d);
                  const body = await r.json();
                  return {ms: Math.round(performance.now()-t0), status: r.status,
                          hit: !!(body && (body.synced || body.plain)),
                          timeout: !!(body && body.timeout),
                          src: (body && body.src) || '',
                          name: (body && body.name) || ''};
                }""",
                {"t": t, "a": a, "d": d},
            )
            j["title"] = t
            j["wall_ms"] = int((time.time() - t0) * 1000)
            out["lyrics"].append(j)
            if j.get("hit"):
                hits += 1
            print("LYRIC", "HIT" if j.get("hit") else "MISS", t, "ms="+str(j.get("ms")), "timeout="+str(j.get("timeout")), "src="+str(j.get("src") or "-"))

        # Shorts: two fetches — first may populate, second must be cache-fast; also open the tab.
        def sh_api(warm=False):
            return pg.evaluate(
                """async warm => {
                  const t0 = performance.now();
                  const u = '/api/shorts?k='+(window.K||'')+'&n=20&page=0'+(warm?'&warm=1':'');
                  const r = await fetch(u);
                  const body = await r.json();
                  const n = Array.isArray(body) ? body.length : 0;
                  return {ms: Math.round(performance.now()-t0), status: r.status, n};
                }""",
                warm,
            )
        a1 = sh_api(False)
        a2 = sh_api(False)
        out["shorts"]["api1"] = a1
        out["shorts"]["api2"] = a2
        t0 = time.time()
        ui = pg.evaluate(
            """async () => {
              const t0 = performance.now();
              if (typeof go === 'function') { try { go('shorts'); } catch(e) {} }
              else { window.view = 'shorts'; }
              if (typeof loadShortsFeed === 'function') await loadShortsFeed(false);
              const n = (window.shRes && window.shRes.length) || 0;
              const empty = (document.getElementById('empty') || {}).style && document.getElementById('empty').style.display;
              return {ms: Math.round(performance.now()-t0), n, empty};
            }"""
        )
        out["shorts"]["ui"] = ui
        out["shorts"]["ui_wall_ms"] = int((time.time() - t0) * 1000)
        print("SHORTS api1", a1, "api2", a2, "ui", ui)
        b.close()

    n = len(SONGS)
    miss = n - hits
    print("LYRICS_HIT", hits, "/", n)
    print("SHORTS_OPEN_MS", (out["shorts"].get("ui") or {}).get("ms"), "api1", a1.get("ms"), "api2", a2.get("ms"), "n", (out["shorts"].get("ui") or {}).get("n") or a2.get("n"))
    out["summary"] = {"hits": hits, "n": n, "miss": miss}
    print("LYRICS_SHORTS", json.dumps(out["summary"] | {"shorts": out["shorts"]}))
    if hits < 7:
        raise SystemExit("lyrics hit-rate too low: %s/%s" % (hits, n))
    if not ((a2.get("n") or 0) >= 8 or (ui.get("n") or 0) >= 8):
        raise SystemExit("shorts feed too small")
    # cached second API call should be clearly faster than a cold 10s search
    if a2.get("ms", 99999) > 4000:
        raise SystemExit("shorts cached fetch still slow: %sms" % a2.get("ms"))

if __name__ == "__main__":
    main()
