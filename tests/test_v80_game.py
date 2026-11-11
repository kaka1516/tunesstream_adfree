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
    await pg.fill('#q','Uptown Funk Mark Ronson'); await pg.press('#q','Enter')
    await pg.wait_for_selector('#list li',timeout=90000); await pg.evaluate("document.querySelectorAll('#list li')[0].querySelector('.meta').click()")
    await pg.wait_for_function('()=>{const a=document.getElementById("aud");return a&&a.currentTime>2}',timeout=120000)
    await pg.evaluate("document.getElementById('np').classList.add('open')"); await pg.wait_for_timeout(800)
    # 1) real song
    await pg.evaluate("window.__msGame.open()")
    await pg.wait_for_function("()=>{const f=document.querySelector('#msneo iframe');return f&&f.contentWindow&&f.contentWindow.__neoChart}",timeout=120000)
    fr=pg.frame_locator('#msneo iframe')
    chart=await pg.evaluate("document.querySelector('#msneo iframe').contentWindow.__neoChart"); print('REAL chart:',chart)
    await pg.evaluate("document.querySelector('#msneo iframe').contentWindow.document.getElementById('btnStart').click()")
    await pg.wait_for_timeout(6000)
    st=await pg.evaluate("document.querySelector('#msneo iframe').contentWindow.__neo.stats()"); print('REAL after 6s:',st); rn=await pg.evaluate("document.querySelector('#msneo iframe').contentWindow.__neo.notes()"); print('REAL first notes',[n['t'] for n in rn[:12]], 'gaps>3s:',sum(1 for a,b in zip(rn,rn[1:]) if b['t']-a['t']>3))
    await pg.screenshot(path=f'uat/v80_game_{"phone" if PHONE else "desk"}.png')
    hostT=await pg.evaluate("document.getElementById('aud').currentTime"); print('host t',round(hostT,2),'game t',round(st['t'],2))
    # tap a lane by touch/click
    box=await pg.evaluate("(()=>{const r=document.querySelector('#msneo iframe').getBoundingClientRect();return [r.width,r.height]})()")
    await pg.mouse.click(box[0]*0.5, box[1]*0.8); await pg.wait_for_timeout(300)
    await pg.evaluate("document.getElementById('msneo')&&window.MSGame.close()")
    # 2) synthetic 128 BPM ground truth
    await pg.evaluate("()=>{const a=document.getElementById('aud');a.src='/vendor/_test/beat128.wav';a.currentTime=0;a.play()}")
    await pg.wait_for_timeout(1500)
    await pg.evaluate("window.__msGame.open()")
    await pg.wait_for_function("()=>{const f=document.querySelector('#msneo iframe');return f&&f.contentWindow&&f.contentWindow.__neoChart}",timeout=120000)
    chart=await pg.evaluate("document.querySelector('#msneo iframe').contentWindow.__neoChart"); print('SYNTH chart:',chart)
    notes=await pg.evaluate("document.querySelector('#msneo iframe').contentWindow.__neo.notes()")
    json.dump(notes,open('uat/v80_notes128.json','w'))
    b=60/128; ev=[]; t=0.5
    while t<75: ev+= [t, t+b/2]; t+=b
    import bisect
    def d(x):
      i=bisect.bisect_left(ev,x); c=[abs(x-ev[j]) for j in (i-1,i) if 0<=j<len(ev)]; return min(c)
    ds=sorted(d(n['t']) for n in notes)
    within=sum(1 for x in ds if x<=0.03)/len(ds)
    print(f'SYNTH notes {len(notes)}; within 30 ms of a real drum hit: {within*100:.1f}%; median offset {ds[len(ds)//2]*1000:.1f} ms; p90 {ds[int(len(ds)*.9)]*1000:.1f} ms')
    await pg.evaluate("window.MSGame.close()")
    json.dump({'errors':errs,'within30':within,'n':len(notes)},open(f'uat/v80_game_{"phone" if PHONE else "desk"}.json','w'))
    print('ERRORS/WARNINGS:',len(errs)); [print('  ',e) for e in errs[:30]]
    await br.close()
asyncio.run(main())
