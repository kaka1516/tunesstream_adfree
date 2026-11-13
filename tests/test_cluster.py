"""cluster-20261113: multi-process front, TCP proxy, cross-process file lock.
Run: python tests/test_cluster.py"""
from __future__ import annotations
import json, os, socket, sys, threading, time, http.client, subprocess
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import ms_cluster
import ms_users


def test_worker_count_and_ports():
    assert ms_cluster.worker_count("1") == 1
    assert ms_cluster.worker_count("3") == 3
    assert ms_cluster.worker_count("99") == 8
    assert ms_cluster.worker_count("auto") >= 1
    ports = ms_cluster.worker_ports(8121, 3)
    assert ports == [8221, 8222, 8223]
    assert 8120 not in ports and 8121 not in ports


def test_should_supervise():
    old = os.environ.get("MUSIC_WORKER_ID")
    os.environ.pop("MUSIC_WORKER_ID", None)
    # count is from env/file; we only check the worker-id short-circuit here
    os.environ["MUSIC_WORKER_ID"] = "0"
    assert ms_cluster.should_supervise() is False
    if old is None:
        os.environ.pop("MUSIC_WORKER_ID", None)
    else:
        os.environ["MUSIC_WORKER_ID"] = old


def test_filelock_two_processes(tmp_path=None):
    import tempfile
    d = Path(tempfile.mkdtemp())
    target = d / "n.json"
    target.write_text("0", encoding="utf-8")
    lock = d / "n.lock"
    script = d / "inc.py"
    script.write_text(
        "import json,sys,time\n"
        "from pathlib import Path\n"
        "sys.path.insert(0, %r)\n"
        "import ms_users\n"
        "p=Path(%r); lk=ms_users._FileLock(%r)\n"
        "for i in range(40):\n"
        "    with lk:\n"
        "        n=int(p.read_text() or 0); p.write_text(str(n+1))\n"
        % (str(ROOT), str(target), str(lock)),
        encoding="utf-8",
    )
    ps = [subprocess.Popen([sys.executable, str(script)]) for _ in range(2)]
    for p in ps:
        assert p.wait(timeout=30) == 0
    assert int(target.read_text()) == 80, target.read_text()


def test_store_sessions_across_processes():
    import tempfile
    d = Path(tempfile.mkdtemp())
    (d / "users.json").write_text(json.dumps({"version": 1, "users": {
        "alice": {"role": "user", "hash": "x", "pwv": 1, "created": 1, "last_login": None}
    }}), encoding="utf-8")
    script = d / "sess.py"
    script.write_text(
        "import sys\n"
        "sys.path.insert(0, %r)\n"
        "import ms_users\n"
        "st=ms_users.Store(%r)\n"
        "tok=st.new_session('alice', True)\n"
        "print(tok or '')\n"
        % (str(ROOT), str(d)),
        encoding="utf-8",
    )
    ps = [subprocess.Popen([sys.executable, str(script)], stdout=subprocess.PIPE, text=True) for _ in range(4)]
    toks = []
    for p in ps:
        out, _ = p.communicate(timeout=30)
        assert p.returncode == 0, out
        toks.append(out.strip())
    assert all(toks) and len(set(toks)) == 4
    st = ms_users.Store(d)
    ok = 0
    for t in toks:
        info, _ = st.session(t)
        if info and info.get("u") == "alice":
            ok += 1
    assert ok == 4, (ok, toks)


class _H(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass
    def do_GET(self):
        if self.path.startswith("/slow"):
            body = (b"abcdef" * 20000)  # 120 KB
            self.send_response(206)
            self.send_header("Content-Type", "application/octet-stream")
            self.send_header("Content-Range", f"bytes 0-{len(body)-1}/{len(body)}")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            for i in range(0, len(body), 8000):
                self.wfile.write(body[i:i+8000])
                self.wfile.flush()
            return
        body = ("ok-%s" % self.server.server_port).encode()
        self.send_response(200)
        self.send_header("Content-Type", "text/plain")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def _serve(port):
    s = ThreadingHTTPServer(("127.0.0.1", port), _H)
    s.server_port = port
    t = threading.Thread(target=s.serve_forever, daemon=True)
    t.start()
    return s


def _free_port():
    s = socket.socket(); s.bind(("127.0.0.1", 0)); p = s.getsockname()[1]; s.close(); return p


def test_proxy_streams_and_balances():
    a, b = _free_port(), _free_port()
    sa, sb = _serve(a), _serve(b)
    time.sleep(0.1)
    front_port = _free_port()
    front = ms_cluster._bind_front("127.0.0.1", front_port, 32)
    pool = ms_cluster.Pool([a, b])
    stop = {"on": False}

    def loop():
        while not stop["on"]:
            try:
                c, _ = front.accept()
            except socket.timeout:
                continue
            except OSError:
                break
            threading.Thread(target=ms_cluster.handle_client, args=(c, pool), daemon=True).start()
    threading.Thread(target=loop, daemon=True).start()
    time.sleep(0.05)
    seen = set()
    for _ in range(8):
        h = http.client.HTTPConnection("127.0.0.1", front_port, timeout=5)
        h.request("GET", "/")
        r = h.getresponse(); body = r.read().decode(); h.close()
        assert r.status == 200 and body.startswith("ok-")
        seen.add(body)
    assert seen == {f"ok-{a}", f"ok-{b}"}, seen
    h = http.client.HTTPConnection("127.0.0.1", front_port, timeout=8)
    h.request("GET", "/slow")
    r = h.getresponse(); data = r.read(); h.close()
    assert r.status == 206 and len(data) == 120000, (r.status, len(data))
    stop["on"] = True
    try:
        front.close(); sa.shutdown(); sb.shutdown()
    except Exception:
        pass


def test_proxy_503_when_workers_down():
    front_port = _free_port()
    front = ms_cluster._bind_front("127.0.0.1", front_port, 8)
    pool = ms_cluster.Pool([_free_port()])  # nothing listening
    threading.Thread(target=lambda: (ms_cluster.handle_client(front.accept()[0], pool)), daemon=True).start()
    h = http.client.HTTPConnection("127.0.0.1", front_port, timeout=5)
    h.request("GET", "/")
    r = h.getresponse(); body = r.read(); h.close()
    assert r.status == 503 and b"try again" in body.lower() or b"Server starting" in body
    front.close()


def test_tune_clears_timeout():
    s = socket.socket(); s.settimeout(1.0)
    ms_cluster._tune(s)
    assert s.gettimeout() is None
    s.close()

if __name__ == "__main__":
    tests = [test_worker_count_and_ports, test_should_supervise, test_tune_clears_timeout, test_filelock_two_processes,
             test_store_sessions_across_processes, test_proxy_streams_and_balances,
             test_proxy_503_when_workers_down]
    failed = 0
    # FileLock lives in ms_users after the patch; if the test is run before the patch, skip later.
    for fn in tests:
        try:
            fn(); print("ok", fn.__name__)
        except Exception as e:
            failed += 1
            print("FAIL", fn.__name__, type(e).__name__, e)
    raise SystemExit(1 if failed else 0)
