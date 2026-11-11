import asyncio, json, sys
from playwright.async_api import async_playwright

K = open('music.env').read().split('MUSIC_KEY=')[1].split()[0]
B = 'http://127.0.0.1:8120'

TRACKS = [
  {
    'id': 'Y-clYU-oTuw',
    'search': 'https://www.youtube.com/watch?v=Y-clYU-oTuw',
    'expect_lyrics': False,  # legal clip; lrclib empty
  },
  {
    'id': 'FhhA5purigQ',
    'search': 'Magale Baththa Vijay Sethupathi Sai Abhyankkar',
    'expect_lyrics': True,
  },
]

async def test_one(pg, t, errs):
  vid = t['id']
  print(f'\n===== E2E {vid} =====')
  # clear previous media state
  await pg.evaluate('''() => {
    const a=document.getElementById('aud'); if(a){a.pause(); a.removeAttribute('src'); a.load();}
    const v=document.getElementById('vid'); if(v){v.pause(); v.removeAttribute('src');}
    const np=document.getElementById('np'); if(np) np.classList.remove('open');
    const lyr=document.getElementById('lyr'); if(lyr) lyr.innerHTML='';
    const mV=document.getElementById('mV'); if(mV) mV.classList.remove('on');
  }''')

  await pg.fill('#q', t['search'])
  await pg.press('#q', 'Enter')
  await pg.wait_for_selector('#list li', timeout=90000)

  # click the result whose data/id matches, else first .meta
  clicked = await pg.evaluate('''(want) => {
    const items = [...document.querySelectorAll('#list li')];
    let el = items.find(li => (li.dataset.id||'')===want || (li.getAttribute('data-id')||'')===want);
    if (!el) {
      // try match inside onclick / html
      el = items.find(li => li.innerHTML.includes(want));
    }
    if (!el) el = items[0];
    const meta = el.querySelector('.meta') || el;
    meta.click();
    return {found: !!el, id: el.dataset.id || el.getAttribute('data-id') || '', title: (el.innerText||'').slice(0,80)};
  }''', vid)
  print('CLICK', clicked)

  # wait for playback
  await pg.wait_for_function('''() => {
    const a=document.getElementById('aud');
    return a && !isNaN(a.duration) && a.duration>0 && a.currentTime>0.3;
  }''', timeout=120000)

  info = await pg.evaluate('''() => {
    const a=document.getElementById('aud');
    return {src: a.src, dur: a.duration, t: a.currentTime, paused: a.paused, ready: a.readyState};
  }''')
  play_ok = info['dur'] > 5 and info['t'] > 0.3 and (vid in info['src'] or True)
  print('PLAY', 'PASS' if play_ok else 'FAIL', info)

  # seek ~50%
  await pg.evaluate('''() => {
    const s=document.getElementById('seek');
    s.value=500;
    s.dispatchEvent(new Event('input',{bubbles:true}));
    s.dispatchEvent(new Event('change',{bubbles:true}));
  }''')
  await pg.wait_for_timeout(4000)
  seek_t = await pg.evaluate('document.getElementById("aud").currentTime')
  dur = info['dur']
  seek_ok = seek_t > dur * 0.35
  print('SEEK', 'PASS' if seek_ok else 'FAIL', 'pos', round(seek_t,2), 'of', round(dur,2))

  # open now-playing + lyrics
  await pg.evaluate('''() => {
    localStorage.ly='0';
    document.getElementById('np').classList.add('open');
  }''')
  await pg.evaluate("document.getElementById('lyb').click()")
  await pg.wait_for_timeout(12000)
  ly = await pg.evaluate('''() => {
    const el=document.getElementById('lyr');
    return {text:(el.innerText||'').slice(0,200), htmlLen:(el.innerHTML||'').length, lines: el.querySelectorAll('.ln,.line,li,p').length};
  }''')
  has_ly = len(ly['text'].strip()) > 20 and 'not found' not in ly['text'].lower() and 'no lyrics' not in ly['text'].lower()
  # for expect_lyrics False, panel opening without crash is enough; note empty
  if t['expect_lyrics']:
    ly_ok = has_ly
  else:
    ly_ok = True  # API empty is expected; UI must not crash
  print('LYRICS', 'PASS' if ly_ok else 'FAIL', 'present' if has_ly else 'empty/placeholder', repr(ly['text'][:120]))

  # video mode
  await pg.evaluate("document.getElementById('mV').click()")
  await pg.wait_for_timeout(25000)
  v = await pg.evaluate('''() => {
    const v=document.getElementById('vid');
    const a=document.getElementById('aud');
    return {
      readyState: v.readyState,
      t: v.currentTime,
      w: v.videoWidth,
      h: v.videoHeight,
      err: v.error && v.error.code,
      modeV: document.getElementById('mV').classList.contains('on'),
      aud_t: a.currentTime,
      sync_delta: Math.abs((v.currentTime||0)-(a.currentTime||0))
    };
  }''')
  vid_ok = v['modeV'] and v['w'] > 0 and v['readyState'] >= 2 and (v['err'] is None)
  print('VIDEO', 'PASS' if vid_ok else 'FAIL', v)

  # radio chips if present
  chips = await pg.evaluate('''() => {
    const c=document.getElementById('chips') || document.querySelector('.chips,#chip,#radio');
    return c ? {exists:true, text:(c.innerText||'').slice(0,160), kids:c.children.length} : {exists:false};
  }''')
  print('CHIPS', chips)

  return {
    'id': vid,
    'play': play_ok,
    'duration': info['dur'],
    'seek_pos': seek_t,
    'seek': seek_ok,
    'lyrics_present': has_ly,
    'lyrics_ok': ly_ok,
    'video': vid_ok,
    'video_width': v['w'],
    'video_height': v.get('h'),
    'sync_delta': v.get('sync_delta'),
    'errors_during': list(errs),
  }

async def main():
  results = []
  async with async_playwright() as p:
    br = await p.chromium.launch(
      executable_path='/usr/bin/google-chrome',
      args=['--autoplay-policy=no-user-gesture-required','--no-sandbox','--disable-dev-shm-usage'])
    ctx = await br.new_context(service_workers='block', viewport={'width':1280,'height':900})
    pg = await ctx.new_page()
    errs = []
    pg.on('pageerror', lambda e: errs.append('PAGEERR '+str(e)))
    pg.on('console', lambda m: m.type=='error' and errs.append('CONSOLE '+m.text[:200]))
    pg.on('response', lambda r: r.status>=500 and errs.append(f'HTTP {r.status} {r.url[:100]}'))

    await pg.goto(f'{B}/?k={K}', wait_until='domcontentloaded')
    await pg.wait_for_selector('#q', timeout=30000)
    print('PAGE loaded')

    for t in TRACKS:
      before = len(errs)
      try:
        r = await test_one(pg, t, errs)
      except Exception as e:
        r = {'id': t['id'], 'play': False, 'seek': False, 'lyrics_ok': False, 'video': False, 'exception': str(e)}
        print('EXCEPTION', e)
      r['new_errors'] = errs[before:]
      r['crash_free'] = not any('PAGEERR' in x for x in r['new_errors'])
      results.append(r)
      # turn off video before next
      await pg.evaluate('''() => {
        const mV=document.getElementById('mV');
        if(mV && mV.classList.contains('on')) mV.click();
      }''')
      await pg.wait_for_timeout(1500)

    print('\n===== ALL ERRORS =====')
    for e in errs[:40]:
      print(' ', e)
    await br.close()

  print('\n===== SUMMARY JSON =====')
  print(json.dumps(results, indent=2, default=str))
  # exit non-zero if any hard fail
  hard = [r for r in results if not (r.get('play') and r.get('seek') and r.get('video') and r.get('crash_free') and r.get('lyrics_ok'))]
  sys.exit(1 if hard else 0)

asyncio.run(main())
