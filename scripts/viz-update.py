# adult-viz-20261111 adult tier added
#!/usr/bin/env python3
"""Automatic visuals catalog updater for Music Stream.

Pulls new dance clips and Poly Haven HDRIs (Butterchurn presets dropped 2026-11-11) from an
allowlisted set of CC0/CC-BY/CMU/MIT sources. License is checked per item.
Unclear, franchise, swimwear, or not-clearly-adult character models are skipped.

Run weekly (4:00 IST Monday) at low priority. Caps: 50 MB network per run,
1 GB of updater-managed files on disk. Downloads go to a temp dir, are
validated, then atomically merged into the catalogs. The last-good catalog
is kept for rollback. No server restart; the player reads clips.json and
rev.js on the next open.

Usage:
  python3 viz-update.py            # no-op if a successful run is < 6 days old
  python3 viz-update.py --once     # run now (tests / manual)
  python3 viz-update.py --dry-run  # list what would be added, write nothing
  python3 viz-update.py --limit 1 --max-bytes 400000 --once
  python3 viz-update.py --off      # disable future automatic runs
  python3 viz-update.py --on       # re-enable
"""
from __future__ import annotations

import argparse, csv, io, json, os, random, re, shutil, sys, tempfile, time, zipfile
from datetime import datetime, timezone, timedelta
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

IST = timezone(timedelta(hours=5, minutes=30))
UA = "MusicStreamVizUpdate/1.0 (personal self-hosted player)"
SCRIPT = Path(__file__).resolve()
ROOT = SCRIPT.parents[1]  # music-stream/

# Hard allowlist of URL prefixes (redirects off this list are rejected).
ALLOW_URLS = (
    "https://huggingface.co/datasets/Sanami/open-vrma/",
    "https://huggingface.co/datasets/Sanami/open-vrma/resolve/",
    "https://huggingface.co/api/resolve-cache/datasets/Sanami/open-vrma/",
    "https://api.polyhaven.com/",
    "https://dl.polyhaven.org/",
    "https://cdn.polyhaven.org/",
    # notrippy-20261111: butterchurn-presets removed (Trippy visualizer removed)
)

# Hugging Face may redirect file bytes to these hosts; only accepted for family=open-vrma.
HF_FILE_HOSTS = {
    "huggingface.co",
    "cdn-lfs.huggingface.co",
    "cdn-lfs-us-1.huggingface.co",
    "cdn-lfs-eu-1.huggingface.co",
    "cas-bridge.xethub.hf.co",
    "cas-bridge.hf.space",
}

ALLOW_LICENSES = {
    "licenseref-cmu-mocap",
    "cc0", "cc0-1.0", "cc0 1.0",
    "cc-by", "cc-by-3.0", "cc-by-4.0", "cc by 3.0", "cc by 4.0", "cc by",
    "mit", "public domain", "pd",
}

# Tight dance filter. kind must be dance; skip walks, fights, playground,
# animal impersonations, franchise names, swimwear, and mis-tagged clips.
RE_SKIP = re.compile(
    r"(mickey|minnie|disney|mario|luigi|pikachu|pokemon|naruto|goku|saiyan|"
    r"sonic|zelda|\blink\b|spiderman|batman|hatsune|miku|gundam|hello kitty|"
    r"playground|climb|baseball|wash windows|rangeofmotion|range of motion|"
    r"motorcycle pose|casual walk|walk/wander|\bwander\b|stepstool|"
    r"egyptian walk|\bwalk\b|\brun\b|\bjog\b|combat|fight|punch|kick|boxing|"
    r"sword|melee|shoot|gun|zombie|nude|nsfw|hentai|porn|sex|"
    r"bikini|swimsuit|swimwear|lingerie|"
    r"dancing bear|dancing animal|dancing ant|monkey sequence|"
    r"avoid attacker|defensive guard|pesky bug|banana|bannana|rugpull|"
    r"rug pull|fall on face|summersult|summersault|hang on ropes|"
    r"walk(ing)?|stepping|steps backwards|turning|ball mount|"
    r"flp twst fall|twist fall|lean forward|sit on|high stool|hand signals)",
    re.I,
)
RE_FRANCHISE = re.compile(
    r"(mickey|minnie|disney|mario|luigi|pikachu|pokemon|naruto|goku|sonic|"
    r"zelda|spiderman|batman|hatsune|miku|gundam|harry potter|star wars)",
    re.I,
)
RE_SWIM = re.compile(r"(bikini|swimsuit|swimwear|lingerie|nude|nsfw|hentai)", re.I)
# adult-viz-20261111: adult tier still never allows nudity / youth / franchise / fetish.
RE_NUDE = re.compile(
    r"(nude|naked|nsfw|hentai|porn|sex\b|fetish|xxx|explicit|genital|nipple|topless|bottomless)",
    re.I,
)
RE_YOUTH = re.compile(
    r"(loli|shota|chibi|toddler|infant|underage|preteen|\bchild\b|\bkids?\b|"
    r"young.?girl|young.?boy|school.?girl|school.?boy|little.?girl|little.?boy)",
    re.I,
)
RE_ADULT_MOVES = re.compile(
    r"(twerk|body.?roll|hip.?sway|hip.?roll|pole|dancehall|reggaeton|salsa|bachata|"
    r"merengue|cumbia|samba|rumba|cha.?cha|mambo|lambada|latin|perreo|whine|wining|"
    r"kizomba|sensual)",
    re.I,
)
RE_ADULT_OUTFIT = re.compile(
    r"(bikini|swimsuit|swimwear|club.?wear|club.?outfit|party.?dress|party.?outfit|"
    r"evening.?dress|club.?clothes)",
    re.I,
)
# Main skip list minus swimwear (adult character outfits may mention those words).
RE_SKIP_ADULT = re.compile(
    RE_SKIP.pattern.replace("bikini|swimsuit|swimwear|lingerie|", ""),
    re.I,
)

# Poly Haven: stage / studio / night only, skip abandoned ruins.
HDRI_WANT = re.compile(
    r"(studio|theatre|theater|concert|night|stage|club|neon|music.?hall|"
    r"dancing.?hall|cinema.?hall|photo.?studio|cyclorama)",
    re.I,
)
HDRI_SKIP = re.compile(
    r"(abandoned|rubble|ruin|desolate|dumpster|bathroom|hospital|gore|"
    r"christmas|church|cemetery|grave|waste|trash)",
    re.I,
)

# Existing files we already ship (do not count against the 1 GB cap).
SEED_HDRI = {
    "dikhololo_night_1k.hdr",
    "studio_small_09_1k.hdr",
    "venice_sunset_1k.hdr",
    "LICENSE.txt",
}

MAX_VRMA = 5 * 1024 * 1024
MAX_MOTION = 1 * 1024 * 1024
MAX_HDR = 4 * 1024 * 1024
MAX_JS = 2 * 1024 * 1024
MAX_VRM = 8 * 1024 * 1024  # lean; skip large characters on a phone
MIN_VRMA = 2048
GLB_MAGIC = b"glTF"


def now_ist() -> datetime:
    return datetime.now(IST)


def log(msg: str) -> None:
    line = f"{now_ist().strftime('%Y-%m-%d %H:%M:%S %Z')} {msg}"
    print(line, flush=True)
    try:
        logf = ROOT / "assets/viz/update/viz-update.log"
        logf.parent.mkdir(parents=True, exist_ok=True)
        with logf.open("a", encoding="utf-8") as f:
            f.write(line + "\n")
            # keep the log lean
        if logf.stat().st_size > 400_000:
            txt = logf.read_text(encoding="utf-8", errors="replace").splitlines()
            logf.write_text("\n".join(txt[-800:]) + "\n", encoding="utf-8")
    except OSError:
        pass


def low_priority() -> None:
    try:
        if hasattr(os, "nice"):
            os.nice(19)
    except OSError:
        pass
    if sys.platform == "win32":
        try:
            import ctypes
            k = ctypes.windll.kernel32
            k.SetPriorityClass(k.GetCurrentProcess(), 0x00004000)  # BELOW_NORMAL
        except Exception:
            pass
    else:
        # ionice best-effort (may be missing in Termux)
        try:
            os.system("ionice -c3 -p %d >/dev/null 2>&1" % os.getpid())
        except Exception:
            pass


def default_config() -> dict:
    return {
        "enabled": True,
        "max_bytes_per_run": 50 * 1024 * 1024,
        "max_total_bytes": 1024 * 1024 * 1024,
        "min_days_between_runs": 6,
        "sources": {
            "open-vrma": True,
            "polyhaven-hdri": True,
            "butterchurn-presets": False,  # notrippy-20261111
            "vrm-characters": True,
        },
        "schedule": "Monday 04:00 Asia/Calcutta, via phone crontab + wd.sh and desktop task MusicStream8121_VizUpdate",
    }


def load_config() -> dict:
    path = ROOT / "assets/viz/update/config.json"
    cfg = default_config()
    if path.exists():
        try:
            got = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(got, dict):
                cfg.update({k: got[k] for k in got if k != "sources"})
                if isinstance(got.get("sources"), dict):
                    cfg["sources"].update(got["sources"])
        except Exception as e:
            log(f"config read failed, using defaults: {e}")
    return cfg


def atomic_write(path: Path, data, *, text=False) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    if text or isinstance(data, str):
        tmp.write_text(data if isinstance(data, str) else data.decode("utf-8"), encoding="utf-8")
    else:
        tmp.write_bytes(data)
    os.replace(tmp, path)


def keep_last_good(path: Path) -> None:
    if path.exists():
        shutil.copy2(path, path.with_name(path.name + ".lastgood"))


def url_allowed(url: str, family: str | None = None) -> bool:
    if any(url.startswith(p) for p in ALLOW_URLS):
        return True
    # Poly Haven file CDNs already listed. HF LFS redirects: only for open-vrma fetches.
    if family == "open-vrma":
        try:
            from urllib.parse import urlparse
            host = (urlparse(url).hostname or "").lower()
            path = urlparse(url).path or ""
        except Exception:
            return False
        if host in HF_FILE_HOSTS or host.endswith(".huggingface.co") or host.endswith(".hf.co"):
            # Prefer a path that still names the dataset; some LFS URLs are hashed-only
            # after a hop that started at an allowlisted Sanami/open-vrma resolve URL.
            # family is only set on fetches that started at an allowlisted Sanami/open-vrma URL
            return True
    return False


class Budget:
    def __init__(self, max_bytes: int):
        self.max = int(max_bytes)
        self.used = 0

    def remain(self) -> int:
        return max(0, self.max - self.used)

    def would_exceed(self, n: int) -> bool:
        return self.used + n > self.max and n > 0


def http_open(url: str, budget: Budget, timeout=30, method="GET", family=None):
    if not url_allowed(url, family):
        raise ValueError(f"blocked url (not allowlisted): {url.split('?')[0]}")
    if budget.remain() <= 0:
        raise RuntimeError("per-run byte cap reached")
    req = Request(url, method=method, headers={"User-Agent": UA})
    return urlopen(req, timeout=timeout)


def http_bytes(url: str, budget: Budget, max_size: int, timeout=45, family=None) -> bytes:
    with http_open(url, budget, timeout=timeout, family=family) as r:
        final = r.geturl()
        if not url_allowed(final, family):
            raise ValueError(f"redirect left allowlist: {final.split('?')[0]}")
        cl = r.headers.get("Content-Length")
        if cl and int(cl) > max_size:
            raise ValueError(f"too large ({cl} > {max_size})")
        buf = io.BytesIO()
        while True:
            chunk = r.read(64 * 1024)
            if not chunk:
                break
            if buf.tell() + len(chunk) > max_size:
                raise ValueError("too large while reading")
            if budget.would_exceed(len(chunk)):
                raise RuntimeError("per-run byte cap reached")
            buf.write(chunk)
            budget.used += len(chunk)
        return buf.getvalue()


def lic_ok(s: str) -> bool:
    return (s or "").strip().lower() in ALLOW_LICENSES


def looks_glb(data: bytes) -> bool:
    return len(data) >= 12 and data[:4] == GLB_MAGIC


def looks_hdr(data: bytes) -> bool:
    head = data[:64].lstrip()
    return head.startswith(b"#?RADIANCE") or head.startswith(b"#?RGBE")


def looks_json(data: bytes) -> bool:
    try:
        json.loads(data.decode("utf-8"))
        return True
    except Exception:
        return False


# ---------- open-vrma ----------

def openvrma_base(file_field: str) -> str:
    # catalog "file" looks like cmu/94_02.vrma
    return "https://huggingface.co/datasets/Sanami/open-vrma/resolve/main/" + file_field.lstrip("/")


def fetch_catalog(budget: Budget, cache_dir: Path, dry: bool) -> list[dict]:
    cache = cache_dir / "open-vrma-catalog.csv"
    url = "https://huggingface.co/datasets/Sanami/open-vrma/resolve/main/catalog.csv"
    stale = True
    if cache.exists() and (time.time() - cache.stat().st_mtime) < 20 * 3600:
        stale = False
    if stale and not dry:
        log("fetching open-vrma catalog.csv")
        data = http_bytes(url, budget, max_size=3 * 1024 * 1024, family="open-vrma")
        if not data.startswith(b"id,") and b"license" not in data[:500]:
            raise ValueError("catalog.csv did not look like the open-vrma catalog")
        atomic_write(cache, data)
    elif not cache.exists():
        # dry-run with no cache: still fetch (needed to plan)
        log("fetching open-vrma catalog.csv (dry, no cache yet)")
        data = http_bytes(url, budget, max_size=3 * 1024 * 1024, family="open-vrma")
        # do not write in dry-run? planning needs it. Write to temp only.
        return list(csv.DictReader(io.StringIO(data.decode("utf-8", "replace"))))
    rows = list(csv.DictReader(cache.open(encoding="utf-8", errors="replace")))
    log(f"open-vrma catalog rows={len(rows)}")
    return rows


def _clip_blob(row: dict) -> str:
    return " ".join(
        [
            row.get("id") or "",
            row.get("name") or "",
            row.get("description") or "",
            row.get("keywords") or "",
            row.get("genre") or "",
        ]
    )


def is_dance_clip(row: dict, tier: str = "main") -> tuple[bool, str]:
    lic = (row.get("license") or "").strip()
    if not lic_ok(lic):
        return False, "license"
    if (row.get("kind") or "").strip().lower() != "dance":
        return False, "not-dance"
    try:
        dur = float(row.get("duration") or 0)
    except ValueError:
        return False, "duration"
    if dur < 1.5 or dur > 90:
        return False, "duration"
    blob = _clip_blob(row)
    if RE_FRANCHISE.search(blob) or RE_NUDE.search(blob) or RE_YOUTH.search(blob):
        return False, "franchise-nude-or-youth"
    if tier == "adult":
        # Same adult/franchise/licence checks; allow sensual Latin / club-style moves.
        # Still never nudity. Swimwear words in a motion description are ignored here
        # (they apply to characters, not CMU mocap).
        if RE_SKIP_ADULT.search(blob):
            return False, "skip"
        if not RE_ADULT_MOVES.search(blob):
            return False, "not-adult-move"
        return True, "ok"
    if RE_SWIM.search(blob):
        return False, "franchise-or-swimwear"
    if RE_SKIP.search(blob):
        return False, "skip"
    return True, "ok"


def mood_for(genre: str, energy: int, tier: str = "main") -> list[str]:
    g = (genre or "").lower()
    if "indian" in g:
        return ["romantic", "devotional"]
    if "salsa" in g or "lambada" in g:
        return ["party", "upbeat"] if tier != "adult" else ["party", "romantic"]
    if "charleston" in g or "lindy" in g or "swing" in g:
        return ["upbeat", "swing"]
    if "break" in g:
        return ["energetic"]
    if "chicken" in g:
        return ["playful"]
    if "folk" in g or "russian" in g:
        return ["folk"]
    if energy >= 4:
        return ["upbeat"]
    if energy <= 2:
        return ["lyrical"]
    return ["casual"]


def label_for(row: dict) -> str:
    desc = (row.get("description") or "").strip()
    genre = (row.get("genre") or "").strip()
    if desc and desc.lower() not in {"unknown", "sequesnce", "sequence"}:
        return desc[:48]
    if genre:
        return f"{genre} dance ({row.get('name') or row.get('id')})"
    return f"Dance {row.get('name') or row.get('id')}"


def clip_entry(row: dict, motion: dict | None, filename: str, tier: str = "main") -> dict:
    tempo = (motion or {}).get("tempo") or {}
    try:
        bpm = float(tempo.get("bpm") or row.get("bpm") or 100)
    except (TypeError, ValueError):
        bpm = 100
    alts = tempo.get("alternatives") or []
    if isinstance(alts, str):
        alts = [float(x) for x in alts.replace(";", ",").split(",") if x.strip()]
    try:
        energy = int(row.get("energy") or 3)
    except ValueError:
        energy = 3
    try:
        dur = float((motion or {}).get("duration") or row.get("duration") or 0)
    except ValueError:
        dur = 0
    first = tempo.get("firstBeat")
    conf = tempo.get("confidence")
    basis = tempo.get("basis") or "motion"
    tmin = max(30, bpm * 0.375) if bpm else 60
    tmax = min(280, bpm * 2.66) if bpm else 200
    src = row.get("id") or ""
    # cmu_94_02 -> 94_02
    m = re.match(r"cmu_(.+)", src)
    original = m.group(1).replace("_", "_", 1)
    if m:
        parts = src.split("_", 1)[1] if "_" in src else src
        original = parts.replace("_", "_")
        # 94_02 style: cmu_94_02 -> 94_02
        original = re.sub(r"^cmu_", "", src)
        original = original[4:] if original.startswith("cmu_") else original
        # cmu_94_02 -> 94_02
        original = src[4:] if src.startswith("cmu_") else (row.get("name") or src)
    return {
        "id": row["id"],
        "file": filename,
        "label": label_for(row),
        "energy": energy,
        "duration": dur,
        "bpm": bpm,
        "alts": alts,
        "firstBeat": first if first is not None else 0,
        "tempoNote": f"open-vrma tempo ({basis}, confidence {conf})" if basis else "open-vrma",
        "tempoMin": round(tmin, 1),
        "tempoMax": round(tmax, 1),
        "loop": str(row.get("loopable") or "").lower() in {"true", "1", "yes"},
        "license": (row.get("license") or "").strip(),
        "source": original,
        "desc": (row.get("description") or "").strip(),
        "genre": (row.get("genre") or "").strip(),
        "moods": mood_for(row.get("genre") or "", energy, tier=tier),
        "locomotion": (row.get("locomotion") or "").strip(),
    }


# ---------- Poly Haven ----------

def polyhaven_list(budget: Budget) -> list[dict]:
    url = "https://api.polyhaven.com/assets?t=hdris"
    data = json.loads(http_bytes(url, budget, max_size=2 * 1024 * 1024).decode("utf-8"))
    out = []
    for name, meta in data.items():
        if not isinstance(meta, dict):
            continue
        blob = " ".join(meta.get("tags") or []) + " " + " ".join(meta.get("categories") or []) + " " + name
        if not HDRI_WANT.search(blob) or HDRI_SKIP.search(blob):
            continue
        # "amphitheatre" contains "theatre" but is an outdoor landmark; keep only strong matches first
        if re.search(r"amphitheatre|amphitheater", name, re.I) and not re.search(r"night|studio|stage", blob, re.I):
            continue
        out.append({"id": name, "meta": meta, "blob": blob})
    def _rank(x):
        n = x["id"]
        if re.search(r"dancing_hall|cinema_hall|music_hall", n, re.I): return 0
        if re.search(r"photo_studio|photostudio|cyclorama|colorful_studio", n, re.I): return 1
        if re.search(r"night", n, re.I): return 2
        return 3
    out.sort(key=lambda x: (_rank(x), x["id"]))
    return out


def polyhaven_hdr_url(asset_id: str, budget: Budget) -> str | None:
    url = f"https://api.polyhaven.com/files/{asset_id}"
    data = json.loads(http_bytes(url, budget, max_size=1 * 1024 * 1024).decode("utf-8"))
    hdri = (data.get("hdri") or {})
    k = hdri.get("1k") or hdri.get("2k") or {}
    hdr = (k.get("hdr") or {})
    u = hdr.get("url")
    if u and url_allowed(u):
        return u
    return None


# ---------- Butterchurn ----------

def butterchurn_version(budget: Budget) -> str | None:
    url = "https://registry.npmjs.org/butterchurn-presets/latest"
    try:
        data = json.loads(http_bytes(url, budget, max_size=200_000).decode("utf-8"))
        return str(data.get("version") or "")
    except Exception as e:
        log(f"butterchurn version check failed: {e}")
        return None


# ---------- VRM characters (conservative empty allowlist) ----------
# No remote VRM feed is auto-trusted: VRoid Hub licences vary, official CC0
# samples are already shipped, and swimwear/franchise models must never be
# pulled. This hook exists so a future, hand-vetted CC0/CC-BY adult original
# may be added to assets/viz/update/vrm-allowlist.json (url + license + name).

def vrm_allowlist(tier: str = "main") -> list[dict]:
    name = "vrm-allowlist.json" if tier != "adult" else "vrm-allowlist-adult.json"
    path = ROOT / "assets/viz/update" / name
    if not path.exists():
        return []
    try:
        rows = json.loads(path.read_text(encoding="utf-8"))
        return rows if isinstance(rows, list) else []
    except Exception:
        return []


def vrm_item_ok(item: dict, tier: str = "main") -> tuple[bool, str]:
    """Licence + adult + franchise checks. Adult tier may allow swimwear/club outfits; never nudity."""
    url = (item or {}).get("url") or ""
    lic = (item or {}).get("license") or ""
    name = (item or {}).get("name") or ""
    fname = (item or {}).get("file") or ""
    notes = (item or {}).get("notes") or ""
    blob = " ".join([name, fname, notes, url])
    if not lic_ok(lic):
        return False, "license"
    if RE_FRANCHISE.search(blob) or RE_NUDE.search(blob) or RE_YOUTH.search(blob):
        return False, "franchise-nude-or-youth"
    if "lingerie" in blob.lower() or "fetish" in blob.lower():
        return False, "fetish"
    if tier == "adult":
        # allow swimwear / club / party outfits (explicitly in notes or name)
        return True, "ok"
    if RE_SWIM.search(blob):
        return False, "swimwear"
    return True, "ok"


def link_or_copy(src: Path, dest: Path) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.exists():
        return
    try:
        os.link(src, dest)
    except Exception:
        shutil.copy2(src, dest)


# ---------- credits / rev / catalog ----------

def append_credits(lines: list[str], dry: bool) -> None:
    if not lines:
        return
    stamp = now_ist().strftime("%Y-%m-%d %H:%M %Z")
    block = "\n## Auto-update {0}\n\n{1}\n".format(stamp, "\n".join(lines))
    for rel in ("docs/VIZ_ADV_CREDITS.md", "assets/viz/CREDITS.md"):
        path = ROOT / rel
        if dry:
            continue
        path.parent.mkdir(parents=True, exist_ok=True)
        prev = path.read_text(encoding="utf-8") if path.exists() else "# Music Stream visuals — credits\n"
        if block.strip() in prev:
            continue
        keep_last_good(path)
        atomic_write(path, prev.rstrip() + "\n" + block, text=True)


def write_rev(rev: str, meta: dict, dry: bool) -> None:
    js = (
        "/* auto-generated by scripts/viz-update.py; safe to overwrite */\n"
        "window.__MS_VIZ_REV = %s;\n"
        "window.__MS_VIZ_REV_META = %s;\n"
        % (json.dumps(rev), json.dumps(meta, separators=(",", ":")))
    )
    path = ROOT / "assets/viz/rev.js"
    if dry:
        log(f"dry: would write {path} rev={rev}")
        return
    keep_last_good(path)
    atomic_write(path, js, text=True)


def write_hdri_index(entries: dict, dry: bool) -> None:
    path = ROOT / "assets/viz/hdri/index.json"
    if dry:
        return
    keep_last_good(path)
    atomic_write(path, json.dumps(entries, indent=2) + "\n", text=True)


def load_state() -> dict:
    path = ROOT / "assets/viz/update/state.json"
    if path.exists():
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            return {}
    return {}


def save_state(state: dict, dry: bool) -> None:
    if dry:
        return
    path = ROOT / "assets/viz/update/state.json"
    atomic_write(path, json.dumps(state, indent=2) + "\n", text=True)


def owned_bytes(state: dict) -> int:
    total = 0
    for rel in state.get("owned") or []:
        p = ROOT / rel
        if p.is_file():
            total += p.stat().st_size
    return total


class Lock:
    def __init__(self, path: Path):
        self.path = path
        self.fp = None

    def acquire(self) -> bool:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if self.path.exists():
            try:
                age = time.time() - self.path.stat().st_mtime
                if age > 2 * 3600:
                    self.path.unlink()
                else:
                    return False
            except OSError:
                return False
        self.fp = open(self.path, "w", encoding="utf-8")
        try:
            if sys.platform == "win32":
                import msvcrt
                msvcrt.locking(self.fp.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(self.fp.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            self.fp.close()
            self.fp = None
            return False
        self.fp.write(str(os.getpid()))
        self.fp.flush()
        return True

    def release(self) -> None:
        if not self.fp:
            return
        try:
            if sys.platform == "win32":
                import msvcrt
                self.fp.seek(0)
                msvcrt.locking(self.fp.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                import fcntl
                fcntl.flock(self.fp.fileno(), fcntl.LOCK_UN)
        except OSError:
            pass
        try:
            self.fp.close()
        except OSError:
            pass
        try:
            self.path.unlink()
        except OSError:
            pass


def set_enabled(on: bool) -> None:
    flag = ROOT / "assets/viz/update/disabled"
    cfg_path = ROOT / "assets/viz/update/config.json"
    cfg = load_config()
    cfg["enabled"] = bool(on)
    atomic_write(cfg_path, json.dumps(cfg, indent=2) + "\n", text=True)
    if on:
        if flag.exists():
            flag.unlink()
        log("automatic updates ENABLED")
    else:
        flag.write_text("disabled " + now_ist().isoformat() + "\n", encoding="utf-8")
        log("automatic updates DISABLED (delete assets/viz/update/disabled or run --on)")


# ---------- main run ----------


def run_adult_tier(rows, budget, cfg, args, state, added, skipped, owned, dry, limit) -> None:
    """18+ pack: sensual Latin / club-style moves + optional hand-vetted adult characters.
    Writes only under assets/dance/adult/ and assets/chars/vrm/adult/. Never touches main clips.json.
    """
    dance_dir = ROOT / "assets/dance/adult"
    dance_dir.mkdir(parents=True, exist_ok=True)
    clips_path = dance_dir / "clips.json"
    if clips_path.exists():
        try:
            catalog = json.loads(clips_path.read_text(encoding="utf-8"))
        except Exception:
            catalog = {"version": "adult", "tier": "adult", "clips": [], "characters": []}
    else:
        catalog = {
            "version": "adult",
            "tier": "adult",
            "clips": [],
            "characters": [],
            "note": "Loaded only when the signed-in user has 18+ visuals enabled by an admin.",
            "source": "open-vrma / CMU mocap; never mixed into the main catalog",
        }
    catalog.setdefault("clips", [])
    catalog.setdefault("characters", [])
    catalog["tier"] = "adult"
    have = {c.get("id") for c in catalog.get("clips") or []}
    have_files = {c.get("file") for c in catalog.get("clips") or []}
    main_dir = ROOT / "assets/dance"
    candidates = []
    why = {}
    for row in rows or []:
        if row.get("id") in have or (row.get("id") + ".vrma") in have_files:
            why["already"] = why.get("already", 0) + 1
            continue
        ok, reason = is_dance_clip(row, tier="adult")
        why[reason] = why.get(reason, 0) + 1
        if ok:
            candidates.append(row)
    log(f"adult open-vrma filter {why}; new adult-move candidates {len(candidates)}")
    # Prefer already-on-disk main files (no network), then shorter labelled clips.
    def already(r):
        return 0 if (main_dir / (r["id"] + ".vrma")).is_file() else 1
    candidates.sort(key=lambda r: (already(r), 0 if (r.get("genre") or r.get("description") or "").strip() else 1, float(r.get("duration") or 99)))
    n_added = 0
    adult_added = 0
    for row in candidates:
        if limit and n_added >= limit:
            break
        if budget.remain() < MIN_VRMA and already(row) != 0:
            log("per-run cap: stopping adult clip downloads")
            break
        if owned_bytes({"owned": owned}) >= int(cfg["max_total_bytes"]):
            log("disk cap: stopping adult clips")
            break
        dest_name = row["id"] + ".vrma"
        mot_name = row["id"] + ".motion.json"
        try:
            motion = None
            motion_bytes = b""
            vrma_len = 0
            src_vrma = main_dir / dest_name
            src_mot = main_dir / mot_name
            if src_vrma.is_file() and looks_glb(src_vrma.read_bytes()):
                if dry:
                    log(f"dry adult: would link {dest_name} from main library  license={row.get('license')}")
                    added.append({"id": row["id"], "license": row.get("license"), "kind": "adult-clip", "dry": True})
                    n_added += 1
                    adult_added += 1
                    continue
                link_or_copy(src_vrma, dance_dir / dest_name)
                vrma_len = src_vrma.stat().st_size
                owned.append(f"assets/dance/adult/{dest_name}")
                if src_mot.is_file():
                    try:
                        motion_bytes = src_mot.read_bytes()
                        if looks_json(motion_bytes):
                            motion = json.loads(motion_bytes.decode("utf-8"))
                            link_or_copy(src_mot, dance_dir / mot_name)
                            owned.append(f"assets/dance/adult/{mot_name}")
                    except Exception:
                        motion = None
            else:
                file_field = row.get("file") or ""
                if not file_field.endswith(".vrma"):
                    skipped.append((row["id"], "no-vrma-file"))
                    continue
                if dry:
                    log(f"dry adult: would fetch {dest_name}  license={row.get('license')}  {row.get('description')}")
                    added.append({"id": row["id"], "license": row.get("license"), "kind": "adult-clip", "dry": True})
                    n_added += 1
                    adult_added += 1
                    continue
                vrma_url = openvrma_base(file_field)
                motion_url = openvrma_base(re.sub(r"\.vrma$", ".motion.json", file_field))
                vrma = http_bytes(vrma_url, budget, MAX_VRMA, family="open-vrma")
                if not looks_glb(vrma) or not (MIN_VRMA <= len(vrma) <= MAX_VRMA):
                    skipped.append((row["id"], "vrma-invalid"))
                    continue
                vrma_len = len(vrma)
                try:
                    motion_bytes = http_bytes(motion_url, budget, MAX_MOTION, family="open-vrma")
                    if looks_json(motion_bytes):
                        motion = json.loads(motion_bytes.decode("utf-8"))
                        lic = ((motion.get("license") or {}) or {})
                        spdx = lic.get("spdx") if isinstance(lic, dict) else None
                        if spdx and not lic_ok(spdx):
                            skipped.append((row["id"], f"motion-license:{spdx}"))
                            continue
                except Exception as e:
                    log(f"adult motion.json optional fail for {row['id']}: {e}")
                    motion_bytes = b""
                    motion = None
                with tempfile.TemporaryDirectory(prefix="vizup-adult-", dir=str(ROOT / "assets/viz/update")) as td:
                    tdir = Path(td)
                    (tdir / dest_name).write_bytes(vrma)
                    if motion_bytes and motion is not None:
                        (tdir / mot_name).write_bytes(motion_bytes)
                    if not looks_glb((tdir / dest_name).read_bytes()):
                        skipped.append((row["id"], "revalidate-fail"))
                        continue
                    shutil.copy2(tdir / dest_name, dance_dir / dest_name)
                    owned.append(f"assets/dance/adult/{dest_name}")
                    if (tdir / mot_name).exists():
                        shutil.copy2(tdir / mot_name, dance_dir / mot_name)
                        owned.append(f"assets/dance/adult/{mot_name}")
            entry = clip_entry(row, motion, dest_name, tier="adult")
            entry["adult"] = True
            catalog["clips"].append(entry)
            have.add(row["id"])
            added.append({
                "id": row["id"],
                "license": row.get("license"),
                "kind": "adult-clip",
                "bytes": vrma_len + len(motion_bytes or b""),
                "label": entry["label"],
            })
            n_added += 1
            adult_added += 1
            if already(row) != 0:
                time.sleep(0.35)
        except RuntimeError as e:
            log(str(e))
            break
        except Exception as e:
            skipped.append((row["id"], f"error:{type(e).__name__}"))
            log(f"adult clip {row['id']} failed: {e}")

    # Adult characters: hand-vetted allowlist only. Empty is honest.
    dest_dir = ROOT / "assets/chars/vrm/adult"
    dest_dir.mkdir(parents=True, exist_ok=True)
    index_path = dest_dir / "index.json"
    index = {"models": [], "tier": "adult", "note": "Loaded only when 18+ visuals is on. Never nudity."}
    if index_path.exists():
        try:
            got = json.loads(index_path.read_text(encoding="utf-8"))
            if isinstance(got, dict):
                index.update(got)
        except Exception:
            pass
    have_v = {m.get("file") for m in index.get("models") or []}
    allow = vrm_allowlist("adult")
    if not allow:
        log("adult VRM: no hand-vetted allowlist entries (no compliant freely licensed swimwear/club character found)")
    else:
        for item in allow:
            url = (item or {}).get("url") or ""
            lic = (item or {}).get("license") or ""
            name = (item or {}).get("name") or ""
            fname = (item or {}).get("file") or (re.sub(r"[^A-Za-z0-9_.-]+", "_", name) + ".vrm")
            ok, reason = vrm_item_ok(item, tier="adult")
            if not ok or not url_allowed(url):
                skipped.append((name or url, "adult-vrm-rejected:" + reason))
                continue
            if fname in have_v:
                continue
            if dry:
                added.append({"id": name, "license": lic, "kind": "adult-vrm", "dry": True})
                continue
            try:
                data = http_bytes(url, budget, MAX_VRM)
                if not looks_glb(data):
                    skipped.append((name, "vrm-invalid"))
                    continue
                atomic_write(dest_dir / fname, data)
                rec = {"name": name, "file": fname, "url": f"/assets/chars/vrm/adult/{fname}", "license": lic, "adult": True}
                index.setdefault("models", []).append(rec)
                catalog.setdefault("characters", []).append(rec)
                owned.append(f"assets/chars/vrm/adult/{fname}")
                added.append({"id": name, "license": lic, "kind": "adult-vrm", "bytes": len(data)})
            except Exception as e:
                skipped.append((name, f"vrm-error:{type(e).__name__}"))
    if not dry:
        keep_last_good(index_path)
        atomic_write(index_path, json.dumps(index, indent=2) + "\n", text=True)
        if adult_added or allow:
            catalog["version"] = "adult-" + now_ist().strftime("%Y%m%d%H%M")
            keep_last_good(clips_path)
            atomic_write(clips_path, json.dumps(catalog, indent=2) + "\n", text=True)
            log(f"adult clips.json now {len(catalog['clips'])} clips, {len(index.get('models') or [])} characters (last-good kept)")
        elif not clips_path.exists():
            atomic_write(clips_path, json.dumps(catalog, indent=2) + "\n", text=True)


def run(args) -> int:
    low_priority()
    cfg = load_config()
    disabled = (ROOT / "assets/viz/update/disabled").exists() or not cfg.get("enabled", True)
    if args.off:
        set_enabled(False)
        return 0
    if args.on:
        set_enabled(True)
        return 0
    if disabled and not args.force:
        log("disabled; use --on or --force to run")
        return 0

    max_bytes = int(args.max_bytes or cfg["max_bytes_per_run"])
    limit = int(args.limit or 0)
    dry = bool(args.dry_run)
    tier = (getattr(args, "tier", None) or "all").strip().lower()
    if tier not in ("all", "main", "adult"):
        log(f"unknown --tier {tier}; use all|main|adult")
        return 2
    budget = Budget(max_bytes)
    state = load_state()

    last = state.get("last_ok")
    if last and not (args.once or args.force or dry):
        try:
            prev = datetime.fromisoformat(last)
            if prev.tzinfo is None:
                prev = prev.replace(tzinfo=IST)
            days = (now_ist() - prev).total_seconds() / 86400
            if days < float(cfg.get("min_days_between_runs") or 6):
                log(f"already ran {days:.1f} days ago; skipping (use --once to run now)")
                return 0
        except Exception:
            pass

    if owned_bytes(state) >= int(cfg["max_total_bytes"]):
        log(f"disk cap reached ({owned_bytes(state)} bytes of updater-managed files); nothing added")
        return 0

    lock = Lock(ROOT / "assets/viz/update/viz-update.lock")
    if not dry and not lock.acquire():
        log("another viz-update is running; exit")
        return 0
    added, skipped = [], []
    owned = list(state.get("owned") or [])
    try:
        cache_dir = ROOT / "assets/viz/update/cache"
        cache_dir.mkdir(parents=True, exist_ok=True)
        dance_dir = ROOT / "assets/dance"
        hdri_dir = ROOT / "assets/viz/hdri"
        clips_path = dance_dir / "clips.json"
        catalog = json.loads(clips_path.read_text(encoding="utf-8"))
        have = {c["id"] for c in catalog.get("clips") or []}
        have_files = {c.get("file") for c in catalog.get("clips") or []}

        # ----- clips -----
        rows = []
        if cfg["sources"].get("open-vrma", True):
            try:
                rows = fetch_catalog(budget, cache_dir, dry)
            except Exception as e:
                log(f"open-vrma catalog failed: {e}")
                rows = []
        if cfg["sources"].get("open-vrma", True) and tier in ("all", "main"):
            candidates = []
            why = {}
            for row in rows:
                if row.get("id") in have or (row.get("id") + ".vrma") in have_files:
                    why["already"] = why.get("already", 0) + 1
                    continue
                ok, reason = is_dance_clip(row)
                why[reason] = why.get(reason, 0) + 1
                if ok:
                    candidates.append(row)
            log(f"open-vrma filter {why}; new dance candidates {len(candidates)}")
            random.Random(now_ist().strftime("%Y%W")).shuffle(candidates)  # stable weekly shuffle, mixed not repeating
            # prefer shorter, clearly labelled dance first
            candidates.sort(key=lambda r: (0 if (r.get("genre") or r.get("description") or "").strip() else 1, float(r.get("duration") or 99)))
            n_added = 0
            for row in candidates:
                if limit and n_added >= limit:
                    break
                if budget.remain() < MIN_VRMA:
                    log("per-run cap: stopping clip downloads")
                    break
                if owned_bytes({"owned": owned}) >= int(cfg["max_total_bytes"]):
                    log("disk cap: stopping")
                    break
                file_field = row.get("file") or ""
                if not file_field.endswith(".vrma"):
                    skipped.append((row["id"], "no-vrma-file"))
                    continue
                vrma_url = openvrma_base(file_field)
                motion_url = openvrma_base(re.sub(r"\.vrma$", ".motion.json", file_field))
                dest_name = row["id"] + ".vrma"
                try:
                    if dry:
                        log(f"dry: would fetch {dest_name}  license={row.get('license')}  {row.get('description')}")
                        added.append({"id": row["id"], "license": row.get("license"), "kind": "clip", "dry": True})
                        n_added += 1
                        continue
                    vrma = http_bytes(vrma_url, budget, MAX_VRMA, family="open-vrma")
                    if not looks_glb(vrma) or not (MIN_VRMA <= len(vrma) <= MAX_VRMA):
                        skipped.append((row["id"], "vrma-invalid"))
                        continue
                    motion_bytes = b""
                    motion = None
                    try:
                        motion_bytes = http_bytes(motion_url, budget, MAX_MOTION, family="open-vrma")
                        if looks_json(motion_bytes):
                            motion = json.loads(motion_bytes.decode("utf-8"))
                            lic = ((motion.get("license") or {}) or {})
                            spdx = lic.get("spdx") if isinstance(lic, dict) else None
                            if spdx and not lic_ok(spdx):
                                skipped.append((row["id"], f"motion-license:{spdx}"))
                                continue
                    except Exception as e:
                        log(f"motion.json optional fail for {row['id']}: {e}")
                    # write to temp then promote
                    with tempfile.TemporaryDirectory(prefix="vizup-", dir=str(ROOT / "assets/viz/update")) as td:
                        tdir = Path(td)
                        (tdir / dest_name).write_bytes(vrma)
                        mot_name = row["id"] + ".motion.json"
                        if motion_bytes and motion is not None:
                            (tdir / mot_name).write_bytes(motion_bytes)
                        # re-read validate
                        if not looks_glb((tdir / dest_name).read_bytes()):
                            skipped.append((row["id"], "revalidate-fail"))
                            continue
                        shutil.copy2(tdir / dest_name, dance_dir / dest_name)
                        owned.append(f"assets/dance/{dest_name}")
                        if (tdir / mot_name).exists():
                            shutil.copy2(tdir / mot_name, dance_dir / mot_name)
                            owned.append(f"assets/dance/{mot_name}")
                    entry = clip_entry(row, motion, dest_name)
                    catalog["clips"].append(entry)
                    have.add(row["id"])
                    added.append({
                        "id": row["id"],
                        "license": row.get("license"),
                        "kind": "clip",
                        "bytes": len(vrma) + len(motion_bytes),
                        "label": entry["label"],
                    })
                    n_added += 1
                    time.sleep(0.35)
                except RuntimeError as e:
                    log(str(e))
                    break
                except Exception as e:
                    skipped.append((row["id"], f"error:{type(e).__name__}"))
                    log(f"clip {row['id']} failed: {e}")

            if added and not dry:
                catalog["version"] = "vizupd-" + now_ist().strftime("%Y%m%d%H%M")
                sel = catalog.get("selection") or ""
                extra = f" Auto-update {now_ist().strftime('%Y-%m-%d')}: added {sum(1 for a in added if a['kind']=='clip')} dance clips from open-vrma (same licence rules)."
                if extra.strip() not in sel:
                    catalog["selection"] = (sel + extra).strip()
                keep_last_good(clips_path)
                atomic_write(clips_path, json.dumps(catalog, indent=2) + "\n", text=True)
                log(f"clips.json now {len(catalog['clips'])} clips (last-good kept)")

        # ----- adult 18+ pack (separate catalog; never mixed into main clips.json) -----
        if cfg["sources"].get("open-vrma", True) and cfg["sources"].get("adult-open-vrma", True) and tier in ("all", "adult"):
            try:
                run_adult_tier(rows, budget, cfg, args, state, added, skipped, owned, dry, limit)
            except Exception as e:
                log(f"adult tier failed: {e}")

        # ----- HDRIs -----
        hdri_index = {
            "club": "/assets/viz/hdri/dikhololo_night_1k.hdr",
            "cine": "/assets/viz/hdri/studio_small_09_1k.hdr",
            "warm": "/assets/viz/hdri/venice_sunset_1k.hdr",
            "extra": [],
        }
        idx_path = hdri_dir / "index.json"
        if idx_path.exists():
            try:
                hdri_index.update(json.loads(idx_path.read_text(encoding="utf-8")))
            except Exception:
                pass
        if tier in ("all", "main") and cfg["sources"].get("polyhaven-hdri", True) and budget.remain() > 200_000 and (not limit or sum(1 for a in added if a["kind"] == "hdri") < 1):
            try:
                assets = polyhaven_list(budget)
                have_hdri = {p.name for p in hdri_dir.glob("*.hdr")}
                # at most one HDRI per run (they're ~1.5 MB)
                for item in assets:
                    name = item["id"]
                    fname = f"{name}_1k.hdr"
                    if fname in have_hdri or name in {x.replace("_1k.hdr", "") for x in SEED_HDRI}:
                        continue
                    if limit and sum(1 for a in added if a.get("kind") in {"clip", "hdri", "preset"}) >= limit:
                        break
                    try:
                        url = polyhaven_hdr_url(name, budget)
                        if not url:
                            continue
                        if dry:
                            log(f"dry: would fetch HDRI {fname} (Poly Haven CC0)")
                            added.append({"id": name, "license": "CC0-1.0", "kind": "hdri", "dry": True})
                            break
                        data = http_bytes(url, budget, MAX_HDR)
                        if not looks_hdr(data):
                            skipped.append((name, "hdr-invalid"))
                            continue
                        dest = hdri_dir / fname
                        atomic_write(dest, data)
                        owned.append(f"assets/viz/hdri/{fname}")
                        extras = hdri_index.setdefault("extra", [])
                        rec = {"id": name, "file": f"/assets/viz/hdri/{fname}", "license": "CC0-1.0", "source": "https://polyhaven.com/a/" + name}
                        if rec not in extras and not any(x.get("id") == name for x in extras):
                            extras.append(rec)
                        added.append({"id": name, "license": "CC0-1.0", "kind": "hdri", "bytes": len(data)})
                        # prefer a dancing/cinema hall as an alternate cine backdrop
                        if re.search(r"dancing.?hall|cinema.?hall|theatre", name, re.I) and "alt_cine" not in hdri_index:
                            hdri_index["alt_cine"] = f"/assets/viz/hdri/{fname}"
                        log(f"added HDRI {fname} ({len(data)} bytes, CC0)")
                        break
                    except RuntimeError as e:
                        log(str(e))
                        break
                    except Exception as e:
                        skipped.append((name, f"hdri-error:{type(e).__name__}"))
                        log(f"HDRI {name} failed: {e}")
            except Exception as e:
                log(f"polyhaven list failed: {e}")
        if not dry:
            write_hdri_index(hdri_index, dry)

        # ----- presets (version check; only bump extra file if npm is newer) -----
        if tier in ("all", "main") and False and cfg["sources"].get("butterchurn-presets", False) and budget.remain() > 50_000:  # notrippy-20261111: Trippy removed
            ver = butterchurn_version(budget)
            pinned = state.get("butterchurn_presets_version") or "2.6.7"
            if ver and ver != pinned:
                log(f"butterchurn-presets npm {ver} (pinned {pinned}); extra presets hook is ready, vendor bundle left in place")
                # We do not replace vendor/butterchurn/*.js automatically (SW cache-first,
                # large bundle). The presets-extra.js hook will pick up curated additions
                # if a later allowlisted incremental file is added by hand or a future run.
                state["butterchurn_presets_version_seen"] = ver
            else:
                log(f"butterchurn-presets up to date ({pinned if not ver else ver})")

        # ----- VRM (allowlist only; default empty) -----
        if tier in ("all", "main") and cfg["sources"].get("vrm-characters", True):
            allow = vrm_allowlist()
            if not allow:
                log("VRM characters: no hand-vetted allowlist entries; skipped (no VRoid Hub scrape, no swimwear/franchise)")
            else:
                # conservative download of explicitly listed CC0/CC-BY adult originals
                dest_dir = ROOT / "assets/chars/vrm"
                index_path = dest_dir / "index.json"
                index = {"models": []}
                if index_path.exists():
                    try:
                        index = json.loads(index_path.read_text(encoding="utf-8"))
                    except Exception:
                        pass
                have_v = {m.get("file") for m in index.get("models") or []}
                for item in allow:
                    url = (item or {}).get("url") or ""
                    lic = (item or {}).get("license") or ""
                    name = (item or {}).get("name") or ""
                    fname = (item or {}).get("file") or (re.sub(r"[^A-Za-z0-9_.-]+", "_", name) + ".vrm")
                    blob = " ".join([name, fname, (item or {}).get("notes") or ""])
                    ok, reason = vrm_item_ok(item, tier="main")
                    if not url_allowed(url) or not ok:
                        skipped.append((name or url, "vrm-rejected:" + reason))
                        continue
                    if fname in have_v:
                        continue
                    if dry:
                        added.append({"id": name, "license": lic, "kind": "vrm", "dry": True})
                        continue
                    try:
                        data = http_bytes(url, budget, MAX_VRM)
                        if not looks_glb(data):
                            skipped.append((name, "vrm-invalid"))
                            continue
                        atomic_write(dest_dir / fname, data)
                        rec = {"name": name, "file": fname, "url": f"/assets/chars/vrm/{fname}", "license": lic, "adult": True}
                        index.setdefault("models", []).append(rec)
                        owned.append(f"assets/chars/vrm/{fname}")
                        added.append({"id": name, "license": lic, "kind": "vrm", "bytes": len(data)})
                    except Exception as e:
                        skipped.append((name, f"vrm-error:{type(e).__name__}"))
                if not dry:
                    keep_last_good(index_path)
                    atomic_write(index_path, json.dumps(index, indent=2) + "\n", text=True)

        # ----- credits + rev -----
        credit_lines = []
        clips_added = [a for a in added if a["kind"] == "clip"]
        if clips_added:
            bits = ", ".join(
                f"{a['id']} ({a.get('label') or 'dance'}, {a.get('license')})"
                for a in clips_added
            )
            credit_lines.append(
                f"- Added {len(clips_added)} dance clip(s) from [open-vrma](https://huggingface.co/datasets/Sanami/open-vrma) "
                f"(conversion CC0-1.0; underlying motion licence per item): {bits}."
            )
        adult_clips = [a for a in added if a["kind"] == "adult-clip"]
        if adult_clips:
            bits = ", ".join(
                f"{a['id']} ({a.get('label') or 'dance'}, {a.get('license')})"
                for a in adult_clips
            )
            credit_lines.append(
                f"- Added {len(adult_clips)} 18+ dance clip(s) to assets/dance/adult/ from [open-vrma](https://huggingface.co/datasets/Sanami/open-vrma) "
                f"(conversion CC0-1.0; underlying motion licence per item; loaded only when 18+ visuals is on): {bits}."
            )
        for a in added:
            if a["kind"] == "hdri":
                credit_lines.append(
                    f"- Added Poly Haven HDRI `{a['id']}` (CC0 1.0, https://polyhaven.com/a/{a['id']})."
                )
            if a["kind"] == "vrm":
                credit_lines.append(f"- Added VRM character `{a['id']}` ({a.get('license')}).")
            if a["kind"] == "adult-vrm":
                credit_lines.append(
                    f"- Added 18+ VRM character `{a['id']}` ({a.get('license')}) to assets/chars/vrm/adult/ (loaded only when 18+ visuals is on)."
                )
        skip_n = len(skipped)
        if skip_n:
            reasons = {}
            for _, r in skipped:
                reasons[r] = reasons.get(r, 0) + 1
            credit_lines.append(f"- Skipped {skip_n} candidate(s) this run: {reasons}.")
        if credit_lines:
            append_credits(credit_lines, dry)

        rev = "vizupd-" + now_ist().strftime("%Y%m%d%H%M")
        meta = {
            "at": now_ist().isoformat(),
            "clips": len(catalog.get("clips") or []),
            "tier": tier,
            "added": [a["id"] for a in added],
            "dry": dry,
        }
        write_rev(rev, meta, dry)

        # ensure stub files exist
        extra = ROOT / "assets/viz/presets-extra.js"
        if not extra.exists() and not dry:
            atomic_write(
                extra,
                "/* extra MilkDrop presets (MIT); filled by viz-update when new allowlisted presets appear */\n"
                "window.MS_BC_PRESETS_EXTRA = window.MS_BC_PRESETS_EXTRA || {};\n",
                text=True,
            )

        state["last_run"] = now_ist().isoformat()
        if not dry:
            state["last_ok"] = now_ist().isoformat()
            state["owned"] = sorted(set(owned))
            state["last_added"] = added
            state["last_rev"] = rev
        save_state(state, dry)
        log(
            f"done dry={dry} added={len(added)} skipped={len(skipped)} "
            f"network_bytes={budget.used} owned_bytes={owned_bytes(state if not dry else {'owned': owned})} rev={rev}"
        )
        for a in added:
            log(f"  + {a['kind']} {a['id']} {a.get('license')} {a.get('bytes', '')}")
        return 0
    finally:
        if not dry:
            lock.release()


def main():
    ap = argparse.ArgumentParser(description="Music Stream visuals auto-updater")
    ap.add_argument("--once", action="store_true", help="run now even if last run was this week")
    ap.add_argument("--force", action="store_true", help="run even if disabled")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--limit", type=int, default=0, help="max new items (clips+HDRI+etc)")
    ap.add_argument("--max-bytes", type=int, default=0, help="override per-run network cap")
    ap.add_argument("--tier", choices=("all", "main", "adult"), default="all", help="which catalog to update")
    ap.add_argument("--off", action="store_true", help="disable automatic updates")
    ap.add_argument("--on", action="store_true", help="re-enable automatic updates")
    args = ap.parse_args()
    try:
        raise SystemExit(run(args))
    except Exception as e:
        log(f"FATAL {type(e).__name__}: {e}")
        raise


if __name__ == "__main__":
    main()
