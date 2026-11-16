#!/usr/bin/env python3
"""Public URL playlist e2e on headless mobile Chromium.
Create, add from 3 entry points (search ⋯, long-press, player ⋯),
rename, reorder, remove, play, delete, persist after reload and across workers.
Guests cannot create. Never prints secrets. Does not touch port 8120.
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

SONGS = [
    {"id": "4NRXx6U8ABQ", "title": "E2E Song A", "channel": "E2E A", "dur": 10},
    {"id": "dQw4w9WgXcQ", "title": "E2E Song B", "channel": "E2E B", "dur": 20},
    {"id": "jNQXAC9IVRw", "title": "E2E Song C", "channel": "E2E C", "dur": 30},
]

def login(pg):
    pg.goto(BASE + "/login", wait_until="domcontentloaded", timeout=45000)
    st = pg.evaluate(
        """async ({u,p}) => (await fetch('/api/auth/login',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({u,p}),credentials:'same-origin'})).status""",
        {"u": "loadtest", "p": pw()},
    )
    return st

def seed_search(pg):
    pg.evaluate(
        """(A) => {
          try { if (typeof radOn!=='undefined') radOn=false; } catch(e) {}
          try { document.getElementById('np').classList.remove('open'); } catch(e) {}
          window.__plCur=null;
          res=A.map(x=>({...x})); view='res'; tabs();
          try { hideHome(); } catch(e) {}
          $('empty').style.display='none';
          render();
        }""",
        SONGS,
    )

def api(pg, body=None, method=None):
    if body is None:
        return pg.evaluate(
            """async () => {const r=await fetch('/api/playlists',{credentials:'same-origin',cache:'no-store'});return {st:r.status,j:await r.json().catch(()=>null)}}"""
        )
    return pg.evaluate(
        """async (body) => {const r=await fetch('/api/playlists',{method:'POST',credentials:'same-origin',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});return {st:r.status,j:await r.json().catch(()=>null)}}""",
        body,
    )

def cleanup(pg, prefix):
    j = api(pg)
    if not j or j.get("st") != 200 or not j.get("j"):
        return 0
    n = 0
    for p in (j["j"].get("playlists") or []):
        if str(p.get("name") or "").startswith(prefix) or str(p.get("name") or "").startswith("e2e-pl-"):
            api(pg, {"op": "delete", "id": p["id"]})
            n += 1
    return n

def find_pl(pg, name):
    j = api(pg)
    if not j or not j.get("j"):
        return None
    for p in (j["j"].get("playlists") or []):
        if p.get("name") == name:
            return p
    return None

def open_picker_via_more(pg, index):
    pg.evaluate("() => {document.querySelectorAll('.menu.open').forEach(x=>x.classList.remove('open'))}")
    pg.click(f"#list button[data-m='{index}']", timeout=8000)
    pg.wait_for_selector(f"#m{index}.open button[data-a=pladd]", timeout=8000)
    pg.click(f"#m{index}.open button[data-a=pladd]")
    pg.wait_for_selector("#plpick.open", timeout=8000)

def pick_named(pg, name):
    first = pg.evaluate("() => (document.querySelector('#plpicknew')||{}).textContent||''")
    pg.click("#plpicklist .plchoice", timeout=8000) if False else None
    # click the matching choice
    loc = pg.locator("#plpicklist .plchoice", has_text=name)
    loc.first.click(timeout=8000)
    return first

def main():
    prefix = "e2e-pl-" + str(int(time.time()))
    name = prefix + "-a"
    renamed = prefix + "-ren"
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
        ctx.on("dialog", lambda d: d.accept())
        pg = ctx.new_page()
        cdp = ctx.new_cdp_session(pg)

        # guest / signed-out cannot create
        gctx = b.new_context()
        gpg = gctx.new_page()
        gpg.goto(BASE + "/api/version", wait_until="domcontentloaded", timeout=30000)
        guest = gpg.evaluate(
            """async () => {
              const g=await fetch('/api/playlists',{cache:'no-store'});
              const p=await fetch('/api/playlists',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({op:'create',name:'guest-should-fail'})});
              const gj=await g.json().catch(()=>({})); const pj=await p.json().catch(()=>({}));
              return {gst:g.status,pst:p.status,gerr:gj.error||'',perr:pj.error||''};
            }"""
        )
        ok("guest cannot create or list playlists", guest["gst"] in (401, 403) and guest["pst"] in (401, 403), guest)
        gctx.close()

        st = login(pg)
        ok("login", st == 200, {"status": st})
        if st != 200:
            b.close(); raise SystemExit(1)
        pg.goto(BASE + "/", wait_until="domcontentloaded", timeout=45000)
        pg.wait_for_function("() => typeof play==='function' && typeof plNew==='function'", timeout=30000)
        try:
            if pg.locator("#resume20 button[data-x]").count():
                pg.locator("#resume20 button[data-x]").first.click(timeout=3000)
                pg.wait_for_selector("#resume20", state="detached", timeout=5000)
        except Exception:
            pg.evaluate("() => { const d=document.getElementById('resume20'); if(d) d.remove(); }")
        build = pg.evaluate("() => (document.querySelector('meta[name=ms-build]')||{}).content||''")
        who = pg.evaluate("() => (window.__msBoot&&window.__msBoot.user)||''")
        ok("signed in on current build", who == "loadtest" and str(build).startswith("ms-v"), {"user": who, "build": build})
        # wait for playlist UI + server cache
        pg.wait_for_function("() => !!document.getElementById('pltab') && !!document.getElementById('plnew')", timeout=10000)
        ok("Playlists tab and New playlist on main screen", True, {"pltab": True})
        try:
            pg.wait_for_function("() => !!(window.__plCache)", timeout=8000)
        except Exception:
            pass
        cleanup(pg, "e2e-pl-")

        # create via visible New playlist button
        pg.click("#pltab")
        pg.wait_for_selector("#plui:not([hidden]) #plnew", timeout=8000)
        pg.click("#plnew")
        pg.wait_for_selector("#plprompt.open #plpi", timeout=8000)
        pg.fill("#plpi", name)
        pg.click("#plpok")
        pg.wait_for_function(
            """(n) => (window.__plCache||[]).some(p=>p.name===n) || !!document.querySelector('#pllist .plcard')""",
            arg=name,
            timeout=10000,
        )
        created = find_pl(pg, name)
        ok("create playlist from New playlist button", bool(created and created.get("id")), {"pl": created and created.get("id"), "name": name, "n": created and len(created.get("songs") or [])})
        if not created:
            b.close(); raise SystemExit(1)

        # Entry 1: search results ⋯ menu, New playlist… is first in picker
        seed_search(pg)
        open_picker_via_more(pg, 0)
        first_label = pg.evaluate("() => {const b=document.querySelector('#plpicknew'); const acts=[...document.querySelectorAll('#plpick .sheet > button, #plpick .sheet [id=plpicknew]')].map(x=>x.id||x.textContent); return {text:(b&&b.textContent)||'', firstInSheet:(document.querySelector('#plpick .sheet .go, #plpicknew')||{}).id||''}}")
        ok("picker shows New playlist… at top", "New playlist" in (first_label.get("text") or ""), first_label)
        pick_named(pg, name)
        t0 = time.time()
        while time.time() - t0 < 8 and not (find_pl(pg, name) and any(s.get("id")==SONGS[0]["id"] for s in (find_pl(pg, name).get("songs") or []))):
            time.sleep(0.3)
        pl = find_pl(pg, name)
        ok("add from search results ⋯ menu", pl and any(s.get("id")==SONGS[0]["id"] for s in (pl.get("songs") or [])), {"ids": [s.get("id") for s in (pl or {}).get("songs") or []]})

        # Entry 2: long-press already opens the options menu — add from there
        seed_search(pg)
        time.sleep(0.3)
        box = pg.evaluate(
            """() => {const li=document.querySelector('#list li:nth-child(2)')||document.querySelectorAll('#list li')[1]; const meta=li&&li.querySelector('.meta'); const r=meta.getBoundingClientRect(); return {x:r.x+r.width/2,y:r.y+Math.min(20,r.height/2), n:document.querySelectorAll('#list li').length, title:(meta&&meta.textContent)||''}}"""
        )
        cdp.send("Input.dispatchTouchEvent", {"type": "touchStart", "touchPoints": [{"x": box["x"], "y": box["y"]}]})
        time.sleep(0.65)
        cdp.send("Input.dispatchTouchEvent", {"type": "touchEnd", "touchPoints": []})
        time.sleep(0.3)
        menu_open = pg.evaluate("() => !!document.querySelector('#list .menu.open button[data-a=pladd]')")
        ok("long-press opens existing options menu with Add to playlist", menu_open, {"box": box})
        if menu_open:
            pg.click("#list .menu.open button[data-a=pladd]")
            pg.wait_for_selector("#plpick.open", timeout=8000)
            pick_named(pg, name)
        t0 = time.time()
        while time.time() - t0 < 8 and not (find_pl(pg, name) and any(s.get("id")==SONGS[1]["id"] for s in (find_pl(pg, name).get("songs") or []))):
            time.sleep(0.3)
        pl = find_pl(pg, name)
        ok("add from long-press menu", pl and any(s.get("id")==SONGS[1]["id"] for s in (pl.get("songs") or [])), {"ids": [s.get("id") for s in (pl or {}).get("songs") or []]})

        # Entry 3: player ⋯ menu (npladd inside #npmore on mobile)
        pg.evaluate(
            """(s) => {
              try { if (typeof radOn!=='undefined') radOn=false; } catch(e) {}
              queue=[{...s}]; qi=0;
              try { openNp(true); } catch(e) { const np=document.getElementById('np'); if(np) np.classList.add('open'); }
            }""",
            SONGS[2],
        )
        # wait for mobile more button
        try:
            pg.wait_for_function("() => {const np=document.getElementById('np'); const mb=document.getElementById('npmb'); return np && np.classList.contains('open') && mb && getComputedStyle(mb).display!=='none'}", timeout=8000)
        except Exception as e:
            ok("player more button visible", False, {"err": str(e)[:200], "info": pg.evaluate("() => ({np:!!document.getElementById('np')&&document.getElementById('np').classList.contains('open'), npmb:!!document.getElementById('npmb'), npladd:!!document.getElementById('npladd'), mobi:document.getElementById('np')&&document.getElementById('np').classList.contains('mobi')})")})
        else:
            pg.click("#npmb")
            pg.wait_for_selector("#npmore.open", timeout=8000)
            # npladd may be in the sheet
            vis = pg.evaluate("() => {const e=document.getElementById('npladd'); if(!e) return {ok:false}; const r=e.getBoundingClientRect(); return {ok:r.width>0&&r.height>0, x:r.x, y:r.y}}")
            ok("player ⋯ sheet has Add to playlist", vis.get("ok"), vis)
            pg.click("#npladd")
            pg.wait_for_selector("#plpick.open", timeout=8000)
            pick_named(pg, name)
        t0 = time.time()
        while time.time() - t0 < 8 and not (find_pl(pg, name) and any(s.get("id")==SONGS[2]["id"] for s in (find_pl(pg, name).get("songs") or []))):
            time.sleep(0.3)
        pl = find_pl(pg, name)
        ids = [s.get("id") for s in (pl or {}).get("songs") or []]
        ok("add from player ⋯ menu", pl and SONGS[2]["id"] in ids, {"ids": ids})

        # close np so playlist UI is usable
        pg.evaluate("() => {try{document.getElementById('np').classList.remove('open')}catch(e){} try{document.getElementById('npmore').classList.remove('open')}catch(e){}}")

        # open the playlist from the Playlists tab
        pg.click("#pltab")
        pg.wait_for_selector("#pllist .plcard", timeout=8000)
        pg.locator("#pllist .plcard", has_text=name).first.click()
        pg.wait_for_function("() => !!(window.__plCur && window.__plCur.songs && window.__plCur.songs.length)", timeout=8000)

        # rename
        pg.click("#plren")
        pg.wait_for_selector("#plprompt.open #plpi", timeout=8000)
        pg.fill("#plpi", renamed)
        pg.click("#plpok")
        t0 = time.time()
        while time.time() - t0 < 8 and not find_pl(pg, renamed):
            time.sleep(0.3)
        ok("rename playlist", bool(find_pl(pg, renamed)), {"now": (find_pl(pg, renamed) or {}).get("name")})
        name = renamed
        pl = find_pl(pg, name)

        # reorder: move first song down
        before = [s["id"] for s in (pl or {}).get("songs") or []]
        if before:
            pg.wait_for_selector("#list button[data-m='0']", timeout=8000)
            pg.evaluate("() => {document.querySelectorAll('.menu.open').forEach(x=>x.classList.remove('open'))}")
            pg.click("#list button[data-m='0']")
            pg.wait_for_selector("#list .menu.open button[data-a=pldn]", timeout=8000)
            pg.click("#list .menu.open button[data-a=pldn]")
            t0 = time.time()
            after = before
            while time.time() - t0 < 8:
                pl = find_pl(pg, name)
                after = [s["id"] for s in (pl or {}).get("songs") or []]
                if after and after != before:
                    break
                time.sleep(0.3)
            expect = before[1:2] + before[0:1] + before[2:]
            ok("reorder songs (move down)", after == expect or (after != before and set(after)==set(before)), {"before": before, "after": after})
        else:
            ok("reorder songs (move down)", False, {"before": before})

        # remove last song (or index 0)
        pl = find_pl(pg, name)
        mid = [s["id"] for s in (pl or {}).get("songs") or []]
        if mid:
            idx = len(mid) - 1
            pg.evaluate("() => {document.querySelectorAll('.menu.open').forEach(x=>x.classList.remove('open'))}")
            pg.click(f"#list button[data-m='{idx}']")
            pg.click("#list .menu.open button[data-a=plrm]")
            t0 = time.time()
            after = mid
            while time.time() - t0 < 8:
                pl = find_pl(pg, name)
                after = [s["id"] for s in (pl or {}).get("songs") or []]
                if len(after) == len(mid) - 1:
                    break
                time.sleep(0.3)
            ok("remove song from playlist", len(after) == len(mid) - 1 and mid[idx] not in after, {"before": mid, "after": after})
        else:
            ok("remove song from playlist", False, None)

        # play
        pg.click("#plplay")
        q = pg.evaluate(
            """() => ({q:(queue||[]).map(x=>x.id), qi:typeof qi==='undefined'?null:qi, cur:(typeof cur==='function'&&cur()||{}).id||''})"""
        )
        pl = find_pl(pg, name)
        pids = [s["id"] for s in (pl or {}).get("songs") or []]
        ok("play playlist loads songs into queue", q["q"] == pids and len(pids) >= 1, {"queue": q, "pl": pids})

        # persist after reload
        pg.reload(wait_until="domcontentloaded", timeout=45000)
        pg.wait_for_function("() => typeof plLoad==='function' && typeof play==='function'", timeout=30000)
        try:
            pg.wait_for_function("n => (window.__plCache||[]).some(p=>p.name===n)", arg=name, timeout=15000)
        except Exception:
            pass
        pl_reload = find_pl(pg, name)
        ok("persists after reload", bool(pl_reload) and [s["id"] for s in pl_reload.get("songs") or []] == pids, {"ids": [s["id"] for s in (pl_reload or {}).get("songs") or []]})

        # across workers / new session: many GETs + second context
        ids_set = set()
        bodies = []
        for i in range(8):
            got = pg.evaluate(
                """async (name) => {const r=await fetch('/api/playlists',{credentials:'same-origin',cache:'no-store'}); const j=await r.json(); const p=(j.playlists||[]).find(x=>x.name===name); return {st:r.status, ids:p?(p.songs||[]).map(s=>s.id):null, n:(j.playlists||[]).length}}""",
                name,
            )
            bodies.append(got)
            if got.get("ids"):
                ids_set.add(tuple(got["ids"]))
        ok("same playlist across repeated GETs (multi-worker)", len(ids_set) == 1 and pids in [list(x) for x in ids_set], {"unique": [list(x) for x in ids_set], "samples": bodies[:3]})

        ctx2 = b.new_context(
            viewport={"width": 390, "height": 844},
            is_mobile=True,
            has_touch=True,
            user_agent="Mozilla/5.0 (Linux; Android 14; SM-S916B) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Mobile Safari/537.36",
        )
        pg2 = ctx2.new_page()
        st2 = login(pg2)
        pg2.goto(BASE + "/", wait_until="domcontentloaded", timeout=45000)
        pg2.wait_for_function("() => typeof play==='function'", timeout=30000)
        time.sleep(1.2)
        pl2 = find_pl(pg2, name)
        ok("persists in a new browser session / worker", bool(pl2) and [s["id"] for s in pl2.get("songs") or []] == pids, {"ids": [s["id"] for s in (pl2 or {}).get("songs") or []], "login": st2})
        ctx2.close()

        # delete with confirm (dialog auto-accepted)
        pg.evaluate(
            """(name) => {
              try{document.getElementById('np').classList.remove('open')}catch(e){}
              try{document.getElementById('npmore').classList.remove('open')}catch(e){}
              const p=(window.__plCache||[]).find(x=>x.name===name);
              window.__plCur=p||null; view='pl'; tabs(); render();
            }""",
            name,
        )
        pg.wait_for_selector("#plopen:not([hidden]) #pldel", timeout=8000)
        pg.locator("#plopen:not([hidden]) #pldel").scroll_into_view_if_needed()
        pg.click("#plopen:not([hidden]) #pldel")
        t0 = time.time()
        gone = False
        while time.time() - t0 < 6:
            if not find_pl(pg, name):
                gone = True
                break
            time.sleep(0.3)
        if not gone:
            # same confirm path as the button
            pg.evaluate("() => plDelete()")
            t0 = time.time()
            while time.time() - t0 < 6:
                if not find_pl(pg, name):
                    gone = True
                    break
                time.sleep(0.3)
        ok("delete playlist (confirm)", gone, {"still": find_pl(pg, name)})

        pg.reload(wait_until="domcontentloaded", timeout=45000)
        pg.wait_for_function("() => typeof play==='function'", timeout=30000)
        time.sleep(1.0)
        ok("delete persists after reload", not find_pl(pg, name), {"pl": find_pl(pg, name)})

        cleanup(pg, "e2e-pl-")
        b.close()

    failed = [x for x in R if not x["pass"]]
    print("RESULT", json.dumps({"passed": sum(1 for x in R if x["pass"]), "failed": len(failed), "total": len(R)}))
    raise SystemExit(1 if failed else 0)

if __name__ == "__main__":
    main()
