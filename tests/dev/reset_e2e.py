#!/usr/bin/env python3
"""Public URL: /reset drops stale app caches and the service worker, but keeps
login cookies, localStorage, and the 'off' saved-song cache. Never prints secrets.
"""
import json, os, time
from pathlib import Path
from playwright.sync_api import sync_playwright

BASE = os.environ.get("MS_BASE", "https://tunestream.dpdns.org")
CHROME = os.environ.get("CHROME", "/usr/bin/google-chrome")
R = []

def pw():
    return Path(os.environ.get("MS_PW_FILE", "/tmp/loadtest.pw")).read_text(encoding="utf-8").strip()

def ok(name, cond, info=None):
    R.append({"name": name, "pass": bool(cond), "detail": info})
    print(("PASS " if cond else "FAIL ") + name, json.dumps(info, default=str)[:800] if info is not None else "")

def main():
    with sync_playwright() as p:
        b = p.chromium.launch(executable_path=CHROME, headless=True,
            args=["--autoplay-policy=no-user-gesture-required", "--disable-dev-shm-usage"])
        ctx = b.new_context(viewport={"width": 390, "height": 844}, is_mobile=True, has_touch=True,
            user_agent="Mozilla/5.0 (Linux; Android 14; SM-S916B) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Mobile Safari/537.36")
        pg = ctx.new_page()
        pg.goto(BASE + "/login", wait_until="domcontentloaded", timeout=45000)
        st = pg.evaluate(
            """async ({u,p}) => (await fetch('/api/auth/login',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({u,p}),credentials:'same-origin'})).status""",
            {"u": "loadtest", "p": pw()},
        )
        ok("login", st == 200, {"status": st})
        pg.goto(BASE + "/", wait_until="domcontentloaded", timeout=45000)
        pg.wait_for_function("() => typeof play==='function'", timeout=30000)
        # plant a stale app cache and a fake saved-song entry; set a localStorage flag
        planted = pg.evaluate(
            """async () => {
              try{ localStorage.msResetProbe = 'keep-me'; }catch(_){}
              await caches.open('ms-v90');
              await (await caches.open('ms-v90')).put('/shell', new Response('<html>stale-v90</html>', {headers:{'Content-Type':'text/html'}}));
              await caches.open('off');
              await (await caches.open('off')).put('/off/_resetprobe', new Response('songbytes', {headers:{'Content-Type':'audio/mp4'}}));
              const keys = await caches.keys();
              return {keys, hasV90: keys.includes('ms-v90'), hasOff: keys.includes('off'), flag: localStorage.msResetProbe||''};
            }"""
        )
        ok("planted stale cache and saved song", planted.get("hasV90") and planted.get("hasOff") and planted.get("flag")=="keep-me", planted)

        pg.goto(BASE + "/reset", wait_until="domcontentloaded", timeout=45000)
        # should land back on the player (or login if cookies were wrongly cleared)
        try:
            pg.wait_for_url(lambda u: "/reset" not in u, timeout=20000)
        except Exception as e:
            ok("left /reset", False, {"url": pg.url, "err": type(e).__name__})
        else:
            ok("left /reset", "/reset" not in pg.url, {"url": pg.url})

        # wait for player or login to settle
        time.sleep(1)
        state = pg.evaluate(
            """async () => {
              const keys = await caches.keys();
              let offHit = false;
              try{
                const r = await (await caches.open('off')).match('/off/_resetprobe');
                offHit = !!(r && (await r.text())==='songbytes');
              }catch(_){}
              let who = null;
              try{
                const r = await fetch('/api/auth/me', {credentials:'same-origin', cache:'no-store'});
                if(r.ok){ const j=await r.json(); who=j.u||j.user||j.name||true; }
                else who = r.status;
              }catch(e){ who = 'err'; }
              const regs = await navigator.serviceWorker.getRegistrations();
              return {
                url: location.pathname+location.search,
                keys, hasV90: keys.includes('ms-v90'), hasOff: keys.includes('off'), offHit,
                flag: (localStorage.msResetProbe||''),
                who, swRegs: regs.length,
                build: (typeof APP_BUILD==='string'&&APP_BUILD)||((document.querySelector('meta[name=ms-build]')||{}).content||'')
              };
            }"""
        )
        ok("stale app cache removed", not state.get("hasV90"), state)
        ok("saved-song cache kept", state.get("hasOff") and state.get("offHit"), state)
        ok("localStorage settings kept", state.get("flag")=="keep-me", state)
        # login cookie should still be valid (200 / signed-in), not 401
        who = state.get("who")
        ok("login cookie kept", who not in (401, "err", None, False) and who != 403, {"who": who, "url": state.get("url"), "build": state.get("build")})

        # cleanup probe blob
        try:
            pg.evaluate("async () => { try{ await (await caches.open('off')).delete('/off/_resetprobe'); }catch(_){} try{ delete localStorage.msResetProbe; }catch(_){} }")
        except Exception:
            pass
        b.close()
    failed = [x for x in R if not x["pass"]]
    print("RESET", json.dumps({"n": len(R), "fail": len(failed)}))
    raise SystemExit(0 if not failed else 1)

if __name__ == "__main__":
    main()
