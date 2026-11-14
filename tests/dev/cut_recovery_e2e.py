import json,time,sys,subprocess
from playwright.sync_api import sync_playwright
K=[l.split('=',1)[1].strip() for l in open('/workspace/repo/music-stream/music.env') if l.startswith('MUSIC_KEY=')][0]
HID=len(sys.argv)>1 and sys.argv[1]=="hidden"
with sync_playwright() as p:
  b=p.chromium.launch(executable_path="/usr/bin/google-chrome",headless=True,args=["--autoplay-policy=no-user-gesture-required"])
  pg=b.new_page(); log=[]
  pg.on("request",lambda r: log.append(("REQ",r.headers.get("range"))) if "/audio" in r.url else None)
  pg.on("requestfailed",lambda r: log.append(("FAIL",r.failure)) if "/audio" in r.url else None)
  pg.goto("http://127.0.0.1:8500/?k="+K,wait_until="domcontentloaded"); pg.wait_for_function("()=>typeof play==='function'",timeout=30000)
  if HID: pg.evaluate("()=>{Object.defineProperty(document,'hidden',{configurable:true,get:()=>true});Object.defineProperty(document,'visibilityState',{configurable:true,get:()=>'hidden'});document.dispatchEvent(new Event('visibilitychange'))}")
  pg.evaluate("()=>{radOn=false;localStorage.gapless='0';play({id:'4NRXx6U8ABQ',title:'long',channel:''})}")
  t0=time.time()
  for i in range(16):
    time.sleep(6)
    s=pg.evaluate("()=>{const a=M;let bf=0;try{bf=a.buffered.length?a.buffered.end(a.buffered.length-1):0}catch(e){};return {ct:+a.currentTime.toFixed(1),buf:+bf.toFixed(1),rs:a.readyState,ns:a.networkState,p:a.paused,err:a.error&&a.error.code,ev:__msLife.slice(-5).map(e=>e.ev).join(',')}}")
    if i==3 and False: pg.evaluate("()=>{try{M.currentTime=Math.max(0,(M.buffered.length?M.buffered.end(0):30)-3)}catch(e){}}")  # jump to the edge of what arrived
    if i==1: print("seek", pg.evaluate("()=>{const e=M.buffered.length?M.buffered.end(M.buffered.length-1):0;M.currentTime=Math.max(0,e-4);return e}"))
    print(int(time.time()-t0),json.dumps(s))
  print(log)
  b.close()
