"""Multi-process front for Music Stream (cluster-20261113).

A lightweight TCP proxy stays on MUSIC_PORT (the public port, e.g. 8121) so the
tunnel never has to move. It forwards each client connection, byte for byte
(Range/206 and long movie streams included), to one of MUSIC_WORKERS local
worker processes. Workers bind 127.0.0.1 only, on MUSIC_PORT+100+i.

MUSIC_WORKERS=auto (default) uses min(3, CPU count) — Android lets Termux use
3 of 8 cores. MUSIC_WORKERS=1 keeps the old single-process server.
"""
from __future__ import annotations
import os, socket, subprocess, sys, threading, time, json
from pathlib import Path

ROOT = Path(__file__).resolve().parent
ENV = ROOT / "music.env"
CLUSTER_JSON = ROOT / "lcache" / "cluster.json"
WORKERS_FILE = ROOT / "server.workers"
MAX_WORKERS = 3
WORKER_PORT_GAP = 100  # public 8121 -> workers 8221, 8222, 8223 (never 8120)


def _load_env():
    d = {}
    try:
        for l in ENV.read_text(encoding="utf-8").splitlines():
            if "=" in l and not l.startswith("#"):
                k, v = l.split("=", 1)
                d[k.strip()] = v.strip()
    except Exception:
        pass
    return d


def _cfg(name, default=""):
    return (os.environ.get(name) or _load_env().get(name, default) or default).strip()


def worker_count(raw=None):
    raw = (raw if raw is not None else _cfg("MUSIC_WORKERS", "auto")).strip().lower()
    if raw in ("", "auto", "0"):
        try:
            n = int(os.cpu_count() or 1)
        except Exception:
            n = 1
        return max(1, min(MAX_WORKERS, n))
    try:
        return max(1, min(8, int(raw)))
    except ValueError:
        return 1


def public_bind_port():
    bind = _cfg("MUSIC_BIND", "0.0.0.0") or "0.0.0.0"
    port = int(_cfg("MUSIC_PORT", "8125") or 8125)
    return bind, port


def worker_ports(port=None, n=None):
    port = int(port if port is not None else public_bind_port()[1])
    n = int(n if n is not None else worker_count())
    return [port + WORKER_PORT_GAP + i for i in range(n)]


def should_supervise():
    if os.environ.get("MUSIC_WORKER_ID"):
        return False
    if os.environ.get("MUSIC_CLUSTER_FRONT") == "0":
        return False
    return worker_count() > 1


def parent_alive(pid):
    if not pid:
        return True
    try:
        pid = int(pid)
    except (TypeError, ValueError):
        return True
    if pid <= 0:
        return True
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False
    except Exception:
        return True


def watch_parent():
    """Workers exit when the front/supervisor process is gone."""
    raw = os.environ.get("MUSIC_PARENT_PID")
    if not raw:
        return
    try:
        ppid = int(raw)
    except ValueError:
        return
    if ppid <= 0 or ppid == os.getpid():
        return

    def loop():
        while True:
            time.sleep(2)
            if not parent_alive(ppid):
                os._exit(0)
    threading.Thread(target=loop, daemon=True, name="parent-watch").start()


def _backlog():
    try:
        return max(16, int(_cfg("MUSIC_BACKLOG", "128") or 128))
    except ValueError:
        return 128


def _503():
    body = b"Server starting, try again in a moment."
    return (b"HTTP/1.1 503 Service Unavailable\r\n"
            b"Retry-After: 2\r\n"
            b"Content-Type: text/plain; charset=utf-8\r\n"
            b"Content-Length: " + str(len(body)).encode() + b"\r\n"
            b"Connection: close\r\n\r\n" + body)


class Pool:
    def __init__(self, ports):
        self.ports = list(ports)
        self.active = {p: 0 for p in self.ports}
        self.down_until = {p: 0.0 for p in self.ports}
        self.lock = threading.Lock()

    def pick(self):
        now = time.time()
        with self.lock:
            up = [p for p in self.ports if self.down_until[p] <= now]
            if not up:
                up = list(self.ports)
            p = min(up, key=lambda x: self.active[x])
            self.active[p] += 1
            return p

    def done(self, p, bad=False):
        with self.lock:
            self.active[p] = max(0, self.active[p] - 1)
            if bad:
                self.down_until[p] = time.time() + 2

    def snapshot(self):
        with self.lock:
            return {str(p): self.active[p] for p in self.ports}


def _tune(s):
    # Never inherit the listen socket's accept() timeout (1 s). A 1 s recv
    # timeout would kill HTTP keep-alive and stall long song/video lookups.
    try:
        s.settimeout(None)
    except Exception:
        pass
    try:
        s.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
    except Exception:
        pass
    try:
        s.setsockopt(socket.SOL_SOCKET, socket.SO_KEEPALIVE, 1)
    except Exception:
        pass
    try:
        # Linux: don't delay ACKs on the first bytes of a response.
        if hasattr(socket, "TCP_QUICKACK"):
            s.setsockopt(socket.IPPROTO_TCP, socket.TCP_QUICKACK, 1)
    except Exception:
        pass


def _pipe(src, dst):
    try:
        while True:
            data = src.recv(256 * 1024)
            if not data:
                break
            dst.sendall(data)
    except Exception:
        pass
    try:
        dst.shutdown(socket.SHUT_WR)
    except Exception:
        pass


def _try_connect(port, timeout=2.0):
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        s.settimeout(timeout)
        s.connect(("127.0.0.1", port))
        s.settimeout(None)
        _tune(s)
        return s
    except Exception:
        try:
            s.close()
        except Exception:
            pass
        return None


def handle_client(csock, pool):
    _tune(csock)
    wsock, port, tried = None, None, set()
    try:
        for _ in range(len(pool.ports)):
            port = pool.pick()
            if port in tried:
                pool.done(port)
                continue
            tried.add(port)
            wsock = _try_connect(port)
            if wsock:
                break
            pool.done(port, bad=True)
            port = None
        if not wsock:
            try:
                csock.sendall(_503())
            except Exception:
                pass
            return
        t1 = threading.Thread(target=_pipe, args=(csock, wsock), daemon=True)
        t2 = threading.Thread(target=_pipe, args=(wsock, csock), daemon=True)
        t1.start(); t2.start(); t1.join(); t2.join()
    finally:
        if port is not None:
            pool.done(port)
        for s in (wsock, csock):
            try:
                if s:
                    s.close()
            except Exception:
                pass


def _bind_front(bind, port, backlog):
    # Prefer IPv4; also try IPv6 dual-stack only when bind is :: or blank IPv6.
    fam = socket.AF_INET6 if ":" in bind and bind != "0.0.0.0" else socket.AF_INET
    if bind in ("0.0.0.0", ""):
        fam = socket.AF_INET
    s = socket.socket(fam, socket.SOCK_STREAM)
    s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    if fam == socket.AF_INET6:
        try:
            s.setsockopt(socket.IPPROTO_IPV6, socket.IPV6_V6ONLY, 0)
        except Exception:
            pass
    s.bind((bind, port))
    s.listen(backlog)
    s.settimeout(1.0)
    return s


def _write_cluster(info):
    try:
        CLUSTER_JSON.parent.mkdir(parents=True, exist_ok=True)
        tmp = CLUSTER_JSON.with_suffix(".tmp")
        tmp.write_text(json.dumps(info), encoding="utf-8")
        tmp.replace(CLUSTER_JSON)
    except Exception:
        pass


def _write_workers(pids):
    try:
        WORKERS_FILE.write_text("\n".join(str(p) for p in pids if p) + "\n", encoding="utf-8")
    except Exception:
        pass


def _spawn(script, i, port, n, parent_pid, xt_each):
    env = os.environ.copy()
    env["MUSIC_WORKER_ID"] = str(i)
    env["MUSIC_WORKERS"] = str(n)
    env["MUSIC_PORT"] = str(port)
    env["MUSIC_BIND"] = "127.0.0.1"
    env["MUSIC_PARENT_PID"] = str(parent_pid)
    env["MUSIC_WORKER_BG"] = "1" if i == 0 else "0"
    env["MUSIC_YTDLP_MAX"] = str(xt_each)
    kw = dict(env=env, cwd=str(ROOT))
    if os.name == "nt":
        kw["creationflags"] = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
    return subprocess.Popen([sys.executable, "-u", str(script)], **kw)


def _xt_each(n):
    try:
        total = int(_cfg("MUSIC_YTDLP_MAX", "4") or 4)
    except ValueError:
        total = 4
    return max(2, (total + n - 1) // n) if n else 2


def _wait_up(ports, timeout=20):
    t0 = time.time()
    left = set(ports)
    while left and time.time() - t0 < timeout:
        for p in list(left):
            s = _try_connect(p, timeout=0.4)
            if s:
                try:
                    s.close()
                except Exception:
                    pass
                left.discard(p)
        if left:
            time.sleep(0.2)
    return not left


def _kill_proc(proc):
    if not proc or proc.poll() is not None:
        return
    try:
        if os.name == "nt":
            proc.terminate()
        else:
            proc.terminate()
    except Exception:
        pass
    try:
        proc.wait(timeout=5)
    except Exception:
        try:
            proc.kill()
        except Exception:
            pass


def run_supervisor(script=None):
    """Bind the public port first, start workers, then proxy forever. Returns process exit code."""
    script = str(script or (ROOT / "music_server.py"))
    bind, port = public_bind_port()
    n = worker_count()
    ports = worker_ports(port, n)
    backlog = _backlog()
    print(f"cluster: front {bind}:{port} -> workers 127.0.0.1:{ports} (n={n})", flush=True)
    try:
        front = _bind_front(bind, port, backlog)
    except OSError as e:
        print(f"cluster: could not bind public port {bind}:{port}: {e}", flush=True)
        return 1
    xt = _xt_each(n)
    parent = os.getpid()
    procs = [None] * n

    def start_one(i):
        procs[i] = _spawn(script, i, ports[i], n, parent, xt)
        return procs[i]

    def port_up(p):
        s = _try_connect(p, timeout=0.4)
        if not s:
            return False
        try:
            s.close()
        except Exception:
            pass
        return True

    for i in range(n):
        # If a previous front died without killing workers, reuse them (do not bind-fail or stack a second set).
        if port_up(ports[i]):
            print(f"cluster: worker {i} port {ports[i]} already up; reusing", flush=True)
            continue
        start_one(i)
        print(f"cluster: worker {i} pid {procs[i].pid} port {ports[i]}", flush=True)
    _write_workers([p.pid for p in procs if p])
    _write_cluster({"n": n, "ports": ports, "pid": parent, "workers": [p.pid for p in procs if p], "ts": time.time()})
    ready = _wait_up(ports, timeout=25)
    if not ready:
        print("cluster: warning: not every worker is listening yet; front is up and will retry", flush=True)

    stop = {"on": False}

    def reaper():
        while not stop["on"]:
            time.sleep(2)
            for i, proc in enumerate(list(procs)):
                if stop["on"]:
                    return
                if proc is None or proc.poll() is None:
                    continue
                print(f"cluster: worker {i} exited {proc.returncode}; restarting", flush=True)
                try:
                    start_one(i)
                    _write_workers([p.pid for p in procs if p])
                    _write_cluster({"n": n, "ports": ports, "pid": parent, "workers": [p.pid for p in procs if p], "ts": time.time()})
                except Exception as e:
                    print(f"cluster: restart worker {i} failed: {e}", flush=True)

    threading.Thread(target=reaper, daemon=True, name="worker-reaper").start()

    def shutdown(*_):
        if stop["on"]:
            return
        stop["on"] = True
        print("cluster: shutting down workers", flush=True)
        for p in procs:
            _kill_proc(p)
        try:
            front.close()
        except Exception:
            pass
        try:
            WORKERS_FILE.unlink(missing_ok=True)
        except Exception:
            pass

    import signal
    for sig in (getattr(signal, "SIGTERM", None), getattr(signal, "SIGINT", None)):
        if sig is None:
            continue
        try:
            signal.signal(sig, lambda *_: (shutdown(), os._exit(0)))
        except Exception:
            pass

    pool = Pool(ports)
    print("cluster: front ready", flush=True)
    try:
        while not stop["on"]:
            try:
                csock, _addr = front.accept()
            except socket.timeout:
                continue
            except OSError:
                if stop["on"]:
                    break
                time.sleep(0.05)
                continue
            threading.Thread(target=handle_client, args=(csock, pool), daemon=True).start()
    finally:
        shutdown()
    return 0


if __name__ == "__main__":
    raise SystemExit(run_supervisor(script=str(ROOT / "music_server.py")))
