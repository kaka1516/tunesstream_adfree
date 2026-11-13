# Front-only recovery: bind 8121 and proxy to already-running workers. Does not spawn or kill workers.
import socket, threading, time, sys
from pathlib import Path
ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
import ms_cluster

BIND, PORT, WORKERS, BACKLOG = "0.0.0.0", 8121, [8221, 8222, 8223], 128
front = ms_cluster._bind_front(BIND, PORT, BACKLOG)
pool = ms_cluster.Pool(WORKERS)
print("front-only ready %s:%s -> %s" % (BIND, PORT, WORKERS), flush=True)
while True:
    try:
        csock, _addr = front.accept()
    except socket.timeout:
        continue
    except OSError:
        time.sleep(0.05)
        continue
    threading.Thread(target=ms_cluster.handle_client, args=(csock, pool), daemon=True).start()
