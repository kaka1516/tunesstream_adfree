#!/usr/bin/env python3
"""Reproduce the v109 Android radio swap-fail cascade.

Standby is forced to rs=0 / src-cleared at each advance, under mobile
emulation, a hidden tab, and CPU+network throttle. Each track must play
for at least 5s with no skip and no multi-second gap.

Uses the 11:08 / 11:14 IST IDs plus the 11:16-11:20 IST failure IDs.
Never points at production. Never prints secrets.
"""
import json, os, time
from pathlib import Path
from playwright.sync_api import sync_playwright

BASE = os.environ.get("MS_BASE", "http://127.0.0.1:8128")
if "tunestream.dpdns.org" in (BASE or ""):
    raise SystemExit("radio_swap_fallback_e2e refuses the public site; set MS_BASE to the test copy")
USER = "loadtest"
CHROME = os.environ.get("CHROME", "/usr/bin/google-chrome")
# 11:08 / 11:14, then 11:16-11:20 audio cascade IDs
SEQS = [
    [
        "4fndeDfaWCg",
        "OMOGaugKpzs",
        "-WMiAcp2XUA",
        "zpzdgmqIHOQ",
        "eNvUS-6PTbs",
        "S_E2EHVxNAE",
        "92cwKCU8Z5c",
    ],
    [
        "izGwDsrQ1eQ",
        "LU-R9Z_LrFc",
        "sR0RT0wiufw",
        "aGCdLKXNF3w",
        "1TO48Cnl66w",
        "NdYWuo9OFAw",
    ],
]
R = []

def pw():
    return Path(os.environ.get("MS_PW_FILE", "/tmp/loadtest.pw")).read_text(encoding="utf-8").strip()

def ok(name, cond, info=None):
    R.append({"name": name, "pass": bool(cond), "detail": info})
    print(("PASS " if cond else "FAIL ") + name, json.dumps(info, default=str)[:800] if info is not None else "")

def snap(page):
    return page.evaluate(
        """() => {
          const r=(typeof cur==='function'&&cur())||{};
          const a=window.AUD||window.M||document.getElementById('aud')||{};
          const s=window.__msSt||{};
          const el=s.el;
          return {
            id:r.id||'', qi:typeof qi==='number'?qi:-1,
            ct:+((a.currentTime||0).toFixed(2)),
            paused:!!a.paused, rs:a.readyState||0,
            stId:s.id||'', stRs:el?el.readyState: -1,
            stSrc:!!(el&&(el.getAttribute('src')||el.src)),
            build:(document.querySelector('meta[name=ms-build]')||{}).content||'',
            hidden:!!document.hidden
          };
        }"""
    )

def wait_play(page, expect_id, timeout=25000):
    t0 = time.time()
    last = {}
    while time.time() - t0 < timeout / 1000:
        last = snap(page)
        if last.get("id") == expect_id and (last.get("ct") or 0) >= 0.2 and not last.get("paused"):
            return last
        time.sleep(0.3)
    return last

def force_standby_dead(page):
    return page.evaluate(
        """() => {
          const s=window.__msSt;
          if(!s||!s.el) return {ok:false, why:'no-standby'};
          try{
            s.el.pause();
            s.el.removeAttribute('src');
            s.el.load();
            s.ready=0;
            s.err=0;
          }catch(e){return {ok:false, why:String(e&&e.message||e)}}
          return {ok:true, id:s.id||'', rs:s.el.readyState||0, src:!!(s.el.getAttribute('src')||s.el.src)};
        }"""
    )

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

def throttle(page):
    cdp = page.context.new_cdp_session(page)
    cdp.send("Network.emulateNetworkConditions", {
        "offline": False,
        "downloadThroughput": 80 * 1024,
        "uploadThroughput": 40 * 1024,
        "latency": 250,
    })
    try:
        cdp.send("Emulation.setCPUThrottlingRate", {"rate": 4})
    except Exception:
        pass
    return True

def login(page):
    page.goto(BASE + "/login", wait_until="domcontentloaded", timeout=45000)
    st = page.evaluate(
        """async ({u,p}) => {
          const r = await fetch('/api/auth/login', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({u,p}), credentials:'same-origin'});
          return r.status;
        }""",
        {"u": USER, "p": pw()},
    )
    if st != 200:
        raise SystemExit("login failed %s" % st)
    page.goto(BASE + "/", wait_until="domcontentloaded", timeout=45000)
    page.wait_for_function("() => typeof play==='function' && typeof next==='function'", timeout=30000)

def run_seq(page, blank, ids, label):
    page.evaluate(
        """(ids) => {
          queue = ids.map(id => ({id, title:id, channel:''}));
          qi = 0;
          try{localStorage.rad='1'}catch(_){};
          if(typeof radOn!=='undefined') radOn=true;
          return play();
        }""",
        ids,
    )
    first = wait_play(page, ids[0], 30000)
    ok(f"{label} first track plays", first.get("id") == ids[0] and not first.get("paused"), first)
    hide(page, True, blank)
    skipped = 0
    gaps = 0
    for i in range(1, len(ids)):
        want = ids[i]
        before = snap(page)
        dead = force_standby_dead(page)
        page.evaluate("() => { try{ next(); }catch(_){ } }")
        # must become the next intended id, not jump ahead
        t0 = time.time()
        got = before
        jumped = None
        while time.time() - t0 < 25:
            got = snap(page)
            gid = got.get("id") or ""
            if gid and gid not in ids[i-1:i+1] and gid in ids:
                # skipped past the target
                jumped = gid
                break
            if gid == want and (got.get("ct") or 0) >= 0.2 and not got.get("paused"):
                break
            time.sleep(0.3)
        landed = got.get("id") == want and not got.get("paused") and (got.get("ct") or 0) >= 0.15
        if not landed:
            skipped += 1
        ok(f"{label} advance to {want} after forced rs=0", landed, {"got": got, "dead": dead, "jumped": jumped, "prev": before})
        if not landed:
            continue
        # 5s continuous play, no skip, no gap over 1.2s
        t1 = time.time()
        samples = [got]
        last_ct = got.get("ct") or 0
        last_t = t1
        gap = False
        changed = False
        while time.time() - t1 < 5.2:
            time.sleep(0.4)
            s = snap(page)
            samples.append(s)
            now = time.time()
            if s.get("id") != want:
                changed = True
                break
            if s.get("paused") and (now - last_t) > 1.2:
                gap = True
            ct = s.get("ct") or 0
            if ct + 0.05 < last_ct and not s.get("paused"):
                # rewind is a problem unless tiny
                if last_ct - ct > 1.5:
                    gap = True
            if ct > last_ct + 0.15:
                last_ct = ct
                last_t = now
            elif s.get("paused"):
                pass
            else:
                # playing but clock not moving for long
                if now - last_t > 1.5:
                    gap = True
        progressed = (samples[-1].get("ct") or 0) - (samples[0].get("ct") or 0)
        good = (not changed) and (not gap) and progressed >= 3.5
        if not good:
            gaps += 1
        ok(f"{label} {want} plays 5s without gap or skip", good, {
            "progressed": round(progressed, 2), "changed": changed, "gap": gap,
            "start": samples[0], "end": samples[-1],
        })
    hide(page, False, blank)
    return skipped, gaps

def main():
    with sync_playwright() as p:
        b = p.chromium.launch(executable_path=CHROME, headless=True, args=[
            "--autoplay-policy=no-user-gesture-required", "--disable-dev-shm-usage",
        ])
        ctx = b.new_context(
            viewport={"width": 390, "height": 844}, is_mobile=True, has_touch=True,
            device_scale_factor=2,
            user_agent="Mozilla/5.0 (Linux; Android 14; SM-S916B) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/157.0.0.0 Mobile Safari/537.36",
            service_workers="block",
        )
        page = ctx.new_page()
        blank = ctx.new_page()
        blank.goto("about:blank")
        login(page)
        throttle(page)
        build = snap(page).get("build")
        ok("build is ms-v110", build == "ms-v110", {"build": build})
        for i, ids in enumerate(SEQS, 1):
            run_seq(page, blank, ids, f"seq{i}")
        b.close()
    failed = sum(1 for x in R if not x["pass"])
    print("SWAP_FALLBACK", json.dumps({"n": len(R), "fail": failed, "results": R}, default=str)[:4000])
    raise SystemExit(1 if failed else 0)

if __name__ == "__main__":
    main()
