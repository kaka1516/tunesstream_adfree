import asyncio,sys
from playwright.async_api import async_playwright
K=open('music.env').read().split('MUSIC_KEY=')[1].split()[0];tag=sys.argv[1]
async def main():
  async with async_playwright() as p:
    br=await p.chromium.launch(executable_path='/usr/bin/google-chrome',args=['--no-sandbox'])
    for name,vp,mob in [('desk',{'width':1280,'height':860},False),('phone',{'width':390,'height':844},True)]:
      c=await br.new_context(viewport=vp,is_mobile=mob,has_touch=mob,device_scale_factor=2 if mob else 1,service_workers='block');pg=await c.new_page()
      errs=[];pg.on('pageerror',lambda e:errs.append(str(e)))
      await pg.goto(f'http://127.0.0.1:8120/?k={K}');await pg.wait_for_timeout(800)
      await pg.fill('#q','arijit singh');await pg.press('#q','Enter');await pg.wait_for_timeout(6000)
      await pg.screenshot(path=f'/tmp/{tag}_{name}_list.png')
      await pg.evaluate("document.querySelector('#list .meta')?.click()");await pg.wait_for_timeout(4000)
      await pg.screenshot(path=f'/tmp/{tag}_{name}_mini.png')
      await pg.evaluate("document.getElementById('mini').click()");await pg.wait_for_timeout(1500)
      await pg.screenshot(path=f'/tmp/{tag}_{name}_np.png');print(name,errs);await c.close()
    await br.close()
asyncio.run(main())
