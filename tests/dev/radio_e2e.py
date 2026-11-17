#!/usr/bin/env python3
"""15+ radio auto-advances with natural end (seek to end-10s, let it play out).
Most transitions run with a real hidden tab (another page in front) and throttled
network. Also checks a forced dead next-track (404), a forced mid-song error
(advance after one retry when standby is ready), and system-pause-near-end
recovery. Seeks the active media element (M), not a hardcoded #aud.
Never prints secrets. Never claims to have heard audio."""
import json, time
from pathlib import Path
from playwright.sync_api import sync_playwright

import os as _os_ms; BASE=_os_ms.environ.get("MS_BASE","https://tunestream.dpdns.org")
USER = "loadtest"
SEED = "4NRXx6U8ABQ"
import os
N_ADV = int(os.environ.get("NADV","15"))
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
            life:(window.__msLife||[]).slice(-8).map(e=>e.ev).join(','),
            mid:(a&&(a.id||'')),
            src:(()=>{try{return (a&&a.getAttribute('src')||'').replace(/([?&]k=)[^&]*/,'$1***')}catch(_){return ''}})(),
            fb:(a&&a.dataset&&a.dataset.fb)||'',
            stId:(window.__msSt&&window.__msSt.id)||'',
            stReady:!!(window.__msSt&&window.__msSt.ready),
            stErr:!!(window.__msSt&&window.__msSt.err),
            stOk:(()=>{try{const n=queue[qi+1];return !!(n&&typeof msStandbyOk==='function'&&msStandbyOk(n.id))}catch(_){return false}})(),
            ahead:Math.max(0,((queue||[]).length-(qi||0)-1))
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
        desktop=bool(os.environ.get("DESKTOP"))
        ua=("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
            if desktop else
            "Mozilla/5.0 (Linux; Android 14) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Mobile Safari/537.36")
        vp={"width":1280,"height":800} if desktop else {"width":390,"height":844}
        browser=p.chromium.launch(executable_path="/usr/bin/google-chrome", headless=True,
            args=["--autoplay-policy=no-user-gesture-required","--disable-dev-shm-usage"])
        ctx=browser.new_context(viewport=vp, user_agent=ua)
        page=ctx.new_page()
        blank=ctx.new_page()
        blank.goto("about:blank")
        page.bring_to_front()
        login(page)
        ev.append(("throttle", {"ok": throttle(page, True)}))
        s0=snap(page)
        ev.append(("boot", {"build":s0.get("build"), "sw":s0.get("sw"),
            "desktop": desktop,
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
        # forced dead next-track: 11-char id whose media requests 404; client must alt-or-drop it
        dead="ZZZZZdead01"
        def _is_dead_req(url):
            u=url or ""
            return dead in u and "/api/alt" not in u
        def _dead_route(route):
            try:
                if _is_dead_req(route.request.url):
                    route.fulfill(status=404, body="e2e-dead", headers={"content-type":"text/plain","cache-control":"no-store"})
                    return
            except Exception:
                pass
            try: route.continue_()
            except Exception:
                try: route.abort("failed")
                except Exception: pass
        page.context.route("**/*", _dead_route)
        page.route("**/*", _dead_route)
        inj=page.evaluate(
            """(dead) => {
              const n={id:dead, title:'e2e-dead', channel:'', dur:180};
              const at=Math.max(1, (typeof qi==='number'?qi:0)+1);
              queue.splice(at, 0, n);
              try{save()}catch(_){}
              try{if(typeof msClearStandby==='function')msClearStandby()}catch(_){}
              try{if(typeof msArmPreload==='function')msArmPreload()}catch(_){}
              return {qi, ql:queue.length, next:(queue[qi+1]&&queue[qi+1].id)||'', ahead:queue.length-qi-1};
            }""",
            dead,
        )
        ev.append(("dead_injected", inj))
        # v110 single-player: dead tracks are skipped/alted at play time, not via
        # dual-player standby preload. Keep the 404 route through the first
        # seek-to-end advance, then assert we never settled on the dead id.

        for n in range(2, N_ADV+2):  # songs 2..N_ADV+1 => N_ADV advances
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
                  const a=(typeof M!=='undefined'&&M)||document.getElementById('aud')||document.getElementById('aud2');
                  if(!a||!isFinite(a.duration)||a.duration<12) return {ok:false, dur:a&&a.duration, mid:a&&a.id};
                  const to=Math.max(0, a.duration-10);
                  a.currentTime=to;
                  return {ok:true, to:+to.toFixed(2), dur:+a.duration.toFixed(2), mid:a.id||'', id:(typeof cur==='function'&&cur()&&cur().id)||''};
                }"""
            )
            ev.append((f"seek{n-1}", seeked, {"ct":snap(page).get("ct"), "hidden":hidden}))
            prev=ids[-1]
            # First advance may briefly land on the injected dead id; wait until
            # the single-player onErr path has skipped or alt-replaced it.
            if n==2:
                nxt=wait_until(lambda: snap(page), 60, lambda s: s and s.get("id") and s["id"]!=prev and s["id"]!=dead and s.get("ct",0)>0.15 and not s.get("paused"))
            else:
                nxt=wait_until(lambda: snap(page), 45, lambda s: s and s.get("id") and s["id"]!=prev)
            ev.append((f"advanced{n}", nxt, {"hidden":hidden}))
            if hidden:
                hide(page, False, blank)
            if not (nxt and nxt.get("id") and nxt["id"]!=prev):
                ev.append((f"FAIL_no_advance_{n}", snap(page), {"ids":ids}))
                print(json.dumps(ev, indent=2)); raise SystemExit(f"did not auto-advance to song {n}")
            if n==2:
                if nxt.get("id")==dead:
                    ev.append(("FAIL_played_dead", nxt, snap(page)))
                    print(json.dumps(ev, indent=2)); raise SystemExit("dead next-track was played instead of skipped or alt-replaced")
                ev.append(("dead_skipped_at_play", {"id":nxt.get("id"), "not_dead":nxt.get("id")!=dead}))
                try:
                    page.unroute("**/*", _dead_route)
                    page.context.unroute("**/*", _dead_route)
                except Exception: pass
            ids.append(nxt["id"])
            # confirm real audio on the new track (or a later unique track if the next one was skipped as dead/slow).
            # radio-lead updates cur().id before the <audio> src swaps, so currentTime can still be
            # the previous song's end (e.g. 281s). Treating that as a start made wait_until return
            # immediately, and the 1.5s resnap then caught the emptied new src (ct=0, rs=0).
            def _started(s):
                if not (s and s.get("id") and not s.get("paused") and s.get("rs", 0) >= 2 and s.get("dur", 0) > 12):
                    return False
                ct = s.get("ct", 0) or 0
                if ct <= 0.15:
                    return False
                life = str(s.get("life") or "")
                recovered = any(k in life for k in ("sb-skip", "stall-swap", "stall-skip", "ended-watchdog", "media-onErr"))
                if ct > 20 and not recovered:
                    return False  # leftover previous-song clock
                src = s.get("src") or ""
                if src and s["id"] not in src and "blob:" not in src and "/off/" not in src:
                    return False
                return s["id"] == ids[-1] or s["id"] not in ids
            okp=wait_until(lambda: snap(page), 40, _started)
            time.sleep(1.5); okp=snap(page)
            if not _started(okp):
                okp=wait_until(lambda: snap(page), 25, _started)
            okp=okp or snap(page) or {}
            if okp and okp.get("id") and okp["id"] not in ids[:-1] and okp.get("ct",0)>0.15 and not okp.get("paused") and okp["id"]!=ids[-1]:
                ev.append((f"stall_skip_{n}", {"from":ids[-1], "to":okp.get("id"), "ct":okp.get("ct"), "life":okp.get("life"), "title":okp.get("title")}))
                ids[-1]=okp["id"]
            life=str(okp.get("life") or "")
            recovered=any(k in life for k in ("sb-skip","stall-swap","stall-skip","ended-watchdog","media-onErr"))
            if okp.get("id")==ids[-1] and okp.get("ct",0)>20 and not recovered and not any(e[0].startswith("stall_skip_") and e[0].endswith(f"_{n}") for e in ev):
                ev.append((f"FAIL_started_midway_{n}", okp)); print(json.dumps(ev[-3:], indent=2)); raise SystemExit(f"song {n} started at {okp.get('ct')}")
            if okp.get("ct",0)>20 and recovered:
                ev.append((f"sb_skip_midway_{n}", {"ct":okp.get("ct"), "id":okp.get("id"), "life":life}))
            ev.append((f"playing{n}", okp))
            if okp.get("vol",0)<0.3 or len(okp.get("playingEls",[]))>1:
                ev.append((f"FAIL_quiet_or_overlap_{n}", okp)); print(json.dumps(ev, indent=2)); raise SystemExit(f"song {n} quiet/overlap")
            if not (okp and okp.get("ct",0)>0.15):
                ev.append((f"FAIL_no_play_{n}", snap(page)))
                print(json.dumps(ev, indent=2)); raise SystemExit(f"song {n} did not start real audio")
        # v110 single-player: mid-song error should recover the same track or skip
        # to the next one. It must not stall, and must not start a second player.
        mid_ready=wait_until(lambda: snap(page), 40, lambda s: s and s.get("id")==ids[-1] and s.get("dur",0)>12 and s.get("ct",0)>=0)
        ev.append(("miderr_clock", mid_ready))
        if mid_ready and mid_ready.get("dur",0)>12:
            page.evaluate("""() => {
              const a=(typeof M!=='undefined'&&M)||document.getElementById('aud');
              if(a&&isFinite(a.duration)&&a.duration>12){
                const to=Math.max(6, Math.min(12, a.duration/4));
                a.currentTime=to;
                try{window.__resumeAt=to}catch(_){}
              }
            }""")
            armed=wait_until(lambda: snap(page), 15, lambda s: s and s.get("id")==ids[-1] and s.get("ct",0)>5 and not s.get("paused"))
            ev.append(("miderr_armed", armed))
            prev=ids[-1]
            fired=page.evaluate("""() => {
              const a=(typeof M!=='undefined'&&M)||document.getElementById('aud');
              const r=(typeof cur==='function'&&cur())||{};
              const n=(queue[qi+1]||{});
              const pos=Math.max(a&&a.currentTime||0, +(window.__resumeAt||0));
              window.__msRt={id:r.id||'', n:1, t:Date.now()};
              window.__resumeAt=pos;
              try{a.dispatchEvent(new Event('error'))}catch(e){return {ok:false, err:String(e), pos, next:n.id, mid:a&&a.id}}
              return {ok:true, pos:+(+pos).toFixed(2), next:n.id||'', mid:a&&a.id, want:a&&a.dataset.wantPlay};
            }""")
            ev.append(("miderr_fired", fired))
            rec=wait_until(lambda: snap(page), 25, lambda s: s and s.get("id") and not s.get("paused") and s.get("ct",0)>0.15 and (s.get("playingEls") or []))
            ev.append(("miderr_after", rec))
            if not (rec and rec.get("id") and not rec.get("paused") and rec.get("ct",0)>0.15):
                ev.append(("FAIL_miderr", snap(page), fired))
                print(json.dumps(ev, indent=2)); raise SystemExit("mid-song error stalled instead of recovering or skipping")
            if rec.get("id")!=prev:
                ev.append(("miderr_skipped", {"from":prev, "to":rec.get("id")}))
                ids.append(rec["id"])
            if rec.get("vol",0)<0.3 or len(rec.get("playingEls",[]))>1:
                ev.append(("FAIL_miderr_overlap", rec)); print(json.dumps(ev, indent=2)); raise SystemExit("mid-song error quiet/overlap")

        # system pause near end (wantPlay left at 1, ended not fired): must auto-advance
        ready=wait_until(lambda: snap(page), 40, lambda s: s and s.get("id")==ids[-1] and s.get("dur",0)>12)
        ev.append(("sys_pause_ready", ready))
        if ready and ready.get("dur",0)>12:
            prev=ids[-1]
            sp=page.evaluate("""() => {
              const a=(typeof M!=='undefined'&&M)||document.getElementById('aud')||document.getElementById('aud2');
              if(!a||!isFinite(a.duration)||a.duration<12) return {ok:false, mid:a&&a.id};
              a.currentTime=Math.max(0, a.duration-3);
              return new Promise(r=>setTimeout(()=>{
                const want=a.dataset.wantPlay;
                a.pause(); /* do not clear wantPlay — system/background pause */
                a.dataset.wantPlay=want||'1';
                r({ok:true, ct:+a.currentTime.toFixed(2), dur:+a.duration.toFixed(2), want:a.dataset.wantPlay, paused:a.paused, mid:a.id||''});
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
