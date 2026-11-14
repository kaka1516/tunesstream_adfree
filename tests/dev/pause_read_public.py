import requests,time,sys
from pathlib import Path
B="https://tunestream.dpdns.org"; P=int(sys.argv[1]) if len(sys.argv)>1 else 150
s=requests.Session(); s.headers["User-Agent"]="Mozilla/5.0 (Linux; Android 14) Chrome/130 Mobile"
r=s.post(B+"/api/auth/login",json={"u":"loadtest","p":Path("/tmp/loadtest.pw").read_text().strip()}); print("login",r.status_code)
r=s.get(B+"/audio?id=4NRXx6U8ABQ&q=std",headers={"Range":"bytes=0-"},stream=True,timeout=60)
cl=int(r.headers.get("Content-Length",0)); print(r.status_code,"CL",cl)
it=r.raw; got=0
while got<700000:
    d=it.read(65536); 
    if not d: break
    got+=len(d)
print("read",got,"pause",P,"s"); time.sleep(P); t0=time.time()
try:
    while got<cl:
        d=it.read(262144)
        if not d: break
        got+=len(d)
except Exception as e: print("err",type(e).__name__,str(e)[:120])
print("final",got,"of",cl,"COMPLETE" if got>=cl else "TRUNCATED",round(time.time()-t0,1),"s")
