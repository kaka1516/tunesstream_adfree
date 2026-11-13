"""Shared on-disk intro (head) cache for audio byte ranges.

Approach (not a copy of any one repo): cache ``Range: bytes=0-N`` on disk and
serve a 206 from that file while the rest is fetched upstream — the same idea
used by yt-dlp's partial/probe pipeline, Invidious/Piped videoplayback Range
proxying, and nginx slice / Cloudflare range-cache. See CREDITS.md.

Must never break playback: every reader falls back to None on any error so the
caller can hit upstream. Writers use a temp file + os.replace (atomic) and a
cross-process lock so multi-core workers can share the directory.
"""
from __future__ import annotations

import json, os, re, threading, time
from pathlib import Path

SAFE = re.compile(r"[^A-Za-z0-9_-]+")
_L = threading.Lock()


def _lock(path: Path, timeout=2.0):
    """Best-effort exclusive lock (fcntl on POSIX, msvcrt on Windows)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    lf = open(str(path) + ".lock", "a+b")
    end = time.time() + timeout
    while True:
        try:
            if os.name == "nt":
                import msvcrt
                lf.seek(0)
                try:
                    lf.write(b"\0")
                    lf.flush()
                    msvcrt.locking(lf.fileno(), msvcrt.LK_NBLCK, 1)
                except OSError:
                    if time.time() >= end:
                        return lf  # proceed without a lock rather than stall playback
                    time.sleep(0.05)
                    continue
            else:
                import fcntl
                fcntl.flock(lf.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            return lf
        except (OSError, BlockingIOError):
            if time.time() >= end:
                return lf
            time.sleep(0.05)


def _unlock(lf):
    try:
        if os.name == "nt":
            import msvcrt
            lf.seek(0)
            msvcrt.locking(lf.fileno(), msvcrt.LK_UNLCK, 1)
        else:
            import fcntl
            fcntl.flock(lf.fileno(), fcntl.LOCK_UN)
    except Exception:
        pass
    try:
        lf.close()
    except Exception:
        pass


class HeadCache:
    def __init__(self, root: Path, max_bytes=300 << 20, head_bytes=384 << 10):
        self.dir = Path(root)
        self.dir.mkdir(parents=True, exist_ok=True)
        self.max_bytes = int(max_bytes)
        self.head_bytes = int(head_bytes)

    def paths(self, vid, fq):
        safe = SAFE.sub("_", f"{vid}_{fq}")[:80]
        return self.dir / f"{safe}.bin", self.dir / f"{safe}.json"

    def get(self, vid, fq):
        """Return {data, size, ctype, n} or None. Never raises to the caller."""
        try:
            binp, metap = self.paths(vid, fq)
            if not (binp.exists() and metap.exists()):
                return None
            meta = json.loads(metap.read_text(encoding="utf-8"))
            data = binp.read_bytes()
            size = int(meta.get("size") or 0)
            n = int(meta.get("n") or 0)
            if size <= 0 or not data or n <= 0 or len(data) != n:
                return None
            if n > size:
                return None
            try:
                os.utime(binp, None)
                os.utime(metap, None)
            except Exception:
                pass
            return {"data": data, "size": size, "ctype": meta.get("ctype") or "application/octet-stream", "n": n, "t": meta.get("t") or 0}
        except Exception:
            return None

    def put(self, vid, fq, data, size, ctype="application/octet-stream"):
        """Atomic write. Returns True if stored. Evicts LRU down to max_bytes."""
        try:
            if not data or size <= 0:
                return False
            data = bytes(data)
            if len(data) > size:
                data = data[:size]
            binp, metap = self.paths(vid, fq)
            self.dir.mkdir(parents=True, exist_ok=True)
            try:
                if binp.exists() and metap.exists():
                    oldm = json.loads(metap.read_text(encoding="utf-8"))
                    if int(oldm.get("size") or 0) == int(size) and int(oldm.get("n") or 0) >= len(data) and binp.stat().st_size == int(oldm.get("n") or 0):
                        os.utime(binp, None)
                        os.utime(metap, None)
                        return True
            except Exception:
                pass
            tmp = binp.with_suffix(".bin.tmp")
            jtmp = metap.with_suffix(".json.tmp")
            lf = _lock(binp)
            try:
                tmp.write_bytes(data)
                jtmp.write_text(json.dumps({"size": int(size), "ctype": ctype or "application/octet-stream", "n": len(data), "t": time.time(), "vid": vid, "q": fq}), encoding="utf-8")
                os.replace(tmp, binp)
                os.replace(jtmp, metap)
            finally:
                _unlock(lf)
                for p in (tmp, jtmp):
                    try:
                        p.unlink()
                    except Exception:
                        pass
            self.evict()
            return True
        except Exception:
            return False

    def evict(self):
        try:
            files = list(self.dir.glob("*.bin"))
            total = 0
            rec = []
            for f in files:
                try:
                    st = f.stat()
                    rec.append((st.st_mtime, st.st_size, f))
                    total += st.st_size
                except Exception:
                    pass
            if total <= self.max_bytes:
                return
            rec.sort()
            for _mt, sz, f in rec:
                if total <= self.max_bytes:
                    break
                lf = _lock(f, timeout=0.2)
                try:
                    jp = f.with_suffix(".json")
                    f.unlink()
                    try:
                        jp.unlink()
                    except Exception:
                        pass
                    total -= sz
                except Exception:
                    pass
                finally:
                    _unlock(lf)
        except Exception:
            pass

    def stats(self):
        try:
            files = list(self.dir.glob("*.bin"))
            nbytes = 0
            for f in files:
                try:
                    nbytes += f.stat().st_size
                except Exception:
                    pass
            return {"n": len(files), "bytes": nbytes, "max": self.max_bytes, "head_bytes": self.head_bytes}
        except Exception:
            return {"n": 0, "bytes": 0, "max": self.max_bytes, "head_bytes": self.head_bytes}


# process-wide default (tests / callers override root)
_default = None


def init(root, max_mb=300, head_kb=384):
    global _default
    _default = HeadCache(Path(root), max_bytes=max(32, int(max_mb)) << 20, head_bytes=max(96, int(head_kb)) << 10)
    return _default


def get(vid, fq):
    return _default.get(vid, fq) if _default else None


def put(vid, fq, data, size, ctype="application/octet-stream"):
    return _default.put(vid, fq, data, size, ctype) if _default else False


def stats():
    return _default.stats() if _default else {"n": 0, "bytes": 0}
