#!/usr/bin/env python3
"""Touch gesture checks (CDP touch events, mobile emulation) on the public URL. Never prints secrets."""
import json, time
from pathlib import Path
from playwright.sync_api import sync_playwright
BASE="https://tunestream.dpdns.org"; R=[]
def ok(name,cond,info=None):
    R.append((("PASS" if cond else "FAIL"),name,info)); print(("PASS " if cond else "FAIL ")+name, json.dumps(info)[:600] if info is not None else "")
def main():
  with sync_playwright() as p:
    b=p.chromium.launch(executable_path="/usr/bin/google-chrome",headless=True,args=["--autoplay-policy=no-user-gesture-required","--disable-dev-shm-usage"])
    ctx=b.new_context(viewport={"width":390,"height":844},is_mobile=True,has_touch=True,device_scale_factor=2,
        user_agent="Mozilla/5.0 (Linux; Android 14; SM-S916B) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Mobile Safari/537.36")
    pg=ctx.new_page(); cdp=ctx.new_cdp_session(pg)
    pg.goto(BASE+"/login",wait_until="domcontentloaded",timeout=45000)
    st=pg.evaluate("""async p=>{const r=await fetch('/api/auth/login',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({u:'loadtest',p}),credentials:'same-origin'});return r.status}""",Path("/tmp/loadtest.pw").read_text().strip())
    assert st==200,st
    pg.goto(BASE+"/",wait_until="domcontentloaded",timeout=45000)
    pg.wait_for_function("()=>typeof startRadio==='function'&&typeof window.__msPtrRefresh==='function'",timeout=30000)
    ok("build", True, pg.evaluate("()=>document.querySelector('meta[name=ms-build]').content"))
    def touch(pts, steps=8, hold=0):
        (x0,y0),(x1,y1)=pts
        cdp.send("Input.dispatchTouchEvent",{"type":"touchStart","touchPoints":[{"x":x0,"y":y0}]})
        if hold: time.sleep(hold)
        for i in range(1,steps+1):
            cdp.send("Input.dispatchTouchEvent",{"type":"touchMove","touchPoints":[{"x":x0+(x1-x0)*i/steps,"y":y0+(y1-y0)*i/steps}]}); time.sleep(0.016)
        cdp.send("Input.dispatchTouchEvent",{"type":"touchEnd","touchPoints":[]})
        time.sleep(0.4)
    S=lambda: pg.evaluate("""()=>{const a=(typeof M!=='undefined'&&M)||document.getElementById('aud');const c=cur()||{};return {id:c.id||'',ct:+(a.currentTime||0).toFixed(2),paused:a.paused,np:document.getElementById('np').classList.contains('open'),menu:!!document.querySelector('.menu.open'),view,life:__msLife.slice(-8).map(e=>e.ev).join(',')}}""")
    pg.evaluate("()=>startRadio({id:'4NRXx6U8ABQ',title:'g',channel:'',dur:0})")
    t0=time.time()
    while time.time()-t0<40 and not (S()['ct']>1 and not S()['paused']): time.sleep(0.5)
    pg.evaluate("()=>{document.getElementById('np').classList.remove('open');window.scrollTo(0,0);view='res';tabs();try{showHomeShell()}catch(e){}}")
    time.sleep(0.5)
    # 1 pull to refresh while playing
    pg.evaluate("()=>window.scrollTo(0,0)"); time.sleep(0.3); sy=pg.evaluate("()=>[scrollY,document.getElementById('np').classList.contains('open')]")
    a=S(); touch(((195,260),(195,520)),steps=14); time.sleep(0.15)
    spin=pg.evaluate("()=>document.getElementById('ptr').classList.contains('spin')")
    time.sleep(2.5); b2=S()
    ok("pull-to-refresh fires, spinner, playback continues", spin and 'ptr-refresh' in b2['life'] and not b2['paused'] and b2['ct']>a['ct']+1 and b2['id']==a['id'], {"spin":spin,"sy":sy,"b":b2})
    # short pull should not refresh
    n0=pg.evaluate("()=>__msLife.filter(e=>e.ev==='ptr-refresh').length"); touch(((195,260),(195,320)),steps=5)
    ok("short pull ignored", pg.evaluate("()=>__msLife.filter(e=>e.ev==='ptr-refresh').length")==n0)
    # 2 swipe up on mini opens full player
    mb=pg.evaluate("()=>{const r=document.getElementById('mini').getBoundingClientRect();return [r.left+r.width*0.4,r.top+r.height/2]}")
    touch(((mb[0],mb[1]),(mb[0],mb[1]-120)),steps=8); ok("mini swipe-up opens player", S()['np'])
    # 3 swipe left on full player = next
    a=S(); touch(((330,330),(60,340)),steps=10); time.sleep(3); b2=S()
    ok("np swipe-left = next", b2['id']!=a['id'] and 'swipe-next' in pg.evaluate("()=>__msLife.map(e=>e.ev).join(',')"), {"a":a['id'],"b":b2['id']})
    # 4 swipe right = previous
    pg.evaluate("()=>{try{M.currentTime=1}catch(e){}}"); time.sleep(0.3)
    touch(((60,330),(330,340)),steps=10); time.sleep(3); c2=S()
    ok("np swipe-right = previous", c2['id']==a['id'], {"want":a['id'],"got":c2['id']})
    # 5 seek bar drag does not change song
    sk=pg.evaluate("()=>{const r=document.getElementById('seek').getBoundingClientRect();return [r.left+20,r.top+r.height/2,r.right-30]}")
    i0=S()['id']; touch(((sk[0],sk[1]),(sk[2],sk[1])),steps=10); time.sleep(1.5)
    ok("seek-bar drag not treated as swipe", S()['id']==i0)
    # 6 swipe down closes full player
    touch(((195,250),(195,500)),steps=10); ok("np swipe-down minimizes", not S()['np'])
    # 7 mini swipe left = next
    a=S(); mb=pg.evaluate("()=>{const r=document.getElementById('mini').getBoundingClientRect();return [r.left+r.width*0.6,r.top+r.height/2]}")
    touch(((mb[0],mb[1]),(mb[0]-200,mb[1])),steps=10); time.sleep(3)
    ok("mini swipe-left = next", S()['id']!=a['id'])
    # 8 long-press a search row opens its menu, does not play
    pg.evaluate("()=>{$('q').value='arijit singh';search('arijit singh')}")
    pg.wait_for_function("()=>document.querySelectorAll('#list li [data-m]').length>2",timeout=30000); time.sleep(0.8)
    pg.evaluate("()=>window.scrollTo(0,0)")
    li=pg.evaluate("()=>{const r=document.querySelectorAll('#list li')[1].querySelector('.meta,img').getBoundingClientRect();return [r.left+r.width/2,r.top+r.height/2]}")
    i0=S()['id']; touch(((li[0],li[1]),(li[0]+1,li[1]+1)),steps=1,hold=0.75); time.sleep(0.6); s2=S()
    ok("long-press opens row menu, no play", s2['menu'] and s2['id']==i0, s2)
    # 9 left-edge swipe = back (closes the menu)
    touch(((6,420),(160,425)),steps=10); ok("edge swipe back closes top layer", not S()['menu'])
    # 10 PTR on results re-runs search
    pg.evaluate("()=>window.scrollTo(0,0)"); n0=pg.evaluate("()=>__msLife.filter(e=>e.ev==='ptr-refresh').length")
    touch(((195,300),(195,560)),steps=14); time.sleep(2)
    ok("pull-to-refresh on results", pg.evaluate("()=>__msLife.filter(e=>e.ev==='ptr-refresh').length")==n0+1 and not S()['paused'])
    # 11 PTR does NOT fire when scrolled down
    pg.evaluate("()=>window.scrollTo(0,400)"); time.sleep(0.3); n0=pg.evaluate("()=>__msLife.filter(e=>e.ev==='ptr-refresh').length")
    touch(((195,300),(195,560)),steps=14); ok("no refresh when not at top", pg.evaluate("()=>__msLife.filter(e=>e.ev==='ptr-refresh').length")==n0)
    # 12 Shorts overlay: vertical swipe still moves to next short, no PTR
    ok_sh=pg.evaluate("""async()=>{const r=await fetch('/api/shorts?k='+K+'&n=6&page=0&seeds=&ex=');const L=r.ok?await r.json():[];if(!L.length)return false;openShorts(L,0);return true}""")
    time.sleep(2); i0=pg.evaluate("()=>shI"); n0=pg.evaluate("()=>__msLife.filter(e=>e.ev==='ptr-refresh').length")
    touch(((195,600),(195,250)),steps=6); time.sleep(1.2)
    ok("shorts vertical swipe still works", ok_sh and pg.evaluate("()=>shI")==i0+1 and pg.evaluate("()=>__msLife.filter(e=>e.ev==='ptr-refresh').length")==n0, {"shI":pg.evaluate("()=>shI")})
    pg.evaluate("()=>closeShorts()")
    # 13 double-tap right/left third of video = +/-10 s
    pg.evaluate("()=>{try{setMode('v')}catch(e){};openNp(true)}"); time.sleep(6)
    r=pg.evaluate("()=>{const r=document.getElementById('stage').getBoundingClientRect();return [r.left,r.top,r.width,r.height]}")
    def tap(x,y):
        cdp.send("Input.dispatchTouchEvent",{"type":"touchStart","touchPoints":[{"x":x,"y":y}]}); time.sleep(0.05)
        cdp.send("Input.dispatchTouchEvent",{"type":"touchEnd","touchPoints":[]}); time.sleep(0.12)
    t1=pg.evaluate("()=>M.currentTime"); x=r[0]+r[2]*0.85; y=r[1]+r[3]*0.5; tap(x,y); tap(x,y); time.sleep(0.6); t2=pg.evaluate("()=>M.currentTime")
    ok("double-tap right = +10s", t2-t1>8.5, {"t1":t1,"t2":t2,"mode":pg.evaluate("()=>mode")})
    x=r[0]+r[2]*0.15; t1=pg.evaluate("()=>M.currentTime"); tap(x,y); tap(x,y); time.sleep(0.6); t2=pg.evaluate("()=>M.currentTime")
    ok("double-tap left = -10s", t1-t2>8.5, {"t1":t1,"t2":t2})
    pg.evaluate("()=>{try{setMode('a')}catch(e){}}")
    pg.screenshot(path="/tmp/gest_final.png")
    b.close()
  f=[r for r in R if r[0]=="FAIL"]; print("GEST_RESULT", len(R)-len(f), "/", len(R)); 
if __name__=="__main__": main()
