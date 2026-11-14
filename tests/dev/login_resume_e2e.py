#!/usr/bin/env python3
"""Public URL: login and resume song/position after reload on headless mobile Chromium.
Does not touch port 8120. Never prints secrets."""
import json, os, time
from pathlib import Path
from playwright.sync_api import sync_playwright

BASE = os.environ.get("MS_BASE", "https://tunestream.dpdns.org")
CHROME = os.environ.get("CHROME", "/usr/bin/google-chrome")
VID = os.environ.get("MS_RESUME_ID", "4NRXx6U8ABQ")
SEEK = float(os.environ.get("MS_RESUME_T", "42"))
R = []

def pw():
    return Path(os.environ.get("MS_PW_FILE", "/tmp/loadtest.pw")).read_text(encoding="utf-8").strip()

def ok(name, cond, info=None):
    R.append({"name": name, "pass": bool(cond), "detail": info})
    print(("PASS " if cond else "FAIL ") + name, json.dumps(info, default=str)[:800] if info is not None else "")

def snap(page):
    return page.evaluate(
        """() => {
          const c=typeof cur==='function'&&cur();
          const m=window.M||window.AUD||document.getElementById('aud')||{};
          let pos=null; try { pos=JSON.parse(localStorage.getItem('local.msPos')||'null'); } catch(e) {}
          const banner=document.getElementById('resume20');
          return {
            id:(c&&c.id)||'',
            title:(c&&c.title)||'',
            ct: +(m.currentTime||0),
            paused: !!m.paused,
            pos: pos && {id:pos.id, t:pos.t},
            banner: !!banner,
            offered: window.__msResumeOffered||null
          };
        }"""
    )

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
        if st != 200:
            b.close()
            raise SystemExit(1)
        pg.goto(BASE + "/", wait_until="domcontentloaded", timeout=45000)
        pg.wait_for_function("() => typeof play==='function'", timeout=30000)
        who = pg.evaluate("() => (window.__msBoot&&window.__msBoot.user)||(window.B&&B.user)||''")
        ok("session is signed in", who == "loadtest", {"user": who})

        pg.evaluate(
            """(id) => {
              try { if (typeof radOn!=='undefined') radOn=false; } catch(e) {}
              try { if (typeof setMode==='function') setMode('a'); } catch(e) {}
              queue=[{id, title:'resume check', channel:''}]; qi=0;
              play(0);
            }""",
            VID,
        )
        t0 = time.time()
        started = False
        while time.time() - t0 < 25:
            s = snap(pg)
            if s.get("id") == VID and s.get("ct", 0) > 0.5:
                started = True
                break
            time.sleep(0.4)
        ok("song playing before save", started, s)

        # Land past the 2s resume floor and save both local and signed-in state
        seeked = pg.evaluate(
            """async (t) => {
              const m=window.M||window.AUD||document.getElementById('aud');
              if (!m) return {ok:false, err:'no media'};
              try { m.currentTime=t; } catch(e) { return {ok:false, err:String(e)}; }
              await new Promise(r => setTimeout(r, 400));
              try { if (typeof window.__msPosSave==='function') window.__msPosSave(); } catch(e) {}
              try { if (m.pause) m.pause(); } catch(e) {}
              try { if (typeof window.__msPosSave==='function') window.__msPosSave(); } catch(e) {}
              try { if (typeof window.__msSyncFlush==='function') window.__msSyncFlush(); } catch(e) {}
              await new Promise(r => setTimeout(r, 800));
              let pos=null; try { pos=JSON.parse(localStorage.getItem('local.msPos')||'null'); } catch(e) {}
              return {ok:true, ct:m.currentTime||0, paused:!!m.paused, pos};
            }""",
            SEEK,
        )
        ok(
            "position saved",
            bool(seeked.get("ok")) and (seeked.get("pos") or {}).get("id") == VID and (seeked.get("pos") or {}).get("t", 0) >= SEEK - 5,
            seeked,
        )

        saved_t = float((seeked.get("pos") or {}).get("t") or seeked.get("ct") or SEEK)
        pg.reload(wait_until="domcontentloaded", timeout=45000)
        pg.wait_for_function("() => typeof play==='function'", timeout=30000)

        # Wait for the continue banner (or auto-restore of the same song/position)
        t0 = time.time()
        after = {}
        banner = False
        auto = False
        while time.time() - t0 < 12:
            after = snap(pg)
            if after.get("banner"):
                banner = True
                break
            if after.get("id") == VID and abs(after.get("ct", 0) - saved_t) <= 8 and after.get("ct", 0) > 2:
                auto = True
                break
            time.sleep(0.3)
        ok("resume offered or auto-restored after reload", banner or auto, after)

        if banner and not auto:
            pg.evaluate(
                """() => {
                  const d=document.getElementById('resume20');
                  const btn=d && d.querySelector('[data-r], button.p');
                  if (btn) btn.click();
                }"""
            )
            t0 = time.time()
            while time.time() - t0 < 25:
                after = snap(pg)
                if after.get("id") == VID and after.get("ct", 0) > 2:
                    break
                time.sleep(0.4)

        ok(
            "song and position restored",
            after.get("id") == VID and after.get("ct", 0) > 2 and abs(after.get("ct", 0) - saved_t) <= 10,
            {"saved": saved_t, "after": after},
        )
        b.close()

    failed = [x for x in R if not x["pass"]]
    print("RESUME", json.dumps({"n": len(R), "fail": len(failed), "results": R}, default=str))
    raise SystemExit(1 if failed else 0)

if __name__ == "__main__":
    main()
