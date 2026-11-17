#!/usr/bin/env python3
"""Saved/offline: a downloaded song still plays when the tab is offline.
Uses the signed-in loadtest session on MS_BASE. Never reads music.env,
never prints secrets, never touches port 8120."""
import json, os, time
from pathlib import Path
from playwright.sync_api import sync_playwright

BASE = os.environ.get("MS_BASE", "http://127.0.0.1:8140")
CHROME = os.environ.get("CHROME", "/usr/bin/google-chrome")
SEED = os.environ.get("MS_OFF_ID", "4NRXx6U8ABQ")
R = []

def pw():
    return Path(os.environ.get("MS_PW_FILE", "/tmp/loadtest.pw")).read_text(encoding="utf-8").strip()

def ok(name, cond, info=None):
    R.append({"name": name, "pass": bool(cond), "detail": info})
    print(("PASS " if cond else "FAIL ") + name, json.dumps(info, default=str)[:700] if info is not None else "")

def main():
    with sync_playwright() as p:
        b = p.chromium.launch(executable_path=CHROME, headless=True, args=["--autoplay-policy=no-user-gesture-required"])
        ctx = b.new_context(viewport={"width": 390, "height": 844}, is_mobile=True, has_touch=True)
        page = ctx.new_page()
        page.goto(BASE + "/login", wait_until="domcontentloaded")
        st = page.evaluate(
            "async p=>(await fetch('/api/auth/login',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({u:'loadtest',p}),credentials:'same-origin'})).status",
            pw(),
        )
        ok("login", st == 200, st)
        page.goto(BASE + "/", wait_until="domcontentloaded")
        page.wait_for_function("()=>typeof play==='function'&&typeof saveOff==='function'", timeout=30000)
        ev = page.evaluate(
            """async (id) => {
              try{await saveOff({id,title:'offline-seed',channel:'e2e',dur:240})}catch(e){return {err:String(e)}}
              const off=typeof isOff==='function'&&isOff(id);
              return {off, hasUrl:!!(OFS&&OFS.urls&&OFS.urls[id])};
            }""",
            SEED,
        )
        # saveOff may be async and hit /audio; give it time
        t0 = time.time(); last = ev
        while time.time() - t0 < 90:
            last = page.evaluate(
                "(id)=>({off:typeof isOff==='function'&&isOff(id), hasFn:typeof saveOff==='function'})",
                SEED,
            )
            if last and last.get("off"):
                break
            time.sleep(1)
        ok("song saved for offline", last and last.get("off"), last)
        page.evaluate("(id)=>{queue=[{id,title:'offline-seed',channel:'e2e',dur:240}];qi=0;play()}", SEED)
        t0 = time.time(); online = None
        while time.time() - t0 < 40:
            online = page.evaluate("()=>({ct:+((M&&M.currentTime)||0), paused:!!(M&&M.paused), src:((M&&M.currentSrc)||'').slice(0,24)})")
            if online and online.get("ct", 0) >= 0.4 and not online.get("paused"):
                break
            time.sleep(0.3)
        ok("plays while online from a saved copy or stream", online and online.get("ct", 0) >= 0.4, online)
        ctx.set_offline(True)
        page.evaluate(
            """(id) => {
              try{M.pause()}catch(_){}
              queue=[{id,title:'offline-seed',channel:'e2e',dur:240}];qi=0;play();
            }""",
            SEED,
        )
        t0 = time.time(); offp = None
        while time.time() - t0 < 25:
            offp = page.evaluate("()=>({ct:+((M&&M.currentTime)||0), paused:!!(M&&M.paused), want:(M&&M.dataset&&M.dataset.wantPlay)||'', src:((M&&(M.currentSrc||M.src))||'').startsWith('blob:')})")
            if offp and offp.get("ct", 0) >= 0.3 and not offp.get("paused"):
                break
            time.sleep(0.3)
        ok("saved song plays while the tab is offline", offp and offp.get("ct", 0) >= 0.3 and not offp.get("paused"), offp)
        ctx.set_offline(False)
        b.close()
    failed = [r for r in R if not r["pass"]]
    print(json.dumps({"passed": len(R)-len(failed), "failed": len(failed), "total": len(R)}))
    raise SystemExit(1 if failed else 0)

if __name__ == "__main__":
    main()
