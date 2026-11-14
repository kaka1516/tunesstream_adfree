# plain HTTP proxy 8500 -> 127.0.0.1:8391; the FIRST /audio response is cut (socket closed) after CUT bytes of body.
import socket,threading,sys,re
CUT=int(sys.argv[1]) if len(sys.argv)>1 else 1200000
state={"cut":0}
def handle(c):
    u=socket.create_connection(("127.0.0.1",8391))
    st={"aud":False}
    def up():
        try:
            while True:
                d=c.recv(65536)
                if not d: break
                if b"GET /audio" in d:
                    st["aud"]=True; state["n"]=state.get("n",0)+1; st["n"]=state["n"]
                    if st["n"]==2: print("HANG req2",flush=True); st["hang"]=True; continue
                u.sendall(d)
        except Exception: pass
    threading.Thread(target=up,daemon=True).start()
    sent=0; hdr=True; buf=b""
    try:
        while True:
            d=u.recv(65536)
            if not d: break
            if st.get("hang"): continue
            if st["aud"] and not state["cut"]:
                sent+=len(d)
                if sent>CUT:
                    state["cut"]=1; print("CUT after",sent,flush=True)
                    c.sendall(d[:max(0,len(d)-(sent-CUT))]); c.shutdown(socket.SHUT_RDWR); c.close(); u.close(); return
            c.sendall(d)
    except Exception: pass
    try: c.close()
    except Exception: pass
s=socket.socket(); s.setsockopt(socket.SOL_SOCKET,socket.SO_REUSEADDR,1); s.bind(("127.0.0.1",8500)); s.listen(50)
while True:
    c,_=s.accept(); threading.Thread(target=handle,args=(c,),daemon=True).start()
