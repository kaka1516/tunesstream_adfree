import json,sys
from pathlib import Path
from playwright.sync_api import sync_playwright
B="https://tunestream.dpdns.org"
with sync_playwright() as p:
  b=p.chromium.launch(executable_path="/usr/bin/google-chrome",headless=True); pg=b.new_page()
  pg.goto(B+"/login",wait_until="domcontentloaded")
  pg.evaluate("async p=>{await fetch('/api/auth/login',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({u:'loadtest',p}),credentials:'same-origin'})}",Path("/tmp/loadtest.pw").read_text().strip())
  pg.goto(B+"/",wait_until="domcontentloaded"); pg.wait_for_function("()=>typeof K!=='undefined'")
  r=pg.evaluate("""async()=>{const j=async u=>(await fetch(u,{cache:'no-store'})).json();const n=await j('/api/room?k='+K+'&op=new');let bad=0,set=0,got=0,ids=new Set();
   for(let i=0;i<40;i++){const s=await j('/api/room?k='+K+'&op=set&r='+n.r+'&hk='+n.hk+'&id=4NRXx6U8ABQ&t='+i+'&p=1&title=x');if(s.ok)set++;else bad++;
     const g=await j('/api/room?k='+K+'&r='+n.r+'&me=guest1');if(g.id==='4NRXx6U8ABQ')got++;else bad++}
   return {bad,set,got,listeners:(await j('/api/room?k='+K+'&op=set&r='+n.r+'&hk='+n.hk+'&id=4NRXx6U8ABQ&t=1&p=1')).listeners}}""")
  print("ROOM", json.dumps(r)); b.close()
