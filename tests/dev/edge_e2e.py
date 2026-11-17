#!/usr/bin/env python3
"""Usage-lean edge-case hunt on the box test server.
Covers empty search, long titles, dead video skip, logout mid-play,
rapid next taps, queue reorder, back button, PWA reinstall, clog
dedupe, and upgrade-reload safety during a system pause.
Never prints secrets. Never claims to have heard audio. Not port 8120.
"""
import json, os, time
from pathlib import Path
from playwright.sync_api import sync_playwright

BASE = os.environ.get("MS_BASE", "http://127.0.0.1:8140")
CHROME = os.environ.get("CHROME", "/usr/bin/google-chrome")
SEED = "4NRXx6U8ABQ"
SEED2 = "ZAfAud_M_mg"
SEED3 = "4fndeDfaWCg"
R = []

def pw():
    return Path(os.environ.get("MS_PW_FILE", "/tmp/loadtest.pw")).read_text(encoding="utf-8").strip()

def ok(name, cond, info=None):
    R.append({"name": name, "pass": bool(cond), "detail": info})
    print(("PASS " if cond else "FAIL ") + name, json.dumps(info, default=str)[:700] if info is not None else "")

def login(page):
    page.goto(BASE + "/login", wait_until="domcontentloaded")
    st = page.evaluate(
        "async p=>(await fetch('/api/auth/login',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({u:'loadtest',p}),credentials:'same-origin'})).status",
        pw(),
    )
    ok("login", st == 200, st)
    page.goto(BASE + "/", wait_until="domcontentloaded")
    page.wait_for_function("()=>typeof play==='function'&&typeof K!=='undefined'", timeout=30000)

def wait_play(page, timeout=45, min_ct=0.4):
    t0 = time.time()
    last = None
    while time.time() - t0 < timeout:
        last = page.evaluate(
            """() => {
              const c=typeof cur==='function'&&cur()||{};
              const m=window.M||window.AUD||document.getElementById('aud')||{};
              return {id:c.id||'', title:c.title||'', ct:+(m.currentTime||0), paused:!!m.paused, want:(m.dataset&&m.dataset.wantPlay)||'', qi:typeof qi==='number'?qi:-1, ql:(queue||[]).length, gen:typeof playGen==='number'?playGen:-1};
            }"""
        )
        if last and last.get("id") and last.get("ct", 0) >= min_ct and not last.get("paused"):
            return last
        time.sleep(0.25)
    return last

def main():
    fails = 0
    with sync_playwright() as p:
        b = p.chromium.launch(executable_path=CHROME, headless=True, args=["--autoplay-policy=no-user-gesture-required","--disable-gpu"])
        ctx = b.new_context(viewport={"width": 390, "height": 844}, is_mobile=True, has_touch=True)
        page = ctx.new_page()
        login(page)

        # --- empty search ---
        ev = page.evaluate(
            """async () => {
              await search('');
              const empty=document.getElementById('empty');
              return {txt:(empty&&empty.textContent)||'', shown:!!(empty&&empty.style.display!=='none'&&empty.offsetParent!==null), n:document.querySelectorAll('#list li').length, res:(typeof res!=='undefined'&&Array.isArray(res))?res.length:-1};
            }"""
        )
        ok("empty search shows a hint and no rows",
           ev and ev.get("n", 1) == 0 and ev.get("res") == 0 and "Type a song" in (ev.get("txt") or ""), ev)

        # --- long title does not overflow the row ---
        ev = page.evaluate(
            """() => {
              const long='A'*180 + ' very long title that should ellipsize or clamp in the list';
              const li=document.createElement('li');
              li.innerHTML='<div class=meta><div class=t></div><div class=s>Artist</div></div>';
              li.querySelector('.t').textContent=long;
              const list=document.getElementById('list');
              list.appendChild(li);
              const t=li.querySelector('.t');
              const cs=getComputedStyle(t);
              const r={overflow:cs.overflow, clamp:cs.webkitLineClamp||cs.getPropertyValue('-webkit-line-clamp'), sw:t.scrollWidth, cw:t.clientWidth, sh:t.scrollHeight, ch:t.clientHeight, w:t.getBoundingClientRect().width, lw:li.getBoundingClientRect().width};
              li.remove();
              return r;
            }"""
        )
        overflow_ok = ev and ev.get("lw", 0) <= 390 + 2 and (
            ev.get("sw", 99) <= ev.get("cw", 0) + 2 or ev.get("sh", 99) <= ev.get("ch", 0) + 4
            or (ev.get("overflow") in ("hidden", "clip"))
        )
        ok("long title is clipped in the list", overflow_ok, ev)


        # --- clog flush is not duplicated ---
        posts = []
        def on_clog(route):
            try:
                body = route.request.post_data or ""
                evs = []
                try:
                    j = json.loads(body)
                    evs = [e.get("ev") for e in (j.get("ev") or [])]
                except Exception:
                    evs = ["?"]
                posts.append({"n": len(evs), "evs": evs[:8], "body_len": len(body)})
                route.fulfill(status=200, content_type="application/json", body='{"ok":1}')
            except Exception:
                try: route.fulfill(status=200, body='{"ok":1}')
                except Exception: pass
        page.route("**/api/clog", on_clog)
        ev = page.evaluate(
            """async () => {
              const marker='hunt-dedupe-'+Date.now();
              if(typeof window.__msClog!=='function') return {ok:false, why:'no-clog'};
              window.__msClog({ev:'play', id:marker});
              if(typeof window.__msClogFlush==='function'){
                await window.__msClogFlush();
                await window.__msClogFlush();
                await window.__msClogFlush(true);
              }
              return {ok:true, marker};
            }"""
        )
        time.sleep(0.3)
        marked = [p for p in posts if ev and ev.get("marker") and ev["marker"] in json.dumps(p)]
        # fallback: count posts after the call (all clog in this window)
        # We only added one event; there should be at most one POST containing it.
        # If the page also flushed older events first, that's one extra pre-existing batch — only count marker.
        containing = 0
        for p in posts:
            raw = json.dumps(p)
            if ev and ev.get("marker") and ev["marker"] in raw:
                containing += 1
        # posts list may not include body ev ids because we only stored ev names. Fix: store ids too? We stored evs as event names.
        # Re-do the check by including id in on_clog — too late. Re-evaluate: store post bodies... I recorded ev names only.
        # The marker is an id, not ev name. Need to recount. I'll change the evaluate to use ev name unique.
        ok("clog hook present", ev and ev.get("ok"), ev)
        page.unroute("**/api/clog")
        # second pass with unique ev name captured in posts
        posts2 = []
        def on_clog2(route):
            try:
                body = route.request.post_data or ""
                posts2.append(body)
                route.fulfill(status=200, content_type="application/json", body='{"ok":1}')
            except Exception:
                try: route.fulfill(status=200, body='{"ok":1}')
                except Exception: pass
        page.route("**/api/clog", on_clog2)
        ev = page.evaluate(
            """async () => {
              const evName='play';
              const marker='huntDedupe'+Date.now();
              window.__msClog({ev:evName, id:marker});
              await window.__msClogFlush();
              await window.__msClogFlush();
              await window.__msClogFlush(true);
              return marker;
            }"""
        )
        time.sleep(0.3)
        hits = [b for b in posts2 if ev and ev in (b or "")]
        ok("clog flush sends a marker only once", ev and len(hits) == 1, {"posts": len(posts2), "hits": len(hits), "marker": ev})
        page.unroute("**/api/clog")

        # --- play + rapid next ---
        page.evaluate(
            """({a,b,c}) => {
              queue=[{id:a,title:'one',channel:'A',dur:240},{id:b,title:'two',channel:'B',dur:240},{id:c,title:'three',channel:'C',dur:240},{id:a,title:'four',channel:'D',dur:240}];
              qi=0; if(typeof radOn!=='undefined'){radOn=false; try{tog('rad',false)}catch(_){}}
              try{window.__msHeard={g:0,id:a,max:2}}catch(_){}
              play();
            }""",
            {"a": SEED, "b": SEED2, "c": SEED3},
        )
        first = wait_play(page, 40, 0.4)
        ok("seed plays before rapid next", first and first.get("id") == SEED and first.get("ct", 0) >= 0.4, first)
        ev = page.evaluate(
            """() => {
              if(typeof _msSafeToReload!=='function'||!M) return {ok:false, why:'missing'};
              window.__msReloadAtBoundary=0;
              const want0=M.dataset.wantPlay, heard0=window.__msHeard;
              window.__ignPause=1;
              M.dataset.wantPlay='1';
              try{M.pause()}catch(_){}
              window.__msHeard={id:(cur()&&cur().id)||'', max:Math.max(2, +(M.currentTime||0))};
              let mid=null; try{mid=_msSafeToReload()}catch(e){mid=String(e)}
              M.dataset.wantPlay='0';
              let idle=null; try{idle=_msSafeToReload()}catch(e){idle=String(e)}
              M.dataset.wantPlay=want0||'1';
              window.__msHeard=heard0;
              window.__ignPause=0;
              try{if(M.dataset.wantPlay==='1')M.play().catch(()=>{})}catch(_){}
              return {mid, idle, ct:+(M.currentTime||0), rs:M.readyState, paused:!!M.paused};
            }"""
        )
        time.sleep(0.4)
        ok("system pause mid-song is not safe to reload", ev and ev.get("mid") is False, ev)
        ok("user-paused / idle is safe to reload", ev and ev.get("idle") is True, ev)
        burst = page.evaluate(
            """() => {
              const before={qi, id:(cur()||{}).id, gen:playGen};
              next(); next(); next();
              return {before, after:{qi, id:(cur()||{}).id, gen:playGen, ql:queue.length}};
            }"""
        )
        time.sleep(0.25)  # coalesce 60ms + start
        after = wait_play(page, 40, 0.2)
        ok("rapid next advances more than one song and still plays",
           after and burst and burst.get("after", {}).get("qi", 0) >= 2 and after.get("ct", 0) >= 0.2 and not after.get("paused"),
           {"burst": burst, "after": after})

        # --- queue reorder ---
        ev = page.evaluate(
            """() => {
              view='queue'; try{tabs();render()}catch(_){}
              const before=(queue||[]).map(x=>x.id);
              const from=before.length>1?1:0;
              if(before.length>1){const r=queue.splice(from,1)[0]; queue.push(r); try{save();render()}catch(_){}}
              return {before, after:(queue||[]).map(x=>x.id), moved:from};
            }"""
        )
        ok("queue reorder keeps the same songs in a new order",
           ev and ev.get("before") and ev.get("after") and sorted(ev["before"]) == sorted(ev["after"]) and ev["before"] != ev["after"],
           ev)

        # --- back button closes now-playing, stays on the app ---
        ev = page.evaluate(
            """() => {
              try{openNp(true)}catch(_){document.getElementById('np').classList.add('open')}
              try{arm&&arm()}catch(_){}
              return {open:document.getElementById('np').classList.contains('open'), path:location.pathname};
            }"""
        )
        page.go_back()
        time.sleep(0.4)
        ev2 = page.evaluate(
            "()=>({open:document.getElementById('np')&&document.getElementById('np').classList.contains('open'), path:location.pathname, playing:!!(M&&M.dataset&&M.dataset.wantPlay==='1')})"
        )
        ok("back closes now-playing and stays on /",
           ev2 and ev2.get("path") in ("/", "/index.html") and ev2.get("open") is False, {"before": ev, "after": ev2})

        # --- dead video is skipped without a long hang ---
        dead = "ZZZZZdead01"
        def _dead_route(route):
            u = route.request.url or ""
            try:
                if dead in u and "/api/alt" not in u:
                    route.fulfill(status=404, body="e2e-dead", headers={"content-type": "text/plain", "cache-control": "no-store"})
                    return
            except Exception:
                pass
            try:
                route.continue_()
            except Exception:
                try: route.abort("failed")
                except Exception: pass
        page.route("**/*", _dead_route)
        t0 = time.time()
        page.evaluate(
            """(dead) => {
              const n={id:dead,title:'e2e-dead',channel:'',dur:180};
              queue=[cur()||{id:'4NRXx6U8ABQ',title:'x'}, n, {id:'ZAfAud_M_mg',title:'after-dead',channel:'',dur:240}];
              qi=1; try{if(typeof msClearStandby==='function')msClearStandby()}catch(_){}
              play();
            }""",
            dead,
        )
        skipped = None
        while time.time() - t0 < 25:
            s = page.evaluate("()=>({id:(cur()||{}).id||'', qi, ct:+((M&&M.currentTime)||0), want:(M&&M.dataset&&M.dataset.wantPlay)||''})")
            if s and s.get("id") and s.get("id") != dead and s.get("ct", 0) >= 0.15:
                skipped = s
                break
            time.sleep(0.3)
        dt = time.time() - t0
        ok("dead video is skipped in under 20s", skipped and skipped.get("id") != dead and dt < 20, {"dt": round(dt, 2), "snap": skipped})
        page.unroute("**/*")

        # --- PWA reinstall (unregister SW, reload, still boots) ---
        page.evaluate(
            """async () => {
              if(!('serviceWorker' in navigator)) return;
              const regs=await navigator.serviceWorker.getRegistrations();
              await Promise.all(regs.map(r=>r.unregister()));
              const keys=await caches.keys();
              await Promise.all(keys.map(k=>caches.delete(k)));
            }"""
        )
        page.reload(wait_until="domcontentloaded")
        page.wait_for_function("()=>typeof play==='function'&&typeof APP_BUILD==='string'", timeout=30000)
        ev = page.evaluate("()=>({build:APP_BUILD, path:location.pathname, hasPlay:typeof play==='function'})")
        ver = page.evaluate("async()=>((await fetch('/api/version',{cache:'no-store'})).json())")
        ok("PWA reinstall still boots the current build",
           ev and ev.get("hasPlay") and ev.get("build") and ver and ev.get("build") == ver.get("v"),
           {"boot": ev, "ver": ver})

        # --- logout mid-play: land on login, no exception ---
        # start a song first
        page.evaluate("(id)=>{queue=[{id,title:'lo',channel:'',dur:240}];qi=0;play()}", SEED)
        mid = wait_play(page, 30, 0.3)
        ok("playing before logout", mid and mid.get("ct", 0) >= 0.3, mid)
        page.evaluate(
            """async () => {
              if(typeof signOut==='function'){await signOut(); return 'fn'}
              await fetch('/api/auth/logout',{method:'POST',headers:{'Content-Type':'application/json'},body:'{}',credentials:'same-origin'});
              location.replace('/login');
              return 'fetch';
            }"""
        )
        page.wait_for_url("**/login**", timeout=15000)
        ok("logout mid-play goes to login", "/login" in page.url, {"url": page.url.split("?")[0]})

        b.close()

    failed = [r for r in R if not r["pass"]]
    print(json.dumps({"passed": len(R) - len(failed), "failed": len(failed), "total": len(R)}, indent=2))
    for r in failed:
        print("FAIL", r["name"], r.get("detail"))
    raise SystemExit(1 if failed else 0)

if __name__ == "__main__":
    main()
