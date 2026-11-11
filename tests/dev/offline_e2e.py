import asyncio
from playwright.async_api import async_playwright
K=open('music.env').read().split('MUSIC_KEY=')[1].split()[0]
async def main():
  async with async_playwright() as p:
    br=await p.chromium.launch(executable_path='/usr/bin/google-chrome',args=['--no-sandbox'])
    c=await br.new_context(viewport={'width':390,'height':844},is_mobile=True,has_touch=True,device_scale_factor=2);pg=await c.new_page()
    errs=[];pg.on('pageerror',lambda e:errs.append(str(e)));pg.on('dialog',lambda d:asyncio.ensure_future(d.accept('Road trip')))
    u=f'http://127.0.0.1:8120/?k={K}';await pg.goto(u);await pg.wait_for_timeout(1500);await pg.reload();await pg.wait_for_timeout(1500)
    for id,t in [('fLnMzPk_p_M','Song A'),('Y-clYU-oTuw','Song B')]:
      await pg.evaluate(f"saveOff({{id:'{id}',title:'{t}',channel:'Test'}})")
      await pg.wait_for_function(f"isOff('{id}')",timeout=90000)
    await pg.click('#libb',force=True);await pg.click('#lnew',force=True);await pg.wait_for_timeout(300)
    await pg.click('#lsongs [data-a="0"]',force=True);await pg.click('#lsongs [data-a="1"]',force=True);await pg.wait_for_timeout(1500)
    await c.set_offline(True);await pg.reload();await pg.wait_for_timeout(2500)
    await pg.screenshot(path='offline_library.png')
    await pg.click('[data-pp="0"]',force=True);await pg.wait_for_timeout(4000)
    st=await pg.evaluate("[AUD.currentTime,AUD.paused,AUD.error&&AUD.error.code,navigator.onLine]");print('offline play',st)
    await pg.evaluate("$('mini').click()");await pg.wait_for_timeout(1200);await pg.screenshot(path='offline_np.png')
    print('errs',errs);await br.close()
asyncio.run(main())
