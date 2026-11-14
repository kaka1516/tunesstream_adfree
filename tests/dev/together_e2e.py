#!/usr/bin/env python3
"""Listen together: shared control, rooms list, chat, guest join, WebRTC (fake media).
Uses two logged-in contexts and a third guest context on the public URL. Never prints secrets."""
import json, os, time
from pathlib import Path
from playwright.sync_api import sync_playwright

BASE = os.environ.get("MS_BASE", "https://tunestream.dpdns.org")
USER = "loadtest"
CHROME = os.environ.get("CHROME", "/usr/bin/google-chrome")
R = []

def pw():
    return Path(os.environ.get("MS_PW_FILE", "/tmp/loadtest.pw")).read_text(encoding="utf-8").strip()

def ok(name, cond, info=None):
    R.append({"name": name, "pass": bool(cond), "detail": info})
    print(("PASS " if cond else "FAIL ") + name, json.dumps(info, default=str)[:800] if info is not None else "")

def login(page, user=USER):
    page.goto(BASE + "/login", wait_until="domcontentloaded", timeout=45000)
    st = page.evaluate(
        """async ({u,p}) => {
          const r = await fetch('/api/auth/login', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({u,p}), credentials:'same-origin'});
          return r.status;
        }""",
        {"u": user, "p": pw()},
    )
    if st != 200:
        raise SystemExit("login failed %s" % st)
    page.goto(BASE + "/", wait_until="domcontentloaded", timeout=45000)
    page.wait_for_function("() => typeof roomJoin === 'function' || typeof roomPush === 'function'", timeout=30000)

def ctx(browser, guest=False):
    kwargs = dict(viewport={"width": 390, "height": 844}, is_mobile=True, has_touch=True, device_scale_factor=2,
                  user_agent="Mozilla/5.0 (Linux; Android 14; SM-S916B) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Mobile Safari/537.36",
                  permissions=["microphone"] if not guest else ["microphone"])
    c = browser.new_context(**kwargs)
    p = c.new_page()
    return c, p

def wait_id(page, timeout=25000):
    t0 = time.time()
    while time.time() - t0 < timeout / 1000:
        try:
            d = page.evaluate("() => {const c=typeof cur==='function'&&cur(); return {id:(c&&c.id)||'', ct: (window.AUD||document.getElementById('aud')||{}).currentTime||0, paused: !!(window.AUD||document.getElementById('aud')||{}).paused}}")
            if d and d.get("id"):
                return d
        except Exception:
            pass
        time.sleep(0.4)
    return {}

def main():
    with sync_playwright() as p:
        b = p.chromium.launch(executable_path=CHROME, headless=True, args=[
            "--autoplay-policy=no-user-gesture-required", "--disable-dev-shm-usage",
            "--use-fake-ui-for-media-stream", "--use-fake-device-for-media-stream",
            "--disable-features=WebRtcHideLocalIpsWithMdns",
        ])
        ca, pa = ctx(b); cb, pb = ctx(b); cg, pg = ctx(b, guest=True)
        login(pa); login(pb)
        # API: 10 rooms + shared control without host key
        api = pa.evaluate("""async () => {
          const j = async (op, body, method='POST') => {
            const r = await fetch('/api/room'+(method==='GET'?('?op='+op):''), {method, credentials:'same-origin', headers:{'Content-Type':'application/json'}, body: method==='POST'?JSON.stringify(Object.assign({op}, body||{})):undefined, cache:'no-store'});
            return r.json();
          };
          const lst = await j('list', null, 'GET');
          const s1 = await j('set', {r:'FOCUS', id:'4NRXx6U8ABQ', t:5, p:1, title:'Me at the zoo', channel:'jawed'});
          return {n:(lst.rooms||[]).length, names:(lst.rooms||[]).map(x=>x.r), v:s1.v, ok:s1.ok, shared:!!lst.shared};
        }""")
        ok("ten permanent rooms", api.get("n", 0) >= 10 and "MAIN" in api.get("names", []), api)
        ok("shared set without host key", bool(api.get("ok")) and int(api.get("v") or 0) >= 1, api)

        # A starts / B follows on FOCUS, then B pauses and A follows, B seeks, A changes track
        for pgx, name in ((pa, "A"), (pb, "B")):
            pgx.wait_for_function("() => typeof window.roomJoin==='function' && typeof window.roomStart==='function'", timeout=30000)
            pgx.evaluate("() => window.roomJoin('FOCUS')")
        time.sleep(1.2)
        pa.evaluate("() => { queue=[{id:'4NRXx6U8ABQ',title:'Me at the zoo',channel:'jawed'}]; qi=0; return play(3); }")
        t0 = time.time(); a_id = ""; followed = False
        while time.time() - t0 < 25:
            ba = wait_id(pb, 2000); aa = wait_id(pa, 1000)
            if ba.get("id") == "4NRXx6U8ABQ" and aa.get("id") == "4NRXx6U8ABQ":
                followed = True; break
        ok("B follows A's track", followed, {"A": wait_id(pa, 1000), "B": wait_id(pb, 1000)})
        time.sleep(2.5)

        pb.evaluate("""() => {
          const a=document.getElementById('aud');
          if(!a || a.paused) return {already:true, want:a&&a.dataset.wantPlay};
          const btn=document.getElementById('pp');
          if(btn) btn.click();
          else { a.dataset.wantPlay='0'; a.pause(); }
          return {paused:a.paused, want:a.dataset.wantPlay};
        }""")
        t0 = time.time(); paused = False
        while time.time() - t0 < 12:
            aa = pa.evaluate("() => !!(document.getElementById('aud')||{}).paused")
            if aa: paused = True; break
            time.sleep(0.5)
        ok("A follows B's pause", paused)

        pb.evaluate("() => { const a=document.getElementById('aud'); if(a) a.currentTime = 8; }")
        t0 = time.time(); seeked = False
        while time.time() - t0 < 12:
            ct = pa.evaluate("() => (document.getElementById('aud')||{}).currentTime||0")
            if ct and abs(ct - 8) < 3: seeked = True; break
            time.sleep(0.5)
        ok("A follows B's seek", seeked, {"ct": pa.evaluate("() => (document.getElementById('aud')||{}).currentTime||0")})

        pb.evaluate("() => { queue=[{id:'oHg5SJYRHA0',title:'Rick Astley',channel:'RickAstley'}]; qi=0; return play(2); }")
        t0 = time.time(); switched = False
        while time.time() - t0 < 25:
            aa = wait_id(pa, 2000)
            if aa.get("id") == "oHg5SJYRHA0":
                switched = True; break
        ok("A follows B's song change", switched, wait_id(pa, 1000))

        # chat both ways
        pa.evaluate("() => { if (typeof rmOpen==='function') rmOpen(); else { const p=document.getElementById('rmp'); if(p) p.classList.add('open'); } }")
        pb.evaluate("() => { if (typeof rmOpen==='function') rmOpen(); else { const p=document.getElementById('rmp'); if(p) p.classList.add('open'); } }")
        time.sleep(0.8)
        chat = pa.evaluate("""async () => {
          const j = await (await fetch('/api/room',{method:'POST',credentials:'same-origin',headers:{'Content-Type':'application/json'},body:JSON.stringify({op:'chat',r:'FOCUS',m:'hello from A <tag>'})})).json();
          return j;
        }""")
        ok("A chat accepted", bool(chat.get("ok")), {"id": chat.get("id")})
        t0 = time.time(); seen = False
        while time.time() - t0 < 10:
            html = pb.evaluate("() => (document.getElementById('rmchat')||{}).innerHTML||''")
            if "hello from A" in html and "<tag>" not in html:
                seen = True; break
            if "hello from A" in html and "&lt;tag&gt;" in html:
                seen = True; break
            time.sleep(0.5)
            try: pb.evaluate("() => roomPull && roomPull()")
            except Exception: pass
        ok("B sees escaped chat", seen, {"html": (pb.evaluate("() => (document.getElementById('rmchat')||{}).innerHTML||''") or "")[:200]})

        # guest in third context
        time.sleep(1)
        resp = pg.goto(BASE + "/listen?room=FOCUS", wait_until="domcontentloaded", timeout=45000)
        try:
            pg.wait_for_function("() => document.getElementById('rmp') && window.__msListen", timeout=30000)
        except Exception as e:
            body = ""
            try: body = pg.content()[:1500]
            except Exception: pass
            ok("guest /listen loads", False, {"err": str(e)[:200], "url": pg.url, "status": getattr(resp, "status", None), "body": body})
            # skip remaining guest/webrtc if listen page failed
            b.close()
            failed = [x for x in R if not x["pass"]]
            print("TOGETHER", json.dumps({"n": len(R), "fail": len(failed), "results": R}, default=str))
            raise SystemExit(1)
        guest_boot = pg.evaluate("() => window.__msListen")
        ok("guest /listen loads", bool(guest_boot and guest_boot.get("guest") and document_has(pg)), guest_boot)
        jn = pg.evaluate("""async () => {
          try { if(window.__msListen) window.__msListen.name='GuestPal';
            const r = await roomJoin('FOCUS', true);
            return {ok:true, rm: RM && RM.r, err: window.__joinErr||null};
          } catch(e) { return {ok:false, err:String(e)} }
        }""")
        t0 = time.time(); gjoin = False; gid = ""
        while time.time() - t0 < 30:
            d = wait_id(pg, 2000)
            if d.get("id"):
                gjoin = True; gid = d["id"]; break
            time.sleep(0.4)
        ok("guest follows current track", gjoin, {"id": gid, "join": jn})
        # guest cannot search
        st = pg.evaluate("async () => (await fetch('/api/search?q=hello',{credentials:'same-origin'})).status")
        ok("guest search denied", st in (401, 403), {"status": st})
        # guest pause should reach A
        pg.evaluate("""() => {
          const a=document.getElementById('aud');
          if(!a || a.paused) return {already:true, want:a&&a.dataset.wantPlay};
          const btn=document.getElementById('pp');
          if(btn) btn.click();
          else { a.dataset.wantPlay='0'; a.pause(); }
          return {paused:a.paused, want:a.dataset.wantPlay};
        }""")
        t0 = time.time(); gpaused = False
        while time.time() - t0 < 12:
            if pa.evaluate("() => !!(document.getElementById('aud')||{}).paused"):
                gpaused = True; break
            time.sleep(0.5)
        ok("logged-in follows guest pause", gpaused)

        # WebRTC: A and B join voice, wait for connected
        for pgx in (pa, pb):
            pgx.evaluate("""async () => {
              try { if (typeof rmOpen==='function') rmOpen(); if (typeof vcJoin==='function') await vcJoin(); if (typeof vcMic==='function') await vcMic(); } catch(e) { window.__vcErr=String(e) }
            }""")
        t0 = time.time(); rtc = {"A": "", "B": ""}
        while time.time() - t0 < 25:
            rtc = {
                "A": pa.evaluate("() => Object.values(VC&&VC.pcs||{}).map(pc=>pc.connectionState||pc.iceConnectionState).join(',')"),
                "B": pb.evaluate("() => Object.values(VC&&VC.pcs||{}).map(pc=>pc.connectionState||pc.iceConnectionState).join(',')"),
            }
            if any(s in (rtc["A"]+rtc["B"]) for s in ("connected", "completed")):
                break
            time.sleep(0.5)
        ok("webrtc peer connected (fake media)", any(s in (rtc["A"]+rtc["B"]) for s in ("connected", "completed")), rtc)
        # music still defined after voice
        ok("audio element intact after voice", pa.evaluate("() => !!(document.getElementById('aud'))") and pb.evaluate("() => !!(document.getElementById('aud'))"))

        pa.evaluate("() => { try{vcHang()}catch(e){} try{roomLeave()}catch(e){} }")
        pb.evaluate("() => { try{vcHang()}catch(e){} try{roomLeave()}catch(e){} }")
        pg.evaluate("() => { try{roomLeave()}catch(e){} }")
        b.close()
    failed = [x for x in R if not x["pass"]]
    print("TOGETHER", json.dumps({"n": len(R), "fail": len(failed), "results": R}, default=str))
    raise SystemExit(1 if failed else 0)

def document_has(page):
    try:
        return page.evaluate("() => !!document.getElementById('rmp')")
    except Exception:
        return False

if __name__ == "__main__":
    main()
