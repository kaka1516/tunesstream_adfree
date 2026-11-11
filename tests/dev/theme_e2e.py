import asyncio,json
from playwright.async_api import async_playwright
K=open('music.env').read().split('MUSIC_KEY=')[1].split()[0]
async def main():
  async with async_playwright() as p:
    br=await p.chromium.launch(executable_path='/usr/bin/google-chrome',args=['--no-sandbox','--autoplay-policy=no-user-gesture-required'])
    c=await br.new_context(viewport={'width':390,'height':844},is_mobile=True,has_touch=True,device_scale_factor=2);pg=await c.new_page()
    errs=[];pg.on('pageerror',lambda e:errs.append(str(e)))
    await pg.goto(f'http://127.0.0.1:8120/?k={K}');await pg.wait_for_timeout(1500)
    # a11y check
    await pg.click('#thb');await pg.wait_for_timeout(300)
    a11y=await pg.evaluate("({role:thl.getAttribute('role'),focus:document.activeElement.getAttribute('aria-checked'),n:thl.querySelectorAll('[role=radio]').length})")
    await pg.keyboard.press('ArrowDown');await pg.keyboard.press('Escape')
    a11y['escFocusBack']=await pg.evaluate("document.activeElement.id")
    out={'a11y':a11y}
    for k in ['sideb','synth','sakura','paper','nord']:
      r={}
      await pg.evaluate("document.getElementById('np')?.classList.contains('open')&&npclose.click()");await pg.wait_for_timeout(600)
      await pg.evaluate("thb.click()");await pg.click(f'#thl [data-k={k}]');await pg.wait_for_timeout(300)
      r['theme']=await pg.evaluate("document.documentElement.dataset.theme")
      await pg.evaluate("np&&$('npclose').click()") if False else None
      await pg.evaluate("document.getElementById('np')?.classList.contains('open')&&document.getElementById('npclose').click()");await pg.wait_for_timeout(500)
      await pg.fill('#q','arijit singh tum hi ho');await pg.press('#q','Enter');await pg.wait_for_timeout(7000)
      r['results']=await pg.evaluate("document.querySelectorAll('#list li').length")
      await pg.screenshot(path=f'theme_shots/{k}_list.png')
      await pg.evaluate("document.querySelector('#list .meta')?.click()");await pg.wait_for_timeout(6000)
      r['playing']=await pg.evaluate("!aud.paused&&aud.currentTime>0")
      await pg.evaluate("aud.currentTime=60");await pg.wait_for_timeout(1500)
      r['seek']=await pg.evaluate("aud.currentTime>=59")
      await pg.evaluate("document.getElementById('mini').click()");await pg.wait_for_timeout(1200)
      await pg.screenshot(path=f'theme_shots/{k}_np.png')
      await pg.evaluate("lyb.click()");await pg.wait_for_timeout(4000)
      r['lyrics']=await pg.evaluate("lyr.querySelectorAll('div').length")
      await pg.screenshot(path=f'theme_shots/{k}_lyrics.png');await pg.evaluate("lyb.click()")
      await pg.evaluate("mV.click()");await pg.wait_for_timeout(8000)
      r['video']=await pg.evaluate("vid.readyState>=2")
      await pg.evaluate("mA.click()");await pg.wait_for_timeout(500)
      r['svgIconColor']=await pg.evaluate("getComputedStyle(document.querySelector('#mV .ti')).stroke")
      out[k]=r;print(k,r,flush=True)
    out['errors']=errs;print(json.dumps(out))
    await br.close()
asyncio.run(main())
