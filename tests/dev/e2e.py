import asyncio, re, sys, os
from playwright.async_api import async_playwright
K=open('music.env').read().split('MUSIC_KEY=')[1].split()[0]; B='http://127.0.0.1:8120'
async def main():
  async with async_playwright() as p:
    br=await p.chromium.launch(executable_path='/usr/bin/google-chrome',args=['--autoplay-policy=no-user-gesture-required','--no-sandbox'])
    ctx=await br.new_context(service_workers='block',viewport={'width':1280,'height':900}); pg=await ctx.new_page(); errs=[]
    pg.on('pageerror',lambda e:errs.append('PAGEERR '+str(e)))
    pg.on('console',lambda m:m.type=='error' and errs.append('CONSOLE '+m.text+' '+str(m.location.get('url'))[:120]))
    pg.on('requestfinished',lambda r:None)
    pg.on('response',lambda r:r.status>=400 and errs.append(f'HTTP {r.status} {r.url[:90]}'))
    await pg.goto(f'{B}/?k={K}'); await pg.fill('#q','beatles let it be'); await pg.press('#q','Enter')
    await pg.wait_for_selector('#list li',timeout=90000); await pg.evaluate("document.querySelectorAll('#list li')[1].querySelector('.meta').click()")
    await pg.wait_for_function('()=>{const a=document.getElementById("aud");return a&&a.currentTime>1}',timeout=90000)
    print("aud src", await pg.evaluate("document.getElementById(\"aud\").src"))
    dur=await pg.evaluate('document.getElementById("aud").duration'); print('PLAY ok dur',dur)
    await pg.evaluate('()=>{const s=document.getElementById("seek");s.value=500;s.dispatchEvent(new Event("input"));s.dispatchEvent(new Event("change"))}')
    await pg.wait_for_timeout(5000); t=await pg.evaluate('document.getElementById("aud").currentTime'); print('SEEK ->',t, 'PASS' if t>dur*0.45 else 'FAIL')
    await pg.evaluate('()=>{localStorage.ly="0"}'); await pg.evaluate('document.getElementById("np").classList.add("open")')
    await pg.evaluate("document.getElementById('lyb').click()"); await pg.wait_for_timeout(15000)
    ly=await pg.evaluate('document.getElementById("lyr").innerText.slice(0,120)'); print('LYRICS:',repr(ly))
    await pg.evaluate('document.getElementById("mV").click()'); await pg.wait_for_timeout(25000)
    v=await pg.evaluate('(()=>{const v=document.getElementById("vid");return [v.readyState,v.currentTime,v.videoWidth,v.error&&v.error.code,document.getElementById("mV").classList.contains("on")]})()')
    print('VIDEO readyState,t,width,err,modeV:',v)
    print('ERRORS:',*errs[:20],sep='\n  '); await br.close()
asyncio.run(main())
