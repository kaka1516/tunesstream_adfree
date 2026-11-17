#!/usr/bin/env python3
"""Hidden stale client (APP_BUILD spoofed to ms-v109) must upgrade to the
server build at the next track change, via /reset, without cutting mid-song.
Also checks clog events persist in IndexedDB and flush on resume.
Never prints secrets. Never claims to have heard audio."""
import json, os, time
from pathlib import Path
from playwright.sync_api import sync_playwright

BASE = os.environ.get("MS_BASE", "http://127.0.0.1:8131")
CHROME = os.environ.get("CHROME", "/usr/bin/google-chrome")
USER = "loadtest"
SEED = "4NRXx6U8ABQ"
SEED2 = "4fndeDfaWCg"
R = []
TARGET = os.environ.get("MS_LIVE_BUILD") or ""  # filled from /api/version if empty

def pw():
    return Path(os.environ.get("MS_PW_FILE", "/tmp/loadtest.pw")).read_text(encoding="utf-8").strip()

def ok(name, cond, info=None):
    R.append({"name": name, "pass": bool(cond), "detail": info})
    print(("PASS " if cond else "FAIL ") + name, json.dumps(info, default=str)[:900] if info is not None else "")

def hide(page, on, blank=None):
    if blank is not None:
        if on:
            blank.bring_to_front()
        else:
            page.bring_to_front()
        time.sleep(0.15)
    page.evaluate(
        """(on) => {
          try{
            Object.defineProperty(document, 'hidden', {configurable:true, get:()=>!!on});
            Object.defineProperty(document, 'visibilityState', {configurable:true, get:()=>on?'hidden':'visible'});
            document.dispatchEvent(new Event('visibilitychange'));
          }catch(_){}
        }""",
        on,
    )

def snap(page):
    return page.evaluate(
        """() => {
          const r=(typeof cur==='function'&&cur())||{};
          const a=(typeof M!=='undefined'&&M)||document.getElementById('aud');
          return {
            build: (window.__msForceBuild||((typeof APP_BUILD==='string'&&APP_BUILD)||'')), rawBuild:(typeof APP_BUILD==='string'&&APP_BUILD)||'',
            serverV: window.__msServerV||'',
            pending: window.__msPendingReload||'',
            id: r.id||'',
            paused: !!(a&&a.paused),
            want: a&&a.dataset.wantPlay,
            ct: a&&+(+a.currentTime||0).toFixed(2),
            dur: a&&(isFinite(a.duration)?+a.duration.toFixed(2):0),
            hidden: !!document.hidden,
            url: location.pathname+location.search,
            sw: window.__swV||''
          };
        }"""
    )

def main():
    global TARGET
    with sync_playwright() as p:
        b = p.chromium.launch(executable_path=CHROME, headless=True,
            args=["--autoplay-policy=no-user-gesture-required", "--disable-dev-shm-usage"])
        ctx = b.new_context(viewport={"width": 390, "height": 844}, is_mobile=True, has_touch=True,
            user_agent="Mozilla/5.0 (Linux; Android 14; SM-S916B) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Mobile Safari/537.36")
        page = ctx.new_page()
        blank = ctx.new_page()
        blank.goto("about:blank")

        page.goto(BASE + "/login", wait_until="domcontentloaded", timeout=45000)
        st = page.evaluate(
            """async ({u,p}) => (await fetch('/api/auth/login',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({u,p}),credentials:'same-origin'})).status""",
            {"u": USER, "p": pw()},
        )
        ok("login", st == 200, {"status": st})
        page.goto(BASE + "/", wait_until="domcontentloaded", timeout=45000)
        page.wait_for_function("() => typeof play==='function' && typeof next==='function' && typeof _msReloadAtTrackChange==='function'", timeout=30000)

        ver = page.evaluate("async () => { const r=await fetch('/api/version',{cache:'no-store'}); return r.json(); }")
        TARGET = (ver or {}).get("v") or TARGET or "ms-v112"
        ok("server is current", TARGET.startswith("ms-v") and (ver or {}).get("v")==TARGET, ver)
        boot = snap(page)
        ok("page booted as current", boot.get("build") == TARGET, boot)

        # clog IndexedDB persist
        idb = page.evaluate(
            """async () => {
              try{
                if(typeof window.__msClog!=='function') return {ok:false, why:'no-clog'};
                window.__msClog({ev:'play', id:'clog-probe', why:'idb-test'});
                await new Promise(r=>setTimeout(r, 250));
                const db = await new Promise((res,rej)=>{const q=indexedDB.open('ms-clog',1);q.onsuccess=()=>res(q.result);q.onerror=()=>rej(q.error);});
                const rows = await new Promise((res,rej)=>{try{const t=db.transaction('q','readonly').objectStore('q').getAll();t.onsuccess=()=>res(t.result||[]);t.onerror=()=>rej(t.error)}catch(e){res([])}});
                return {ok:true, n:rows.length, evs:(rows||[]).map(x=>x.ev).slice(-5), hasProbe:(rows||[]).some(x=>x.id==='clog-probe'||x.ev==='play')};
              }catch(e){return {ok:false, why:String(e&&e.message||e).slice(0,160)}}
            }"""
        )
        ok("clog persisted to IndexedDB", bool(idb and idb.get("ok") and (idb.get("n",0)>0 or idb.get("hasProbe"))), idb)

        # start a song on the current (v111) build so we have an active track
        started = page.evaluate(
            """async ({id}) => {
              try{
                if(typeof play==='function'){ queue=[{id,title:'seed'}]; qi=0; await play(); }
                return true;
              }catch(e){ return String(e&&e.message||e).slice(0,160); }
            }""",
            {"id": SEED},
        )
        ok("started first track", started is True, {"started": started})
        t0 = time.time()
        last = None
        while time.time()-t0 < 25:
            last = snap(page)
            if last.get("id") == SEED and (last.get("ct") or 0) >= 0 or (last.get("want")=="1"):
                if last.get("id") == SEED:
                    break
            time.sleep(0.4)
        ok("first track loaded", last and last.get("id")==SEED, last)

        # Spoof a v109-era client that is already open, then hide it
        page.evaluate(
            """() => {
              window.__msForceBuild = 'ms-v109';
              window.__msPendingReload = null;
              window.__msVerAt = 0;
              window.__msServerV = '';
              try{ sessionStorage.removeItem('msReloaded-ms-v109'); sessionStorage.removeItem('msReloaded-ms-v109At'); }catch(_){}
            }"""
        )
        hide(page, True, blank=blank)
        hidden = snap(page)
        ok("hidden with spoofed v109", hidden.get("build")=="ms-v109" and hidden.get("hidden") is True, hidden)

        # enqueue a second song and go next — this is the track-change boundary
        nav = {"reset": False, "err": None}
        def on_frame(frm):
            try:
                if "/reset" in (frm.url or ""):
                    nav["reset"] = True
            except Exception:
                pass
        page.on("framenavigated", on_frame)

        page.evaluate(
            """async ({id}) => {
              try{
                if(typeof queue!=='undefined'){
                  if(!queue.length) queue=[{id: (cur()&&cur().id)||''}];
                  // ensure a different next id
                  if(!queue[qi+1] || queue[qi+1].id!==id){ queue.splice(qi+1, 0, {id, title:'next-seed'}); }
                }
                if(typeof next==='function') next();
                return true;
              }catch(e){ return String(e&&e.message||e).slice(0,160); }
            }""",
            {"id": SEED2},
        )

        t0 = time.time()
        upgraded = None
        while time.time()-t0 < 30:
            if nav["reset"] or "/reset" in page.url:
                try:
                    page.wait_for_function("() => typeof APP_BUILD==='string'", timeout=15000)
                except Exception:
                    pass
                # /reset should bounce back to /
                try:
                    page.wait_for_url(lambda u: "/reset" not in (u if isinstance(u,str) else str(u)), timeout=20000)
                except Exception:
                    pass
                time.sleep(0.4)
                try:
                    page.wait_for_function("() => typeof APP_BUILD==='string'", timeout=15000)
                except Exception:
                    pass
                upgraded = snap(page)
                break
            try:
                upgraded = snap(page)
                if upgraded.get("build")==TARGET and "reset" not in (upgraded.get("url") or "") and upgraded.get("build")!="ms-v109":
                    # already on v111 after navigation
                    if "fresh=" in (upgraded.get("url") or "") or upgraded.get("serverV")==TARGET:
                        break
            except Exception as e:
                # navigation in flight
                nav["err"] = type(e).__name__
            time.sleep(0.35)

        # if still on the same document with pending reload, wait a bit more
        if not upgraded or upgraded.get("build")!=TARGET:
            time.sleep(2)
            try:
                upgraded = snap(page)
            except Exception as e:
                upgraded = {"err": type(e).__name__, "url": page.url}

        ok("navigated through /reset or fresh", nav["reset"] or "fresh=" in page.url or "reset" in page.url or (upgraded and upgraded.get("build")==TARGET),
           {"nav": nav, "url": page.url, "snap": upgraded})
        ok("build is current after track change", upgraded and upgraded.get("build")==TARGET, upgraded)

        # clog flush on resume
        hide(page, False, blank=blank)
        flushed = page.evaluate(
            """async () => {
              try{
                if(typeof window.__msClogFlush==='function'){ await window.__msClogFlush(); }
                await new Promise(r=>setTimeout(r, 300));
                return {ok:true, hasFlush: typeof window.__msClogFlush==='function', build: APP_BUILD};
              }catch(e){ return {ok:false, why:String(e&&e.message||e).slice(0,160)}; }
            }"""
        )
        ok("clog flush on resume callable", bool(flushed and flushed.get("ok") and flushed.get("hasFlush")), flushed)

        b.close()

    failed = [x for x in R if not x["pass"]]
    print("SUMMARY", json.dumps({"pass": len(R)-len(failed), "fail": len(failed), "total": len(R)}))
    return 0 if not failed else 1

if __name__ == "__main__":
    raise SystemExit(main())
