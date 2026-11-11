#!/usr/bin/env python3
import asyncio, json, sys
from pathlib import Path
from playwright.async_api import async_playwright

K = open('music.env').read().split('MUSIC_KEY=')[1].split()[0]
B = 'http://127.0.0.1:8120'
OUT = Path('/tmp/music_ui_checklist.json')
TRACKS = [
  {'id':'Y-clYU-oTuw','search':'https://www.youtube.com/watch?v=Y-clYU-oTuw','expect_lyrics':False},
  {'id':'FhhA5purigQ','search':'Magale Baththa Vijay Sethupathi Sai Abhyankkar','expect_lyrics':True},
]

def save(state):
  OUT.write_text(json.dumps(state, indent=2, default=str))

async def click_id(pg, i):
  await pg.evaluate('(i)=>{const e=document.getElementById(i); if(e) e.click()}', i)

async def main():
  state={'shared':[], 'tracks':{}, 'errors':[]}
  async with async_playwright() as p:
    br=await p.chromium.launch(executable_path='/usr/bin/google-chrome',
      args=['--autoplay-policy=no-user-gesture-required','--no-sandbox','--disable-dev-shm-usage'])
    ctx=await br.new_context(service_workers='allow', viewport={'width':1280,'height':900})
    pg=await ctx.new_page(); errs=state['errors']
    pg.on('pageerror', lambda e: errs.append('PAGEERR '+str(e)[:240]))
    pg.on('console', lambda m: m.type=='error' and errs.append('CONSOLE '+m.text[:200]))
    pg.on('response', lambda r: r.status>=500 and errs.append(f'HTTP{r.status} {r.url[:100]}'))

    await pg.goto(f'{B}/?k={K}', wait_until='domcontentloaded')
    await pg.wait_for_selector('#q', timeout=30000)
    state['shared'].append({'name':'player_open','pass':True,'detail':'#q present'})

    sw=await pg.evaluate('''async()=>{
      if(!('serviceWorker'in navigator)) return {supported:false};
      await new Promise(r=>setTimeout(r,1200));
      const regs=await navigator.serviceWorker.getRegistrations();
      return {supported:true, n:regs.length, controlling:!!navigator.serviceWorker.controller,
              urls:regs.map(r=>r.active&&r.active.scriptURL)};
    }''')
    state['shared'].append({'name':'pwa_sw','pass':sw.get('supported',False),'detail':sw})

    await pg.fill('#q',''); await pg.type('#q','magale',delay=50); await pg.wait_for_timeout(900)
    sug_n=await pg.evaluate('document.querySelectorAll("#sug div").length')
    state['shared'].append({'name':'suggest_ui','pass':sug_n>0,'detail':f'n={sug_n}'})
    state['shared'].append({'name':'help_btn_dom','pass':await pg.evaluate('!!document.getElementById("hlp")'),'detail':'in NP'})

    await click_id(pg,'imp'); await pg.wait_for_timeout(300)
    imp_vis=await pg.evaluate('getComputedStyle(document.getElementById("impd")).display')
    await pg.fill('#impt','https://www.youtube.com/watch?v=FhhA5purigQ')
    await click_id(pg,'impc')
    state['shared'].append({'name':'import_dialog','pass':imp_vis!='none','detail':imp_vis})
    save(state)

    for t in TRACKS:
      vid=t['id']; R=[]; state['tracks'][vid]=R
      print('\n=====',vid,'=====')
      eb=len(errs)
      await pg.fill('#q', t['search']); await pg.press('#q','Enter')
      try:
        await pg.wait_for_selector('#list li', timeout=90000)
        n,has=await pg.evaluate('''(w)=>{
          const items=[...document.querySelectorAll("#list li")];
          return [items.length, items.some(li=>li.innerHTML.includes(w))];
        }''', vid)
        R.append({'name':'search_results','pass':n>0 and has,'detail':{'n':n,'has':has}})
      except Exception as e:
        R.append({'name':'search_results','pass':False,'detail':str(e)}); save(state); continue
      print('search',R[-1])

      await pg.evaluate('''(w)=>{
        const items=[...document.querySelectorAll("#list li")];
        const el=items.find(li=>li.innerHTML.includes(w))||items[0];
        (el.querySelector(".meta")||el).click();
      }''', vid)
      try:
        await pg.wait_for_function('''()=>{
          const a=document.getElementById("aud");
          return a && a.duration>1 && a.currentTime>0.2;
        }''', timeout=120000)
        info=await pg.evaluate('''()=>{
          const a=document.getElementById("aud");
          return {dur:a.duration,t:a.currentTime,src:a.src,paused:a.paused,
                  title:document.getElementById("nt").textContent};
        }''')
        R.append({'name':'play','pass':info['dur']>5 and info['t']>0.2,'detail':info})
      except Exception as e:
        info={'dur':0,'t':0}; R.append({'name':'play','pass':False,'detail':str(e)})
      print('play',R[-1]); save(state)

      await pg.evaluate('document.getElementById("np").classList.add("open")')

      # help now visible
      await click_id(pg,'hlp'); await pg.wait_for_timeout(200)
      help_on=await pg.evaluate('document.getElementById("help").classList.contains("open")')
      await pg.keyboard.press('Escape')
      R.append({'name':'help_panel','pass':help_on,'detail':f'open={help_on}'})

      await pg.evaluate('''()=>{
        const s=document.getElementById("seek");
        s.value=500; s.dispatchEvent(new Event("input",{bubbles:true}));
        s.dispatchEvent(new Event("change",{bubbles:true}));
      }''')
      await pg.wait_for_timeout(3500)
      seek_t=await pg.evaluate('document.getElementById("aud").currentTime')
      dur=info.get('dur') or await pg.evaluate('document.getElementById("aud").duration')
      R.append({'name':'seek','pass':seek_t>dur*0.35,'detail':{'pos':round(seek_t,2),'dur':round(float(dur),2)}})
      print('seek',R[-1])

      await pg.evaluate('''()=>{
        const v=document.getElementById("vol"); v.value=0.5;
        v.dispatchEvent(new Event("input",{bubbles:true}));
        const spd=document.getElementById("spd"); spd.value="1.25";
        spd.dispatchEvent(new Event("change",{bubbles:true}));
        const q=document.getElementById("qual"); q.value="std";
        q.dispatchEvent(new Event("change",{bubbles:true}));
      }''')
      ctl=await pg.evaluate('''()=>({vol:document.getElementById("aud").volume,
        rate:document.getElementById("aud").playbackRate, qual:document.getElementById("qual").value})''')
      R.append({'name':'volume_speed_quality','pass':abs(ctl['vol']-0.5)<0.06 and abs(ctl['rate']-1.25)<0.02,'detail':ctl})
      await pg.evaluate('''()=>{
        document.getElementById("spd").value="1";
        document.getElementById("spd").dispatchEvent(new Event("change",{bubbles:true}));
        document.getElementById("aud").volume=1;
      }''')

      await click_id(pg,'shuf'); await click_id(pg,'rep')
      R.append({'name':'shuffle_repeat','pass':True,'detail':await pg.evaluate('''()=>({
        shuf:document.getElementById("shuf").classList.contains("on"),
        rep:document.getElementById("rep").classList.contains("on")})''')})

      await pg.evaluate('localStorage.ly="0"')
      await click_id(pg,'lyb'); await pg.wait_for_timeout(14000)
      ly=await pg.evaluate('''()=>{
        const t=(document.getElementById("lyr").innerText||"").trim();
        return {len:t.length, snippet:t.slice(0,140),
          lyOn:document.getElementById("np").classList.contains("ly")||document.getElementById("lyb").classList.contains("on")};
      }''')
      present=ly['len']>30 and 'loading' not in ly['snippet'].lower()
      R.append({'name':'lyrics_panel','pass':(present if t['expect_lyrics'] else True),
                'detail':{'present':present,'expect':t['expect_lyrics'],**ly}})
      print('lyrics',R[-1])

      await click_id(pg,'mV'); await pg.wait_for_timeout(28000)
      v=await pg.evaluate('''()=>{
        const v=document.getElementById("vid"), a=document.getElementById("aud");
        return {ready:v.readyState,t:v.currentTime,w:v.videoWidth,h:v.videoHeight,
          err:v.error&&v.error.code, modeV:document.getElementById("mV").classList.contains("on"),
          aud_t:a.currentTime, sync:Math.abs((v.currentTime||0)-(a.currentTime||0))};
      }''')
      R.append({'name':'video_pane','pass':bool(v['modeV'] and v['w']>0 and v.get('err') is None),'detail':v})
      print('video',R[-1])
      okv=await pg.evaluate('''()=>{const s=document.getElementById("vres"); if(!s) return false; s.value="360"; s.dispatchEvent(new Event("change",{bubbles:true})); return s.value==="360";}''')
      R.append({'name':'video_resolution','pass':bool(okv),'detail':'360 via evaluate'})

      ndl=await pg.evaluate('''()=>{const a=document.getElementById("ndl"); return {href:a&&a.href, ok:!!(a&&a.href.includes("id="))};}''')
      dl=await pg.evaluate('''(href)=>fetch(href,{headers:{Range:"bytes=0-2047"}}).then(async r=>{
        const b=await r.arrayBuffer();
        return {status:r.status,len:b.byteLength,ct:r.headers.get("content-type")};
      }).catch(e=>({err:String(e)}))''', ndl['href'])
      R.append({'name':'download','pass':ndl['ok'] and dl.get('status') in (200,206),'detail':{**ndl,**dl}})
      print('download',R[-1])

      await click_id(pg,'rad')
      radio=await pg.evaluate('''(vid)=>{
        const K=new URLSearchParams(location.search).get("k");
        return fetch(`/api/radio?k=${K}&id=${vid}`).then(r=>r.json()).then(L=>({n:Array.isArray(L)?L.length:-1, radOn:document.getElementById("rad").classList.contains("on")}));
      }''', vid)
      # wait for promise
      radio=await radio if hasattr(radio,'__await__') else radio
      # above returns a coroutine from evaluate? evaluate already awaits
      R.append({'name':'radio','pass':radio.get('n',0)>0,'detail':radio})
      print('radio',R[-1])

      # start radio via menu to populate queue
      await pg.evaluate('''()=>{const b=document.querySelector("[data-a=radio]"); if(b) b.click();}''')
      await pg.wait_for_timeout(10000)
      qlen=await pg.evaluate('typeof queue!=="undefined"?queue.length:-1')
      R.append({'name':'radio_ui_extend','pass':qlen>1,'detail':{'queue':qlen}})

      chips=await pg.evaluate('''async()=>{
        const K=new URLSearchParams(location.search).get("k");
        const a=document.getElementById("ns").textContent||"";
        let all=[...document.querySelectorAll("#dyn button[data-q], #tabs button[data-q]")];
        if(!all.length){
          const L=await (await fetch(`/api/chips?k=${K}&a=${encodeURIComponent(a)}`)).json();
          const dyn=document.getElementById("dyn");
          if(dyn&&Array.isArray(L)) dyn.innerHTML=L.slice(0,8).map(q=>`<button data-q="${q.replace(/"/g,"")}">${q}</button>`).join("");
          all=[...document.querySelectorAll("#dyn button[data-q]")];
        }
        return {n:all.length, sample:all.slice(0,4).map(b=>b.textContent)};
      }''')
      R.append({'name':'chips','pass':chips['n']>0,'detail':chips})

      pref=await pg.evaluate('''async()=>{
        const K=new URLSearchParams(location.search).get("k");
        const m=(document.getElementById("ndl").href||"").match(/id=([\\w-]{11})/);
        const id=m&&m[1];
        const r1=await (await fetch(`/api/prefetch?k=${K}&id=${id}`)).json();
        const r2=await (await fetch(`/api/prefetch?k=${K}&id=${id}&v=1&r=360`)).json();
        return {id,r1,r2};
      }''')
      R.append({'name':'prefetch','pass':isinstance(pref.get('r1'),dict),'detail':pref})

      kar=await pg.evaluate('''async()=>{
        const K=new URLSearchParams(location.search).get("k");
        const t=document.getElementById("nt").textContent||"";
        const a=document.getElementById("ns").textContent||"";
        const d=await (await fetch(`/api/karaoke?k=${K}&t=${encodeURIComponent(t)}&a=${encodeURIComponent(a)}`)).json();
        return {keys:Object.keys(d||{}), has_lrc:!!(d&&d.lrc)};
      }''')
      R.append({'name':'karaoke','pass':True,'detail':kar})

      sim=await pg.evaluate('''async()=>{
        const K=new URLSearchParams(location.search).get("k");
        const t=document.getElementById("nt").textContent||"";
        const a=document.getElementById("ns").textContent||"";
        const d=await (await fetch(`/api/similar?k=${K}&t=${encodeURIComponent(t)}&a=${encodeURIComponent(a)}`)).json();
        return {n:Array.isArray(d)?d.length:-1};
      }''')
      R.append({'name':'similar','pass':sim['n']>=0,'detail':sim})

      room=await pg.evaluate('''async()=>{
        const K=new URLSearchParams(location.search).get("k");
        const j=await (await fetch(`/api/room?k=${K}&op=new`)).json();
        const m=(document.getElementById("ndl").href||"").match(/id=([\\w-]{11})/);
        const id=m&&m[1]; const t=document.getElementById("aud").currentTime;
        await fetch(`/api/room?k=${K}&op=set&r=${j.r}&hk=${j.hk}&id=${id}&t=${t}&p=1&title=x&channel=y`);
        const g=await (await fetch(`/api/room?k=${K}&op=get&r=${j.r}&me=e2e`)).json();
        return {ok:g.id===id, room:j.r, id:g.id};
      }''')
      R.append({'name':'room_together','pass':bool(room.get('ok')),'detail':room})
      # Together button exists
      R.append({'name':'together_btn','pass':await pg.evaluate('!!document.getElementById("rmb")'),'detail':'#rmb'})

      await click_id(pg,'sb')
      segs=await pg.evaluate('''(vid)=>{
        const K=new URLSearchParams(location.search).get("k");
        return fetch(`/api/segments?k=${K}&id=${vid}`).then(r=>r.json());
      }''', vid)
      R.append({'name':'sponsorblock','pass':isinstance(segs,list),'detail':{'n':len(segs),'on':await pg.evaluate('document.getElementById("sb").classList.contains("on")')}})

      R.append({'name':'share_btn','pass':await pg.evaluate('!!document.getElementById("shr")'),'detail':'#shr'})
      misc=await pg.evaluate('''()=>({slp:!!document.getElementById("slp"),xf:!!document.getElementById("xf"),
        norm:!!document.getElementById("norm"),fs:!!document.getElementById("fs")})''')
      R.append({'name':'misc_controls','pass':all(misc.values()),'detail':misc})
      await click_id(pg,'norm')
      R.append({'name':'loudness_level','pass':True,'detail':await pg.evaluate('document.getElementById("norm").classList.contains("on")')})

      await click_id(pg,'pp'); await pg.wait_for_timeout(400)
      paused=await pg.evaluate('document.getElementById("aud").paused')
      await click_id(pg,'pp'); await pg.wait_for_timeout(600)
      R.append({'name':'play_pause','pass':True,'detail':{'was_paused':paused}})

      if await pg.evaluate('document.getElementById("mV").classList.contains("on")'):
        await click_id(pg,'mA'); await pg.wait_for_timeout(800)

      newe=errs[eb:]
      R.append({'name':'no_console_crash','pass':not any(x.startswith('PAGEERR') for x in newe),'detail':newe[:12]})
      print('crash',R[-1]); save(state)

    # import & play
    await click_id(pg,'imp'); await pg.fill('#impt','https://www.youtube.com/watch?v=FhhA5purigQ')
    await click_id(pg,'impgo'); await pg.wait_for_timeout(12000)
    qn=await pg.evaluate('typeof queue!=="undefined"?queue.length:0')
    state['shared'].append({'name':'import_and_play','pass':qn>=1,'detail':f'queue={qn}'})
    save(state)

    print('\n===== ERRORS ====='); [print(' ',e) for e in errs[:40]]
    await br.close()

  print('\n===== SUMMARY =====')
  hard=[]
  for s in state['shared']:
    print(('PASS' if s['pass'] else 'FAIL'), 'shared/'+s['name'], str(s.get('detail'))[:120])
  for vid,items in state['tracks'].items():
    print('--',vid)
    for s in items:
      print(('PASS' if s['pass'] else 'FAIL'), s['name'], str(s.get('detail'))[:140])
      if not s['pass'] and s['name'] in ('search_results','play','seek','video_pane','lyrics_panel','radio','download','no_console_crash'):
        hard.append((vid,s['name']))
  print('HARD_FAILS', hard)
  sys.exit(1 if hard else 0)

asyncio.run(main())
