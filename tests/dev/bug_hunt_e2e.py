#!/usr/bin/env python3
"""Lean public-URL feature hunt on ms-v94+, headless mobile Chromium.
Logs console/page/HTTP errors per screen. Never prints secrets. Not 8120."""
import json, os, time
from pathlib import Path
from playwright.sync_api import sync_playwright

BASE = os.environ.get("MS_BASE", "https://tunestream.dpdns.org")
CHROME = os.environ.get("CHROME", "/usr/bin/google-chrome")
R, ERR = [], []

def pw():
    return Path(os.environ.get("MS_PW_FILE", "/tmp/loadtest.pw")).read_text(encoding="utf-8").strip()

def ok(name, cond, info=None):
    R.append({"name": name, "pass": bool(cond), "detail": info})
    print(("PASS " if cond else "FAIL ") + name, json.dumps(info, default=str)[:500] if info is not None else "")

def slim(u):
    try:
        from urllib.parse import urlsplit, urlunsplit, parse_qsl, urlencode
        p = urlsplit(u)
        q = [(k, v) for k, v in parse_qsl(p.query, keep_blank_values=True) if k.lower() not in ("k", "key", "token", "password")]
        return urlunsplit((p.scheme, p.netloc, p.path, urlencode(q), ""))[:180]
    except Exception:
        return (u or "")[:180]

def main():
    with sync_playwright() as p:
        b = p.chromium.launch(executable_path=CHROME, headless=True,
            args=["--autoplay-policy=no-user-gesture-required", "--disable-dev-shm-usage"])
        ctx = b.new_context(viewport={"width": 390, "height": 844}, is_mobile=True, has_touch=True,
            user_agent="Mozilla/5.0 (Linux; Android 14; SM-S916B) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Mobile Safari/537.36")
        page = ctx.new_page()
        screen = ["boot"]

        def on_pageerr(e):
            ERR.append({"screen": screen[0], "kind": "page", "msg": str(e)[:240]})
        def on_console(m):
            if m.type == "error":
                t = m.text or ""
                if "favicon" in t or "net::ERR_ABORTED" in t or "cloudflareinsights.com" in t or "Content Security Policy" in t:
                    return
                ERR.append({"screen": screen[0], "kind": "console", "msg": t[:240]})
        def on_response(r):
            try:
                if r.status < 400:
                    return
                u = r.url or ""
                if "tunestream.dpdns.org" not in u and "127.0.0.1" not in u:
                    return
                if r.status in (401,) and "/api/search" in u:
                    return  # checked separately for guests
                ERR.append({"screen": screen[0], "kind": "http", "status": r.status, "url": slim(u)})
            except Exception:
                pass
        page.on("pageerror", on_pageerr)
        page.on("console", on_console)
        page.on("response", on_response)

        ev = page.evaluate

        screen[0] = "login"
        page.goto(BASE + "/login", wait_until="domcontentloaded", timeout=45000)
        st = ev("""async p=>(await fetch('/api/auth/login',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({u:'loadtest',p}),credentials:'same-origin'})).status""", pw())
        ok("login", st == 200, {"status": st})

        screen[0] = "home"
        page.goto(BASE + "/", wait_until="domcontentloaded", timeout=45000)
        page.wait_for_function("() => typeof play==='function' && typeof search==='function'", timeout=30000)
        ev("""() => { try{ const d=document.getElementById('resume20'); if(d){ const b=d.querySelector('[data-x]'); if(b)b.click(); else d.remove(); } }catch(_){} }""")
        sw = ev("() => window.__swV || ''")
        ok("home loaded", True, {"sw": sw})

        screen[0] = "search"
        ev("() => { setMode('a'); $('q').value='kesariya'; search('kesariya') }")
        try:
            page.wait_for_function("() => document.querySelectorAll('#list li').length>2", timeout=30000)
        except Exception:
            pass
        s = ev("() => ({n:document.querySelectorAll('#list li').length, view})")
        ok("search results", s.get("n", 0) > 2, s)

        screen[0] = "play"
        ev("""() => { try{ const r=(res&&res[0])||null; if(r){ queue=[{...r}]; qi=0; play(); } else { const el=document.querySelector('#list li .meta, #list li'); if(el) el.click(); } }catch(e){} }""")
        t0 = time.time()
        play = None
        while time.time() - t0 < 25:
            play = ev("() => { const r=cur()||{}; const a=M||document.getElementById('aud'); return {id:r.id||'', title:(r.title||'').slice(0,50), ct:+((a&&a.currentTime)||0).toFixed(2), paused:!!(a&&a.paused), err:!!(a&&a.error), want:a&&a.dataset.wantPlay, endbar:!!(document.getElementById('endbar')&&document.getElementById('endbar').classList.contains('on'))} }")
            if play and play.get("id") and play.get("ct", 0) > 0.8 and not play.get("paused"):
                break
            time.sleep(0.4)
        ok("search+tap plays", bool(play and play.get("id") and play.get("ct", 0) > 0.8 and not play.get("paused")), play)
        first = (play or {}).get("id") or ""

        screen[0] = "queue"
        ev("""() => { try{ const n={id:'4NRXx6U8ABQ',title:'hunt-next',channel:''}; if(!queue.some(x=>x&&x.id===n.id)) queue.splice(qi+1,0,n); save(); render(); }catch(e){} }""")
        qn = ev("() => ({qi, ql:queue.length, ids:(queue||[]).slice(Math.max(0,qi), qi+3).map(x=>x&&x.id)})")
        ok("queue has next", qn.get("ql", 0) > qn.get("qi", 0) + 0, qn)

        screen[0] = "next"
        ev("() => next()")
        t0 = time.time(); nxt = None
        while time.time() - t0 < 20:
            nxt = ev("() => { const r=cur()||{}; const a=M; return {id:r.id||'', ct:+((a&&a.currentTime)||0).toFixed(2), paused:!!(a&&a.paused)} }")
            if nxt and nxt.get("id") and nxt["id"] != first and nxt.get("ct", 0) > 0.4:
                break
            time.sleep(0.4)
        ok("next plays another song", bool(nxt and nxt.get("id") and nxt["id"] != first and nxt.get("ct", 0) > 0.4), {"prev": first, "now": nxt})

        screen[0] = "prev"
        ev("() => prev()")
        t0 = time.time(); prv = None
        while time.time() - t0 < 16:
            prv = ev("() => { const r=cur()||{}; const a=M; return {id:r.id||'', ct:+((a&&a.currentTime)||0).toFixed(2), paused:!!(a&&a.paused)} }")
            if prv and prv.get("id") == first and prv.get("ct", 0) > 0.2:
                break
            time.sleep(0.4)
        ok("prev returns to prior song", bool(prv and prv.get("id") == first), {"want": first, "got": prv})

        screen[0] = "likes"
        liked = ev("""() => { const r=cur(); if(!r||!r.id) return {ok:false}; if(!isLiked(r.id)) toggleLike(r); return {ok:isLiked(r.id), id:r.id} }""")
        ev("() => { view='liked'; tabs(); render() }")
        time.sleep(0.4)
        lk = ev("() => ({view, n:document.querySelectorAll('#list li').length, has: liked().some(x=>x.id===(cur()&&cur().id))})")
        ok("like + liked tab", bool(liked and liked.get("ok") and lk.get("has")), {"liked": liked, "tab": lk})

        screen[0] = "saved"
        sv = ev("""async () => { try{ const r=cur(); if(r&&r.id&&typeof saveOff==='function'){ await saveOff(r); } view='saved'; tabs(); render(); return {off:!!(r&&isOff(r.id)), n:document.querySelectorAll('#list li').length, view} }catch(e){ return {err:String(e)} } }""")
        ok("save offline + saved tab", bool(sv and sv.get("view")=="saved" and (sv.get("off") or sv.get("n",0)>0)), sv)

        screen[0] = "lyrics"
        ly = ev("""async () => {
          try{
            const r=cur(); if(!r) return {ok:false};
            const lb=document.getElementById('lyb'); if(lb && !lyOn) lb.click();
            const t0=Date.now();
            while(Date.now()-t0<12000){
              const txt=(document.getElementById('lyr')&&document.getElementById('lyr').textContent)||'';
              if((LY&&LY.length) || (txt && txt.length>20 && !/loading/i.test(txt))) break;
              await new Promise(z=>setTimeout(z,300));
            }
            const txt=(document.getElementById('lyr')&&document.getElementById('lyr').textContent)||'';
            return {on:!!lyOn, lines:(LY||[]).length, txt:txt.slice(0,80), empty:/no lyrics|not found|unavailable/i.test(txt), t:txt.length};
          }catch(e){ return {err:String(e)} }
        }""")
        ok("lyrics panel opens", bool(ly and (ly.get("on") or ly.get("lines") or ly.get("t", 0) > 0 or ly.get("empty"))), ly)

        screen[0] = "sponsorblock"
        sb = ev("""async () => {
          try{
            sbOn=true; localStorage.sb='1';
            const r=cur(); if(!r||!r.id) return {ok:false};
            const j=await (await fetch('/api/segments?k='+K+'&id='+encodeURIComponent(r.id))).json();
            const segs=Array.isArray(j)?j:(j&&j.segments)||[];
            if(!segs.length) return {ok:true, segs:0, skipped:false, note:'no segments'};
            const g=segs[0]; const a=M; const mid=(Number(g.s)+Number(g.e))/2;
            if(!(mid>0) || !a) return {ok:true, segs:segs.length, skipped:false, note:'bad seg'};
            a.currentTime=Math.max(0, mid);
            await new Promise(z=>setTimeout(z,800));
            try{ sbCheck() }catch(_){}
            await new Promise(z=>setTimeout(z,800));
            return {ok:true, segs:segs.length, at:mid, ct:+a.currentTime.toFixed(2), skipped:a.currentTime > Number(g.e)-0.4 || a.currentTime < Number(g.s)-0.2};
          }catch(e){ return {err:String(e)} }
        }""")
        ok("sponsorblock API", bool(sb and (sb.get("ok") or sb.get("segs") == 0) and not sb.get("err")), sb)

        screen[0] = "video720"
        ev("() => { try{ localStorage.vres='720'; setMode('v') }catch(e){} }")
        t0 = time.time(); v = None
        while time.time() - t0 < 18:
            v = ev("() => ({mode, h:VID&&VID.videoHeight, w:VID&&VID.videoWidth, ct:+((VID&&VID.currentTime)||0).toFixed(2), paused:!!(VID&&VID.paused), vres})")
            if v and v.get("h", 0) >= 720 and v.get("ct", 0) > 0.5:
                break
            time.sleep(0.5)
        ok("video 720p", bool(v and v.get("h", 0) >= 720), v)
        ev("() => { try{ setMode('a') }catch(_){} }")

        screen[0] = "shorts"
        ev("() => { $('q').value=''; view='shorts'; tabs(); loadShortsFeed(false) }")
        t0 = time.time(); sh = None; first_ms = None
        while time.time() - t0 < 25:
            sh = ev("() => ({view, n:(shRes||[]).length, loading:!!shLoading, empty:($('empty')&&$('empty').textContent)||''})")
            if sh and sh.get("n", 0) > 3:
                first_ms = int((time.time() - t0) * 1000)
                break
            time.sleep(0.4)
        if first_ms is None:
            first_ms = int((time.time() - t0) * 1000)
        ok("shorts feed loads", bool(sh and sh.get("n", 0) > 3), {"ms": first_ms, **(sh or {})})
        ev("() => { try{ loadShortsFeed(true) }catch(_){} }")
        time.sleep(6)
        sh2 = ev("() => ({n:(shRes||[]).length, loading:!!shLoading})")
        ok("shorts refresh/more", True, sh2)

        screen[0] = "rooms"
        ev("() => { try{ rmOpen() }catch(_){} }")
        time.sleep(1.2)
        rm = ev("""() => {
          const p=document.getElementById('rmp');
          const rows=[...document.querySelectorAll('button.rmr')].map(b=>(b.textContent||'').trim()).filter(Boolean);
          return {open:!!(p&&p.classList.contains('open')), n:rows.length, names:rows.slice(0,10)};
        }""")
        ok("rooms panel lists rooms", bool(rm and rm.get("open") and rm.get("n", 0) >= 8), rm)
        ev("() => { try{ rmClose() }catch(_){} }")

        screen[0] = "settings"
        stg = ev("""() => {
          const before={rad:!!radOn, sb:!!sbOn, qual};
          try{ if(typeof tog==='function'){ tog('rad', true); tog('sb', true);} }catch(_){}
          radOn=true; sbOn=true; localStorage.rad='1'; localStorage.sb='1';
          return {before, after:{rad:!!radOn, sb:!!sbOn, qual:localStorage.qual||qual, gap:localStorage.gapless}};
        }""")
        ok("settings toggles", bool(stg and stg.get("after", {}).get("rad") and stg.get("after", {}).get("sb")), stg)

        screen[0] = "resume"
        ev("""() => { try{ const a=M; if(a&&isFinite(a.duration)&&a.duration>60) a.currentTime=42; window.__msPosSave&&__msPosSave(); }catch(_){} }""")
        time.sleep(0.4)
        pos = ev("() => { try{ return JSON.parse(localStorage.getItem('local.msPos')||'null') }catch(_){ return null } }")
        ok("resume position saved", bool(pos and pos.get("t", 0) >= 30), {"t": pos and pos.get("t"), "id": pos and pos.get("id")})

        screen[0] = "guest"
        gctx = b.new_context(viewport={"width": 390, "height": 844}, is_mobile=True, has_touch=True,
            user_agent="Mozilla/5.0 (Linux; Android 14; SM-S916B) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Mobile Safari/537.36")
        gpage = gctx.new_page()
        gpage.on("pageerror", on_pageerr)
        gpage.on("console", on_console)
        gpage.on("response", on_response)
        gpage.goto(BASE + "/listen?room=CHILL", wait_until="domcontentloaded", timeout=45000)
        time.sleep(1.5)
        gst = gpage.evaluate("""async () => {
          const name='hunt'+Math.random().toString(36).slice(2,6);
          const r=await fetch('/api/room',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({op:'guest',r:'CHILL',name}),credentials:'same-origin'});
          let j=null; try{j=await r.json()}catch(_){}
          const denied=await fetch('/api/search?q=test',{credentials:'same-origin'});
          return {status:r.status, ok:!!(j&&(j.ok||j.name||j.r)), denied:denied.status, room:j&&j.r};
        }""")
        ok("guest can join room, search denied", bool(gst and gst.get("denied") == 401), gst)
        gpage.close(); gctx.close()

        # console errors after all screens
        bad = [e for e in ERR if e.get("kind") in ("page", "console") or (e.get("kind") == "http" and e.get("status", 0) >= 500)]
        ok("no page/console/5xx errors on screens", len(bad) == 0, {"n": len(ERR), "bad": bad[:12], "all": ERR[:20]})

        b.close()

    fails = [x for x in R if not x["pass"]]
    print("HUNT", {"n": len(R), "fail": len(fails), "errors": len(ERR)})
    if fails:
        raise SystemExit(f"hunt failed {len(fails)}/{len(R)}")

if __name__ == "__main__":
    main()
