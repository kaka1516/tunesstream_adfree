#!/usr/bin/env python3
"""Public URL: default video quality is 720p on headless mobile Chromium.
Does not touch port 8120. Never prints secrets."""
import json, os, time
from pathlib import Path
from playwright.sync_api import sync_playwright

BASE = os.environ.get("MS_BASE", "https://tunestream.dpdns.org")
CHROME = os.environ.get("CHROME", "/usr/bin/google-chrome")
# Official-style clip known to have a 720p rendition; already used as the radio seed.
VID = os.environ.get("MS_VIDEO_ID", "4NRXx6U8ABQ")
R = []

def pw():
    return Path(os.environ.get("MS_PW_FILE", "/tmp/loadtest.pw")).read_text(encoding="utf-8").strip()

def ok(name, cond, info=None):
    R.append({"name": name, "pass": bool(cond), "detail": info})
    print(("PASS " if cond else "FAIL ") + name, json.dumps(info, default=str)[:800] if info is not None else "")

def main():
    with sync_playwright() as p:
        b = p.chromium.launch(
            executable_path=CHROME,
            headless=True,
            args=["--autoplay-policy=no-user-gesture-required", "--disable-dev-shm-usage"],
        )
        ctx = b.new_context(
            viewport={"width": 390, "height": 844},
            is_mobile=True,
            has_touch=True,
            device_scale_factor=2,
            user_agent="Mozilla/5.0 (Linux; Android 14; SM-S916B) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Mobile Safari/537.36",
        )
        pg = ctx.new_page()
        pg.goto(BASE + "/login", wait_until="domcontentloaded", timeout=45000)
        st = pg.evaluate(
            """async ({u,p}) => (await fetch('/api/auth/login',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({u,p}),credentials:'same-origin'})).status""",
            {"u": "loadtest", "p": pw()},
        )
        ok("login", st == 200, {"status": st})
        pg.goto(BASE + "/", wait_until="domcontentloaded", timeout=45000)
        pg.wait_for_function("() => typeof play==='function' && typeof setMode==='function'", timeout=30000)

        boot = pg.evaluate(
            """() => {
              // fresh profile: do not force a resolution; only report the built-in default
              return {
                vres: (typeof vres!=='undefined'?String(vres):''),
                pick: localStorage.vresPick||'',
                stored: localStorage.vres||'',
                start: (typeof vStartRes==='function'?vStartRes():''),
                sel: (document.getElementById('vres')||{}).value||'',
                sw: (typeof V!=='undefined'?V:null) || (window.__swV||'')
              };
            }"""
        )
        ok(
            "default quality pick is 720",
            boot.get("pick") in ("", "720") and (boot.get("vres") == "720" or boot.get("sel") == "720"),
            boot,
        )

        pg.evaluate(
            """(id) => {
              try { if (typeof radOn!=='undefined') radOn=false; } catch(e) {}
              queue=[{id, title:'720p check', channel:''}]; qi=0;
              if (typeof play==='function') play(0);
            }""",
            VID,
        )
        t0 = time.time()
        playing = False
        while time.time() - t0 < 25:
            a = pg.evaluate(
                "() => {const c=typeof cur==='function'&&cur(); const m=window.M||window.AUD||document.getElementById('aud')||{}; return {id:(c&&c.id)||'', ct:m.currentTime||0, paused:!!m.paused};}"
            )
            if a.get("id") == VID and a.get("ct", 0) > 0.5:
                playing = True
                break
            time.sleep(0.4)
        ok("audio started", playing, a if playing else {"timeout": True})

        # Switch to video without writing vres — default pick must stay 720
        pg.evaluate("() => { try { setMode('v'); } catch(e) { window.__vErr=String(e); } }")
        v = {}
        t0 = time.time()
        while time.time() - t0 < 40:
            v = pg.evaluate(
                """() => {
                  const vid=document.getElementById('vid')||window.VID;
                  return {
                    mode: (typeof mode!=='undefined'?mode:''),
                    vres: (typeof vres!=='undefined'?String(vres):''),
                    pick: localStorage.vresPick||'',
                    start: (typeof vStartRes==='function'?vStartRes():''),
                    h: vid?vid.videoHeight:0,
                    w: vid?vid.videoWidth:0,
                    ct: vid?vid.currentTime:0,
                    paused: !!(vid&&vid.paused),
                    ready: vid?vid.readyState:0,
                    err: window.__vErr||null
                  };
                }"""
            )
            if v.get("h", 0) >= 720 and v.get("ct", 0) > 1 and not v.get("paused"):
                break
            time.sleep(0.5)
        ok(
            "video plays at 720p by default",
            v.get("h", 0) >= 720 and v.get("ct", 0) > 1 and v.get("mode") == "v",
            v,
        )
        b.close()

    failed = [x for x in R if not x["pass"]]
    print("VIDEO720", json.dumps({"n": len(R), "fail": len(failed), "results": R}, default=str))
    raise SystemExit(1 if failed else 0)

if __name__ == "__main__":
    main()
