import asyncio, json, sys
from playwright.async_api import async_playwright
K=open('music.env').read().split('MUSIC_KEY=')[1].split()[0]; B='http://127.0.0.1:8130'
PHONE = len(sys.argv)>1 and sys.argv[1]=='phone'
async def main():
  async with async_playwright() as p:
    br=await p.chromium.launch(executable_path='/usr/bin/google-chrome',args=['--autoplay-policy=no-user-gesture-required','--no-sandbox','--use-gl=angle','--use-angle=swiftshader','--enable-unsafe-swiftshader'])
    vp={'width':390,'height':844} if PHONE else {'width':1280,'height':900}
    ctx=await br.new_context(service_workers='block',viewport=vp,has_touch=PHONE,is_mobile=PHONE)
    pg=await ctx.new_page(); errs=[]
    pg.on('pageerror',lambda e:errs.append('PAGEERR '+str(e)))
    pg.on('console',lambda m:(m.type in('error','warning')) and errs.append(m.type.upper()+' '+m.text[:200]))
    pg.on('response',lambda r:r.status>=400 and errs.append(f'HTTP {r.status} {r.url.split("?")[0][-80:]}'))
    await pg.goto(f'{B}/?k={K}'); await pg.wait_for_timeout(1500)
    await pg.evaluate("localStorage.vizMode65='dance';localStorage['ms.viz']=JSON.stringify({on:true,model:'vita'})")
    await pg.reload(); await pg.wait_for_timeout(1500)
    await pg.fill('#q','Uptown Funk Mark Ronson'); await pg.press('#q','Enter')
    await pg.wait_for_selector('#list li',timeout=90000); await pg.evaluate("document.querySelectorAll('#list li')[0].querySelector('.meta').click()")
    await pg.wait_for_function('()=>{const a=document.getElementById("aud");return a&&a.currentTime>2}',timeout=120000)
    title=await pg.evaluate("(document.querySelector('#np .nptitle .t')||{}).textContent||''"); print('REAL TRACK:',title[:60])
    await pg.evaluate("document.getElementById('np').classList.add('open')"); await pg.wait_for_timeout(500)
    await pg.evaluate("window.__msViz.set(true);window.__msViz.mode('dance')")
    await pg.wait_for_function("()=>{const s=window.__msViz.stats();return s.dance&&s.dance.clip}",timeout=180000)
    print('dancer loaded:',json.dumps(await pg.evaluate("window.__msViz.stats().dance")))
    async def sample(label,n=10,gap=3000):
      rows=[]
      for i in range(n):
        await pg.wait_for_timeout(gap); s=await pg.evaluate("window.__msViz.stats().dance")
        rows.append(s); print(f"  [{label}] t+{(i+1)*gap//1000}s detectedBPM={s['bpm']} conf={s['conf']} clip={s['clip']} clipBPM={s['clipBpm']} rate={s['rate']} animTempoNow={s['animTempo']} animTempoMeasured={s['animTempoMeasured']} animBeats/songBeat={s['animBeatsPerSongBeat']} phaseErr={s['phaseErrMs']}ms beats={s['beats']} tempoSwitches={s['tempoSwitches']} fps={s['fps']}")
      return rows
    real=await sample('real song',8)
    await pg.screenshot(path=f'uat/v80_dance_{"phone" if PHONE else "desk"}.png')
    res={}
    for bpm in (128,92):
      await pg.evaluate(f"()=>{{const a=document.getElementById('aud');a.src='/vendor/_test/beat{bpm}.wav';a.currentTime=0;a.play()}}")
      rows=await sample(f'synthetic {bpm} BPM',9)
      res[bpm]=rows[-4:]
      dump=await pg.evaluate('(()=>{const t=window.__msViz.danceApi().tracker;return {T:t.T.slice(),F:t.F.slice()}})()'); json.dump(dump,open(f'uat/v80_flux_{bpm}.json','w'))
    log=await pg.evaluate("window.__msViz.stats().danceLog()")
    print('clip switches:',json.dumps(log['clips'][-8:]))
    out={'real':real,'synthetic':{str(k):v for k,v in res.items()},'log':log,'errors':errs}
    json.dump(out,open(f'uat/v80_dance_{"phone" if PHONE else "desk"}.json','w'),indent=1)
    print('ERRORS/WARNINGS:',len(errs)); [print('  ',e) for e in errs[:30]]
    await br.close()
asyncio.run(main())
