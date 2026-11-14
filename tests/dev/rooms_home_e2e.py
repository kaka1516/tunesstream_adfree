#!/usr/bin/env python3
"""Public URL: main-screen Rooms button opens the room list and joins, headless mobile Chromium.
Does not touch port 8120. Never prints secrets."""
import json, os, time
from pathlib import Path
from playwright.sync_api import sync_playwright

BASE = os.environ.get("MS_BASE", "https://tunestream.dpdns.org")
CHROME = os.environ.get("CHROME", "/usr/bin/google-chrome")
ROOM = os.environ.get("MS_ROOM", "CHILL")
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
        pg.wait_for_function("() => typeof rmOpen==='function' && document.getElementById('rmtab')", timeout=30000)
        # allow a one-time SW upgrade reload to finish before we click
        try:
            pg.wait_for_function("() => !!(sessionStorage.msSwReloaded || (window.__swV && window.__swV==='ms-v93') || typeof rmOpen==='function')", timeout=8000)
        except Exception:
            pass
        time.sleep(0.8)
        if pg.evaluate("() => typeof rmOpen!=='function' || !document.getElementById('rmtab')"):
            pg.wait_for_function("() => typeof rmOpen==='function' && document.getElementById('rmtab')", timeout=30000)

        vis = pg.evaluate(
            """() => {
              const el=document.getElementById('rmtab');
              if(!el) return {ok:false};
              const r=el.getBoundingClientRect();
              const cs=getComputedStyle(el);
              return {
                ok: true,
                text: (el.textContent||'').trim(),
                w: Math.round(r.width), h: Math.round(r.height),
                top: Math.round(r.top), left: Math.round(r.left),
                visible: !!(r.width&&r.height) && cs.display!=='none' && cs.visibility!=='hidden' && r.bottom>0 && r.top<window.innerHeight,
                inHeader: !!el.closest('header') || !!el.closest('#tabs')
              };
            }"""
        )
        ok("Rooms button visible on main screen", bool(vis.get("visible") and vis.get("inHeader") and "Rooms" in (vis.get("text") or "")), vis)

        pg.locator("#rmtab").click()
        t0 = time.time()
        opened = {}
        while time.time() - t0 < 15:
            try:
                opened = pg.evaluate(
                """() => {
                  const p=document.getElementById('rmp');
                  const list=document.getElementById('rmlist');
                  const rooms=[...((list&&list.querySelectorAll('button.rmr'))||[])].map(b => ({
                    r: b.dataset.r, name: (b.querySelector('b')&&b.querySelector('b').textContent)||b.textContent||''
                  }));
                  return {open: !!(p&&p.classList.contains('open')), n: rooms.length, names: rooms.map(x=>x.r||x.name), hasChat: !!document.getElementById('rmform'), hasVoice: !!document.getElementById('rmvc')};
                }"""
            )
            except Exception:
                opened = {}
            if opened.get("open") and opened.get("n", 0) >= 10:
                break
            time.sleep(0.3)
        ok("Rooms button opens the list of 10 rooms", bool(opened.get("open") and opened.get("n", 0) >= 10), opened)

        # one tap to join
        joined = pg.evaluate(
            """(code) => {
              const btn=[...document.querySelectorAll('#rmlist button.rmr')].find(b => (b.dataset.r||'')===code || (b.textContent||'').toUpperCase().includes(code));
              if(!btn) return {ok:false, err:'no button'};
              btn.click();
              return {ok:true};
            }""",
            ROOM,
        )
        t0 = time.time()
        state = {}
        while time.time() - t0 < 15:
            state = pg.evaluate(
                """(code) => {
                  let rm=null; try{rm=JSON.parse(sessionStorage.rm||'null')}catch(e){}
                  const here=(document.querySelector('#rmlist button.rmr.here')||{}).dataset||{};
                  const acts=document.getElementById('rmacts');
                  const chat=document.getElementById('rmform');
                  const vc=document.getElementById('rmvc');
                  const leave=document.getElementById('rmleave');
                  const p=document.getElementById('rmp');
                  return {
                    r: (rm&&rm.r)||here.r||'',
                    panel: !!(p&&p.classList.contains('open')),
                    acts: !!(acts && acts.style.display!=='none'),
                    chat: !!(chat && chat.style.display!=='none'),
                    voice: !!(vc && vc.style.display!=='none' && (vc.offsetWidth||vc.offsetHeight)),
                    leave: !!(leave && leave.offsetWidth),
                    vcLabel: (vc&&vc.textContent)||''
                  };
                }""",
                ROOM,
            )
            if state.get("r") == ROOM and (state.get("chat") or state.get("acts")):
                break
            time.sleep(0.4)
        ok(
            "one tap joins the room",
            state.get("r") == ROOM,
            {"click": joined, "state": state},
        )
        ok(
            "chat and voice reachable after join",
            state.get("r") == ROOM and state.get("chat") and state.get("voice"),
            state,
        )

        # leave so we don't linger in the room
        pg.evaluate(
            """() => {
              try { if (typeof roomLeave==='function') roomLeave(); } catch(e) {}
              try { if (typeof rmClose==='function') rmClose(); } catch(e) {}
            }"""
        )
        b.close()

    failed = [x for x in R if not x["pass"]]
    print("ROOMS_HOME", json.dumps({"n": len(R), "fail": len(failed), "results": R}, default=str))
    raise SystemExit(1 if failed else 0)

if __name__ == "__main__":
    main()
