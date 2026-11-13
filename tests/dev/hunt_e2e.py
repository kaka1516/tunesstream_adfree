import json,time
from pathlib import Path
from playwright.sync_api import sync_playwright
B="https://tunestream.dpdns.org";R=[]
def ok(n,c,i=None): R.append((n,c));print(("PASS " if c else "FAIL ")+n, json.dumps(i)[:400] if i is not None else "")
with sync_playwright() as p:
  b=p.chromium.launch(executable_path="/usr/bin/google-chrome",headless=True,args=["--autoplay-policy=no-user-gesture-required"])
  ctx=b.new_context(viewport={"width":390,"height":844},is_mobile=True,has_touch=True); pg=ctx.new_page()
  pg.goto(B+"/login",wait_until="domcontentloaded")
  st=pg.evaluate("async p=>(await fetch('/api/auth/login',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({u:'loadtest',p}),credentials:'same-origin'})).status",Path("/tmp/loadtest.pw").read_text().strip())
  ok("login",st==200,st)
  pg.goto(B+"/",wait_until="domcontentloaded"); pg.wait_for_function("()=>typeof play==='function'&&typeof K!=='undefined'",timeout=30000)
  ev=lambda s:pg.evaluate(s)
  api=ev("""async()=>{const t=async u=>{const t0=performance.now();const r=await fetch(u);let j=null;try{j=await r.json()}catch(e){};return {s:r.status,n:Array.isArray(j)?j.length:(j&&typeof j==='object'?Object.keys(j).length:0),ms:Math.round(performance.now()-t0)}};
    return {search:await t('/api/search?k='+K+'&q=kesariya'),suggest:await t('/api/suggest?k='+K+'&q=arij'),home:await t('/api/home?k='+K),shorts:await t('/api/shorts?k='+K+'&n=10&page=0&seeds=&ex='),lyrics:await t('/api/lyrics?k='+K+'&id=BddP6PYo2gs'),vinfo:await t('/api/vinfo?k='+K+'&id=BddP6PYo2gs'),state:await t('/api/state?k='+K),list:await t('/api/list?k='+K+'&id=PL4fGSI1pDJn6puJdseH2Rt9sMvt9E2M4i')}}""")
  for k,v in api.items(): ok("api "+k, v['s']==200 and v['n']>0, v)
  # search UI + play audio
  ev("()=>{setMode('a');$('q').value='kesariya';search('kesariya')}"); pg.wait_for_function("()=>document.querySelectorAll('#list li').length>3",timeout=30000)
  ev("()=>{document.querySelector('#list li .meta').click()}"); time.sleep(8)
  a=ev("()=>({id:cur()&&cur().id,ct:M.currentTime,p:M.paused,ql:queue.length})"); ok("search+tap plays audio", a['ct']>1 and not a['p'], a)
  # Next
  ev("()=>{queue.push({id:'4NRXx6U8ABQ',title:'t',channel:''});save();next()}"); time.sleep(7)
  n=ev("()=>({id:cur()&&cur().id,ct:M.currentTime,p:M.paused})"); ok("Next plays next song", n['id']!=a['id'] and n['ct']>0.5, n)
  # like persists across reload
  ev("()=>{const L=liked();if(!L.some(x=>x.id===cur().id))toggleLike(cur())}"); lid=n['id']
  # setting persistence
  ev("()=>{localStorage.gapless='0'}")
  # video 720
  ev("()=>{localStorage.vres='720';setMode('v')}"); time.sleep(12)
  v=ev("()=>({mode,h:VID.videoHeight,ct:VID.currentTime,p:VID.paused,res:typeof vres!=='undefined'?vres:''})"); ok("video plays at >=720p", v['h']>=720 and v['ct']>1, v)
  ev("()=>setMode('a')"); time.sleep(3); ev("()=>{try{M.currentTime=40}catch(e){};window.__msPosSave&&__msPosSave()}"); time.sleep(1.5)
  pg.reload(wait_until="domcontentloaded"); pg.wait_for_function("()=>typeof liked==='function'",timeout=30000); time.sleep(4)
  r=ev("""()=>({liked:liked().some(x=>x.id===%s),gap:localStorage.gapless,pos:JSON.parse(localStorage.getItem('local.msPos')||'null'),resumeUI:!!(document.getElementById('resume20')||document.querySelector('[id^=resume]')),qrestored:queue.length})"""%json.dumps(lid))
  ok("like persists after reload", r['liked'], None); ok("setting persists (gapless off)", r['gap']=='0', r['gap'])
  ok("resume position saved + offered", bool(r['pos']) and r['pos'].get('t',0)>=30 and r['resumeUI'], {"pos":r['pos'] and {k:r['pos'][k] for k in ('id','t')},"ui":r['resumeUI'],"q":r['qrestored']})
  ev("()=>{localStorage.gapless='1'}")
  # Shorts tab feed
  ev("()=>{$('q').value='';document.getElementById('shtab').click()}"); time.sleep(8)
  s=ev("()=>({shLoading,q:$('q').value,view,n:document.querySelectorAll('#list li').length,shRes:(shRes||[]).length})"); ok("Shorts feed loads", s['shRes']>3, s)
  time.sleep(15); print("SH_AFTER23", ev("()=>({shLoading,shRes:(shRes||[]).length,empty:$('empty').textContent})"))
  print("PROTO", ev("()=>[...new Set(performance.getEntriesByType('resource').map(e=>e.nextHopProtocol))]"))
  print("DIRECT", ev("""async()=>{const t0=performance.now();const r=await fetch('/api/shorts?k='+K+'&n=20&page=0&seeds='+encodeURIComponent(shortsSeeds().join(','))+'&ex=');await r.text();return {s:r.status,ms:Math.round(performance.now()-t0)}}"""))
  b.close()
print("HUNT", sum(1 for x in R if x[1]),"/",len(R))
