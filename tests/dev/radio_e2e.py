#!/usr/bin/env python3
"""10+ radio auto-advances with natural end (seek to end-10s, let it play out).
Most transitions run with a real hidden tab (another page in front) and throttled
network. Also checks system-pause-near-end recovery. Real audio. Never prints secrets."""
import json, time
from pathlib import Path
from playwright.sync_api import sync_playwright

BASE = "https://tunestream.dpdns.org"
USER = "loadtest"
SEED = "4NRXx6U8ABQ"
import os
N_ADV = int(os.environ.get("NADV","10"))
VAR=os.environ.get("VAR","")

def pw():
    return Path("/tmp/loadtest.pw").read_text(encoding="utf-8").strip()

def login(page):
    page.goto(BASE + "/login", wait_until="domcontentloaded", timeout=45000)
    st = page.evaluate(
        """async ({u,p}) => {
          const r = await fetch('/api/auth/login', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({u,p}), credentials:'same-origin'});
          return {ok:r.ok, status:r.status};
        }""",
        {"u": USER, "p": pw()},
    )
    if not st or not st.get("ok"):
        raise SystemExit(f"login failed {st}")
    page.goto(BASE + "/", wait_until="domcontentloaded", timeout=45000)
    page.wait_for_function("() => typeof startRadio === 'function' && typeof next === 'function'", timeout=30000)

def snap(page):
    return page.evaluate(
        """() => {
          const r=(typeof cur==='function'&&cur())||{};
          const a=(typeof M!=='undefined'&&M)||document.getElementById('aud');
          const meta=document.querySelector('meta[name=ms-build]');
          return {
            build: meta&&meta.content||'',
            sw: window.__swV||'',
            id: r.id||'', title:(r.title||'').slice(0,50),
            qi, ql:(queue||[]).length, radOn:!!radOn, gen:typeof playGen==='number'?playGen:-1,
            want:a&&a.dataset.wantPlay, paused:a&&a.paused, ended:!!(a&&a.ended),
            ct:a&&+(+a.currentTime||0).toFixed(2),
            dur:a&&(isFinite(a.duration)?+a.duration.toFixed(2):0),
            rs:a&&a.readyState, err:!!(a&&a.error),
            hidden:!!document.hidden, stallN:(window.__stallW&&window.__stallW.n)||0,
            vol:a&&+a.volume.toFixed(2), muted:!!(a&&a.muted), ac:(typeof AC!=='undefined'&&AC)?AC.state:'none',
            playingEls:[...document.querySelectorAll('audio,video')].filter(e=>!e.paused&&!e.ended&&!e.muted).map(e=>e.id||e.tagName),
            endbar:!!(document.getElementById('endbar')&&document.getElementById('endbar').classList.contains('on')),
            life:(window.__msLife||[]).slice(-6).map(e=>e.ev).join(',')
          };
        }"""
    )

def wait_until(fn, timeout, pred):
    t0=time.time(); last=None
    while time.time()-t0<timeout:
        last=fn()
        if pred(last):
            return last
        time.sleep(0.35)
    return last

def hide(page, on, blank=None):
    """Spoof document.hidden and, when blank is set, really background the tab."""
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

def throttle(page, on=True):
    try:
        cdp = page.context.new_cdp_session(page)
        if on:
            cdp.send("Network.emulateNetworkConditions", {
                "offline": False,
                "downloadThroughput": 80 * 1024,
                "uploadThroughput": 40 * 1024,
                "latency": 250,
            })
        else:
            cdp.send("Network.emulateNetworkConditions", {
                "offline": False,
                "downloadThroughput": -1,
                "uploadThroughput": -1,
                "latency": 0,
            })
        return True
    except Exception as e:
        return str(e)

def main():
    ev=[]
    with sync_playwright() as p:
        browser=p.chromium.launch(executable_path="/usr/bin/google-chrome", headless=True,
            args=["--autoplay-policy=no-user-gesture-required","--disable-dev-shm-usage"])
        ctx=browser.new_context(viewport={"width":390,"height":844},
            user_agent="Mozilla/5.0 (Linux; Android 14) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Mobile Safari/537.36")
        page=ctx.new_page()
        blank=ctx.new_page()
        blank.goto("about:blank")
        page.bring_to_front()
        login(page)
        ev.append(("throttle", {"ok": throttle(page, True)}))
        s0=snap(page)
        ev.append(("boot", {"build":s0.get("build"), "sw":s0.get("sw"),
            "hasEndedTick": page.evaluate("()=>typeof endedTick==='function'"),
            "msNext": page.evaluate("()=>!!(navigator.mediaSession)")}))
        if False and s0.get("build") and "ms-v86" not in s0.get("build") and "ms-v85" not in s0.get("build"):
            ev.append(("WARN_build", s0.get("build")))
        page.evaluate(
            """({seed,VAR}) => {
              try{localStorage.rad='1';shuf=false;try{tog('shuf',false)}catch(e){};if(VAR.includes('nogap'))localStorage.gapless='0';else localStorage.gapless='1'}catch(_){}
              if(typeof radOn!=='undefined'){radOn=true; try{tog('rad',true)}catch(_){}}
              if(VAR.includes('norm')){localStorage.norm='1';normOn=true;try{normApply()}catch(e){}}
              if(VAR.includes('viz')){try{setViz(true)}catch(e){}}
              if(VAR.includes('video')){try{setMode('v')}catch(e){}}
              startRadio({id:seed, title:'radio2-test', channel:'', dur:0});
            }""",
            {"seed": SEED, "VAR": VAR},
        )
        ids=[]
        first=wait_until(lambda: snap(page), 45, lambda s: s and s.get("id") and s.get("ct",0)>0.2 and s.get("dur",0)>15 and not s.get("paused"))
        ev.append(("play1", first))
        if not (first and first.get("id") and first.get("ct",0)>0.2):
            print(json.dumps(ev, indent=2)); raise SystemExit("radio did not start")
        ids.append(first["id"])
        for n in range(2, N_ADV+2):  # songs 2..7 => 6 advances
            # wait for a clock and duration, then seek to end-10s and let it play out
            ready=wait_until(lambda: snap(page), 40, lambda s: s and s.get("id")==ids[-1] and s.get("dur",0)>12 and s.get("ct",0)>=0)
            if not (ready and ready.get("dur",0)>12):
                ev.append((f"FAIL_no_clock_{n}", snap(page))); print(json.dumps(ev, indent=2)); raise SystemExit(f"no clock for song {n-1}")
            hidden = (n >= 3)
            if n==6:
                ev.append(("truncate", page.evaluate("()=>{queue=queue.slice(0,qi+1);save();render();return {qi,ql:queue.length}}")))
            if hidden:
                hide(page, True, blank)
                ev.append(("hidden_on", snap(page)))
            if os.environ.get("OFFL") and n==2:
                ev.append(("offline_evt", page.evaluate("()=>{const a=M;a.currentTime=Math.min(a.duration-30,140);return new Promise(r=>setTimeout(()=>{window.dispatchEvent(new Event('offline'));r({ra:window.__resumeAt})},1500))}")))
            seeked=page.evaluate(
                """() => {
                  const a=document.getElementById('aud');
                  if(!a||!isFinite(a.duration)||a.duration<12) return {ok:false, dur:a&&a.duration};
                  const to=Math.max(0, a.duration-10);
                  a.currentTime=to;
                  return {ok:true, to:+to.toFixed(2), dur:+a.duration.toFixed(2), id:(typeof cur==='function'&&cur()&&cur().id)||''};
                }"""
            )
            ev.append((f"seek{n-1}", seeked, {"ct":snap(page).get("ct"), "hidden":hidden}))
            prev=ids[-1]
            nxt=wait_until(lambda: snap(page), 45, lambda s: s and s.get("id") and s["id"]!=prev)
            ev.append((f"advanced{n}", nxt, {"hidden":hidden}))
            if hidden:
                hide(page, False, blank)
            if not (nxt and nxt.get("id") and nxt["id"]!=prev):
                ev.append((f"FAIL_no_advance_{n}", snap(page), {"ids":ids}))
                print(json.dumps(ev, indent=2)); raise SystemExit(f"did not auto-advance to song {n}")
            ids.append(nxt["id"])
            # confirm real audio on the new track
            okp=wait_until(lambda: snap(page), 40, lambda s: s and s.get("id")==ids[-1] and s.get("ct",0)>0.15 and not s.get("paused"))
            time.sleep(1.5); okp=snap(page)
            if okp.get("ct",0)>20: ev.append((f"FAIL_started_midway_{n}", okp)); print(json.dumps(ev[-3:], indent=2)); raise SystemExit(f"song {n} started at {okp.get('ct')}")
            ev.append((f"playing{n}", okp))
            if okp.get("vol",0)<0.3 or len(okp.get("playingEls",[]))>1:
                ev.append((f"FAIL_quiet_or_overlap_{n}", okp)); print(json.dumps(ev, indent=2)); raise SystemExit(f"song {n} quiet/overlap")
            if not (okp and okp.get("ct",0)>0.15):
                ev.append((f"FAIL_no_play_{n}", snap(page)))
                print(json.dumps(ev, indent=2)); raise SystemExit(f"song {n} did not start real audio")
        # system pause near end (wantPlay left at 1, ended not fired): must auto-advance
        ready=wait_until(lambda: snap(page), 40, lambda s: s and s.get("id")==ids[-1] and s.get("dur",0)>12)
        ev.append(("sys_pause_ready", ready))
        if ready and ready.get("dur",0)>12:
            prev=ids[-1]
            sp=page.evaluate("""() => {
              const a=document.getElementById('aud');
              if(!a||!isFinite(a.duration)||a.duration<12) return {ok:false};
              a.currentTime=Math.max(0, a.duration-3);
              return new Promise(r=>setTimeout(()=>{
                const want=a.dataset.wantPlay;
                a.pause(); /* do not clear wantPlay — system/background pause */
                a.dataset.wantPlay=want||'1';
                r({ok:true, ct:+a.currentTime.toFixed(2), dur:+a.duration.toFixed(2), want:a.dataset.wantPlay, paused:a.paused});
              }, 400));
            }""")
            ev.append(("sys_pause_near", sp))
            nxt=wait_until(lambda: snap(page), 20, lambda s: s and s.get("id") and s["id"]!=prev)
            ev.append(("sys_pause_advanced", nxt))
            if not (nxt and nxt.get("id") and nxt["id"]!=prev):
                ev.append(("FAIL_sys_pause", snap(page)))
                print(json.dumps(ev, indent=2)); raise SystemExit("system pause near end did not advance")
            ids.append(nxt["id"])
            okp=wait_until(lambda: snap(page), 40, lambda s: s and s.get("id")==ids[-1] and s.get("ct",0)>0.15 and not s.get("paused"))
            ev.append(("sys_pause_playing", okp))
        ev.append(("PASS", {"ids":ids, "n":len(ids), "unique":len(set(ids)), "final":snap(page), "build":snap(page).get("build"), "sw":snap(page).get("sw")}))
        print(json.dumps(ev, indent=2))
        if len(ids) < N_ADV+1 or len(set(ids)) < N_ADV+1:
            raise SystemExit(f"expected at least {N_ADV+1} distinct songs, got {ids}")
        print("RADIO2_OK", len(ids), "songs", ",".join(ids))
        browser.close()

if __name__=="__main__":
    main()
