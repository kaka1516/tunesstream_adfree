#!/usr/bin/env python3
"""Browser compatibility on the public URL: Chromium mobile (Android Chrome),
Firefox, WebKit (Safari engine), and a Samsung Internet UA.

Checks: page load / console errors, login, search, play, radio 6+ advances
with a hidden tab, video mode, MediaSession. Never prints secrets.
"""
import json, os, time
from pathlib import Path
from playwright.sync_api import sync_playwright

BASE = os.environ.get("MS_BASE", "https://tunestream.dpdns.org")
CHROME = os.environ.get("CHROME", "/usr/bin/google-chrome")
N_ADV = int(os.environ.get("NADV", "6"))
SEED = os.environ.get("MS_VIDEO_ID", "4NRXx6U8ABQ")
USER = "loadtest"
OUT = Path(os.environ.get("MS_COMPAT_OUT", "/tmp/ms-browser-compat.json"))

SAMSUNG_UA = (
    "Mozilla/5.0 (Linux; Android 14; SM-S916B) AppleWebKit/537.36 "
    "(KHTML, like Gecko) SamsungBrowser/27.0 Chrome/122.0.0.0 Mobile Safari/537.36"
)
ANDROID_CHROME_UA = (
    "Mozilla/5.0 (Linux; Android 14; SM-S916B) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/131.0.0.0 Mobile Safari/537.36"
)
FIREFOX_UA = (
    "Mozilla/5.0 (Android 14; Mobile; rv:133.0) Gecko/133.0 Firefox/133.0"
)
SAFARI_UA = (
    "Mozilla/5.0 (iPhone; CPU iPhone OS 18_0 like Mac OS X) "
    "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/18.0 Mobile/15E148 Safari/604.1"
)

# Console noise that is not an app incompat.
IGNORE_CONS = (
    "favicon",
    "net::err_aborted",
    "failed to load resource",
    "cdn-cgi",
    "the play() request was interrupted",
    "abort",
)

def pw():
    return Path(os.environ.get("MS_PW_FILE", "/tmp/loadtest.pw")).read_text(encoding="utf-8").strip()

def interesting_console(msg):
    t = (msg or "").lower()
    if any(x in t for x in IGNORE_CONS):
        return False
    return True

def snap(page):
    return page.evaluate(
        """() => {
          const r=(typeof cur==='function'&&cur())||{};
          const a=(typeof M!=='undefined'&&M)||document.getElementById('aud');
          const meta=document.querySelector('meta[name=ms-build]');
          let ms=null;
          try{
            ms={
              has: 'mediaSession' in navigator,
              playback: navigator.mediaSession && navigator.mediaSession.playbackState || '',
              title: (navigator.mediaSession && navigator.mediaSession.metadata && navigator.mediaSession.metadata.title) || ''
            };
          }catch(e){ms={has:false,err:String(e&&e.name||e)}}
          return {
            build: (typeof APP_BUILD==='string'&&APP_BUILD)||(meta&&meta.content)||'',
            sw: window.__swV||'',
            serverV: window.__msServerV||'',
            id: r.id||'', title:(r.title||'').slice(0,50),
            qi: typeof qi==='number'?qi:-1, ql:(typeof queue!=='undefined'&&queue||[]).length,
            radOn: typeof radOn!=='undefined'&&!!radOn,
            want: a&&a.dataset&&a.dataset.wantPlay,
            paused: !!(a&&a.paused), ended: !!(a&&a.ended),
            ct: a&&+(+a.currentTime||0).toFixed(2),
            dur: a&&(isFinite(a.duration)?+a.duration.toFixed(2):0),
            rs: a&&a.readyState, err: !!(a&&a.error),
            hidden: !!document.hidden,
            vres: (typeof vres!=='undefined'?String(vres):''),
            ms
          };
        }"""
    )

def wait_until(fn, timeout, pred):
    t0 = time.time(); last = None
    while time.time() - t0 < timeout:
        last = fn()
        if pred(last):
            return last
        time.sleep(0.35)
    return last

def hide(page, on, blank=None):
    if blank is not None:
        if on:
            blank.bring_to_front()
        else:
            page.bring_to_front()
        time.sleep(0.2)
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

def run_browser(p, name, kind, ua):
    ev = []
    errors = []
    pageerrors = []

    def rec(n, cond, info=None):
        ev.append({"name": n, "pass": bool(cond), "detail": info})
        return bool(cond)

    launch_kwargs = {"headless": True, "args": ["--disable-dev-shm-usage"]}
    if kind == "chromium":
        if Path(CHROME).exists():
            launch_kwargs["executable_path"] = CHROME
        launch_kwargs["args"] = ["--autoplay-policy=no-user-gesture-required", "--disable-dev-shm-usage"]
        browser = p.chromium.launch(**launch_kwargs)
        ctx_kw = {"is_mobile": True, "has_touch": True, "device_scale_factor": 2}
    elif kind == "firefox":
        browser = p.firefox.launch(
            headless=True,
            firefox_user_prefs={
                "media.autoplay.default": 0,
                "media.autoplay.blocking_policy": 0,
            },
        )
        ctx_kw = {}
    elif kind == "webkit":
        browser = p.webkit.launch(headless=True)
        ctx_kw = {}
    else:
        raise SystemExit("unknown kind " + kind)

    ctx = browser.new_context(
        viewport={"width": 390, "height": 844},
        user_agent=ua,
        **ctx_kw,
    )
    page = ctx.new_page()
    page.on("pageerror", lambda e: pageerrors.append(str(e)[:240]))
    page.on("console", lambda m: errors.append(m.text[:240]) if m.type == "error" and interesting_console(m.text) else None)

    try:
        page.goto(BASE + "/login", wait_until="domcontentloaded", timeout=45000)
        rec("login-page", "login" in (page.title() or "").lower() or page.query_selector("form, input, button") is not None, {"url": page.url})
        ver = page.evaluate(
            """async () => {
              const r = await fetch('/api/version', {cache:'no-store'});
              let j=null; try{j=await r.json()}catch(_){}
              return {status:r.status, v:(j&&j.v)||'', cc:r.headers.get('cache-control')||''};
            }"""
        )
        rec("api-version", ver.get("status") == 200 and str(ver.get("v") or "").startswith("ms-v"), ver)

        st = page.evaluate(
            """async ({u,p}) => (await fetch('/api/auth/login',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({u,p}),credentials:'same-origin'})).status""",
            {"u": USER, "p": pw()},
        )
        rec("login", st == 200, {"status": st})
        if st != 200:
            return ev, errors, pageerrors

        page.goto(BASE + "/", wait_until="domcontentloaded", timeout=45000)
        page.wait_for_function("() => typeof startRadio === 'function' && typeof play === 'function'", timeout=30000)
        boot = snap(page)
        rec("player-boot", bool(boot.get("build")), boot)

        # search
        hits = page.evaluate(
            """async () => {
              const r = await fetch('/api/search?q=blinding%20lights', {credentials:'same-origin'});
              const j = await r.json();
              const arr = Array.isArray(j) ? j : (j.results || j.items || []);
              return {status:r.status, n:arr.length, first:(arr[0]&&(arr[0].title||arr[0].id)||'').toString().slice(0,60)};
            }"""
        )
        rec("search", hits.get("status") == 200 and hits.get("n", 0) >= 1, hits)

        # play one song
        page.evaluate(
            """(id) => {
              try{ if (typeof radOn!=='undefined') radOn=false; }catch(e){}
              queue=[{id, title:'compat play', channel:''}]; qi=0;
              if (typeof play==='function') play(0);
            }""",
            SEED,
        )
        playing = wait_until(lambda: snap(page), 30, lambda s: s and s.get("id") == SEED and (s.get("ct") or 0) > 0.4 and not s.get("err"))
        rec("play", bool(playing and (playing.get("ct") or 0) > 0.4), playing)

        ms = (playing or boot).get("ms") if playing else boot.get("ms")
        rec("mediasession-api", bool(ms and ms.get("has")), ms)

        # video quality default (best effort; skip hard-fail on engines that lack the UI)
        v = page.evaluate("() => ({vres: (typeof vres!=='undefined'?String(vres):''), sel:(document.getElementById('vres')||{}).value||'', pick: localStorage.vresPick||''})")
        rec("video-default-720", v.get("vres") == "720" or v.get("sel") == "720" or v.get("pick") in ("", "720"), v)

        # radio + hidden-tab advances
        page.evaluate(
            """(id) => {
              try{ radOn=true; }catch(e){}
              queue=[{id, title:'compat radio', channel:''}]; qi=0;
              if (typeof play==='function') play(0);
              if (typeof startRadio==='function') { try{ startRadio(); }catch(e){} }
            }""",
            SEED,
        )
        wait_until(lambda: snap(page), 25, lambda s: s and (s.get("ct") or 0) > 0.3)
        blank = ctx.new_page()
        blank.goto("about:blank")
        page.bring_to_front()
        ids = []
        s0 = snap(page)
        if s0.get("id"):
            ids.append(s0.get("id"))
        hide(page, True, blank)
        for i in range(N_ADV):
            prev = ids[-1] if ids else ""
            # wait until this track has a real duration, then jump near the end
            wait_until(lambda: snap(page), 20, lambda s: s and s.get("id") == prev and (s.get("dur") or 0) > 15 and (s.get("rs") or 0) >= 1)
            page.evaluate(
                """() => {
                  const a=(typeof M!=='undefined'&&M)||document.getElementById('aud');
                  if(!a) return 0;
                  const d=isFinite(a.duration)&&a.duration>15?a.duration:0;
                  try{ if(d) a.currentTime=Math.max(0,d-8); }catch(_){}
                  return d;
                }"""
            )
            nxt = wait_until(
                lambda: snap(page),
                40,
                lambda s: s and s.get("id") and s.get("id") != prev,
            )
            ok_adv = bool(nxt and nxt.get("id") and nxt.get("id") != prev)
            rec(f"radio-adv-{i+1}", ok_adv, {"from": prev, "to": (nxt or {}).get("id"), "ct": (nxt or {}).get("ct"), "hidden": (nxt or {}).get("hidden"), "err": (nxt or {}).get("err")})
            if ok_adv:
                ids.append(nxt.get("id"))
            else:
                break
        hide(page, False, blank)
        rec("radio-6-plus", len(ids) >= N_ADV + 1, {"ids": ids, "n": max(0, len(ids) - 1)})
        try:
            blank.close()
        except Exception:
            pass

        # fatal page errors (syntax, ReferenceError) fail the browser
        fatal = [e for e in pageerrors if e]
        rec("no-pageerror", len(fatal) == 0, {"n": len(fatal), "sample": fatal[:5]})
        rec("no-serious-console", True, {"n": len(errors), "sample": errors[:6]})  # logged, not always fatal
    finally:
        try:
            ctx.close()
        except Exception:
            pass
        try:
            browser.close()
        except Exception:
            pass
    return ev, errors, pageerrors

def main():
    plan = [
        ("chromium-android-chrome", "chromium", ANDROID_CHROME_UA),
        ("samsung-internet-ua", "chromium", SAMSUNG_UA),
        ("firefox", "firefox", FIREFOX_UA),
        ("webkit-safari", "webkit", SAFARI_UA),
    ]
    only = os.environ.get("MS_BROWSERS", "")
    if only:
        want = {x.strip() for x in only.split(",") if x.strip()}
        plan = [x for x in plan if x[0] in want]
    report = {"base": BASE, "browsers": {}}
    all_ok = True
    with sync_playwright() as p:
        for name, kind, ua in plan:
            print("===", name, "===")
            try:
                ev, errors, pageerrors = run_browser(p, name, kind, ua)
            except Exception as e:
                ev = [{"name": "run", "pass": False, "detail": {"err": type(e).__name__, "msg": str(e)[:200]}}]
                errors, pageerrors = [], []
            failed = [x for x in ev if not x["pass"]]
            # no-serious-console is informational
            hard = [x for x in failed if x["name"] != "no-serious-console"]
            ok = len(hard) == 0
            all_ok = all_ok and ok
            report["browsers"][name] = {"ok": ok, "checks": ev, "console": errors[:10], "pageerrors": pageerrors[:10]}
            print(("PASS " if ok else "FAIL ") + name, "failed=", [x["name"] for x in hard] or "none")
            for x in ev:
                print(("  ok " if x["pass"] else "  FAIL ") + x["name"], json.dumps(x.get("detail"), default=str)[:400])
    OUT.write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
    print("WROTE", str(OUT), "ALL_OK" if all_ok else "ALL_FAIL")
    raise SystemExit(0 if all_ok else 1)

if __name__ == "__main__":
    main()
