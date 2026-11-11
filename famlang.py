# famlang.py — cross-language / dubbed-version family gate (additive to famkey/fam_rel).
# Does NOT replace fam_rel. Returns only 'merge' or 'unknown' (never 'distinct').
# Rule (all required): same film/album segment AND same composer/MD credit
#   AND duration within ±DUR_TOL s AND detectable different languages/scripts.
# Never merges on title fuzz / edit-distance alone.
# Optional MusicBrainz work lookup is OFF hot path (cached, ≤1 req/s); see mb_work_lookup.

from __future__ import annotations
import re, time, unicodedata
from typing import Any, Dict, Optional, Set, Tuple

DUR_TOL = 6

# Verified billing aliases observed on official multi-lang uploads (RRR / Pushpa fixtures).
_TITLE_ALIAS = {
    # Official dubbed renames (evidence: RRR T-Series Telugu Naatu Naatu ↔ T-Series Hindi Naacho Naacho)
    "naatu naatu": "naatu naatu",
    "natu natu": "naatu naatu",
    "naacho naacho": "naatu naatu",
    "nacho nacho": "naatu naatu",
}
_COMPOSER_ALIAS = {
    "dsp": "devi sri prasad",
    "devi sri prasad": "devi sri prasad",
    "d s p": "devi sri prasad",
    "mm keeravaani": "mm keeravaani",
    "m m keeravaani": "mm keeravaani",
    "keeravaani": "mm keeravaani",
    "m m kreem": "mm keeravaani",  # Hindi billing of M.M. Keeravaani (RRR Naacho credits)
    "mm kreem": "mm keeravaani",
    "kreem": "mm keeravaani",
    "ravi basrur": "ravi basrur",
}

_LANG_WORD = {
    "telugu": "te", "tollywood": "te",
    "tamil": "ta", "kollywood": "ta",
    "hindi": "hi", "bollywood": "hi",
    "kannada": "kn", "sandalwood": "kn",
    "malayalam": "ml", "mollywood": "ml",
    "bengali": "bn", "punjabi": "pa", "marathi": "mr", "english": "en",
}

_SCRIPT_RANGES = (
    ("te", re.compile(r"[\u0C00-\u0C7F]")),
    ("ta", re.compile(r"[\u0B80-\u0BFF]")),
    ("kn", re.compile(r"[\u0C80-\u0CFF]")),
    ("ml", re.compile(r"[\u0D00-\u0D7F]")),
    ("hi", re.compile(r"[\u0900-\u097F]")),
    ("bn", re.compile(r"[\u0980-\u09FF]")),
)

_FILM_STOP = re.compile(
    r"\b(songs?|movie|film|ost|soundtrack|full|video|audio|lyrical|official|hit|hits)\b",
    re.I,
)

_COMPOSER_TITLE_RX = re.compile(
    r"\b(dsp|devi\s+sri\s+prasad|m\.?\s*m\.?\s*keeravaani|m\.?\s*m\.?\s*kreem|ravi\s+basrur)\b",
    re.I,
)


def _nf(s: str) -> str:
    t = "".join(
        c if unicodedata.category(c)[0] in "LMN" else " "
        for c in unicodedata.normalize("NFKC", s or "").lower()
    )
    return " ".join(t.split())


def _composer_key(name: str) -> str:
    n = _nf(name)
    if n in _COMPOSER_ALIAS:
        return _COMPOSER_ALIAS[n]
    compact = n.replace(" ", "")
    for k, v in _COMPOSER_ALIAS.items():
        if compact == k.replace(" ", ""):
            return v
    return n


def extract_composer(meta: Optional[Dict[str, Any]] = None, description: str = "", title: str = "") -> str:
    """Parse Music:/Music by:/Composer/Music Director from description or meta fields."""
    meta = meta or {}
    if meta.get("composer"):
        return _composer_key(str(meta["composer"]))
    blob = description or meta.get("description") or ""
    patterns = [
        r"(?im)^\s*music\s*director\s*[:\-]\s*(.+)$",
        r"(?im)^\s*music\s*composer\s*[:\-]\s*(.+)$",
        r"(?im)^\s*composer\s*[:\-]\s*(.+)$",
        r"(?im)^\s*music\s*by\s*[:\-]?\s*(.+)$",
        r"(?im)^\s*music\s*[:\-]\s*(.+)$",
        r"(?im)\bmusic\s+composed\s+by\s+([^\n\.|,]+)",
        r"(?im)\bcomposed\s+by\s+([^\n\.|,]+)",
    ]
    for pat in patterns:
        m = re.search(pat, blob)
        if not m:
            continue
        val = m.group(1).strip()
        val = re.split(r"[|\n•]", val)[0].strip()
        val = re.sub(r"[#@].*$", "", val).strip()
        low = val.lower()
        if low.startswith("label") or "http" in low or "amazon" in low or "wynk" in low or "apple" in low:
            continue
        if len(_nf(val)) < 2:
            continue
        return _composer_key(val)
    t = title or meta.get("title") or ""
    m = _COMPOSER_TITLE_RX.search(t)
    if m:
        return _composer_key(m.group(1))
    return ""


def _film_key(s: str) -> str:
    n = _nf(s)
    n = _FILM_STOP.sub(" ", n)
    n = re.sub(r"\bthe\s+rise\b", " ", n)
    n = " ".join(n.split())
    n = re.sub(r"\bkgf\s*chapter\s*2\b", "kgf chapter 2", n)
    n = re.sub(r"\bkgf\s*ch(?:apter)?\s*2\b", "kgf chapter 2", n)
    if n.startswith("rrr"):
        return "rrr"
    if n.startswith("pushpa"):
        return "pushpa"
    return n


def _film_from_text(s: str) -> str:
    if not s:
        return ""
    m = re.search(r"(?i)\b(kgf\s*chapter\s*\d+|kgf\s*ch(?:apter)?\s*\d+|kgf)\b", s)
    if m:
        return _film_key(m.group(0))
    m = re.search(r"(?i)\b(rrr)\b", s)
    if m:
        return "rrr"
    m = re.search(r"(?i)\b(pushpa(?:\s*-\s*the\s+rise)?)\b", s)
    if m:
        return "pushpa"
    m = re.search(r"(?i)\b(baahubali|salaar|kalki)\b", s)
    if m:
        return _film_key(m.group(1))
    return ""


def extract_film(meta: Optional[Dict[str, Any]] = None, title: str = "", description: str = "") -> str:
    """Film/album segment from album field, title pipes, or 'from the movie X'."""
    meta = meta or {}
    if meta.get("film"):
        return _film_key(str(meta["film"]))
    if meta.get("album"):
        return _film_key(str(meta["album"]))
    t = title or meta.get("title") or ""
    blob = description or meta.get("description") or ""
    parts = [p.strip() for p in re.split(r"[|｜]", t) if p.strip()]
    for p in parts:
        hit = _film_from_text(p)
        if hit:
            return hit
    hit = _film_from_text(t)
    if hit:
        return hit
    m = re.search(r"(?i)from\s+the\s+movie\s+[\"'#]*\s*([A-Za-z0-9][A-Za-z0-9 .'\-]{1,60})", blob)
    if m:
        return _film_key(m.group(1))
    for p in parts:
        n = _nf(p)
        if re.search(r"(?i)\bsongs?\b", p) and len(n.split()) <= 5:
            k = _film_key(_FILM_STOP.sub(" ", p))
            if k:
                return k
    return ""


def detect_langs(meta: Optional[Dict[str, Any]] = None, title: str = "", channel: str = "", tags=None) -> Set[str]:
    """Language set from title/channel markers, scripts, meta.lang, and yt tags.
    Does NOT scrape free-text description (multi-lang promo blurbs name every language)."""
    meta = meta or {}
    found: Set[str] = set()
    if meta.get("lang"):
        found.add(str(meta["lang"]).lower()[:2])
    t = title or meta.get("title") or ""
    ch = channel or meta.get("channel") or ""
    for word, code in _LANG_WORD.items():
        if re.search(rf"(?i)[\(\[]\s*{word}\s*[\)\]]", t) or re.search(rf"(?i)\b{word}\b", t):
            found.add(code)
    for word, code in _LANG_WORD.items():
        if re.search(rf"(?i)\b{word}\b", ch):
            found.add(code)
    # Bare T-Series (no Telugu/Tamil/Kannada suffix) is the Hindi catalog label on official dubs.
    if re.fullmatch(r"t\s*series", _nf(ch)):
        found.add("hi")
    for code, rx in _SCRIPT_RANGES:
        if rx.search(t):
            found.add(code)
    tag_list = tags if tags is not None else meta.get("tags")
    if tag_list:
        blob = " ".join(tag_list) if isinstance(tag_list, (list, tuple)) else str(tag_list)
        for word, code in _LANG_WORD.items():
            if re.search(rf"(?i)\b{word}\b", blob):
                found.add(code)
    return found


def enrich(item: Dict[str, Any]) -> Dict[str, Any]:
    """Shallow-copy item with composer/film/langs/duration filled when missing."""
    x = dict(item)
    title = x.get("title") or ""
    ch = x.get("channel") or ""
    desc = x.get("description") or ""
    if not x.get("composer"):
        x["composer"] = extract_composer(x, desc, title)
    if not x.get("film"):
        if x.get("album"):
            x["film"] = _film_key(str(x["album"]))
        else:
            x["film"] = extract_film(x, title, desc)
    langs = detect_langs(x, title, ch, x.get("tags"))
    x["langs"] = sorted(langs)
    if x.get("duration") is None and x.get("dur") is not None:
        x["duration"] = x["dur"]
    return x


def _duration(x: Dict[str, Any]) -> Optional[float]:
    for k in ("duration", "dur", "length"):
        v = x.get(k)
        if v is None or v == "":
            continue
        try:
            return float(v)
        except (TypeError, ValueError):
            continue
    return None


def _film_of(x: Dict[str, Any]) -> str:
    if x.get("film"):
        return _film_key(str(x["film"]))
    if x.get("album"):
        return _film_key(str(x["album"]))
    return extract_film(x, x.get("title") or "", x.get("description") or "")


def _composer_of(x: Dict[str, Any]) -> str:
    if x.get("composer"):
        return _composer_key(str(x["composer"]))
    return extract_composer(x, x.get("description") or "", x.get("title") or "")


def _langs_of(x: Dict[str, Any]) -> Set[str]:
    if x.get("langs"):
        return set(x["langs"])
    if x.get("lang"):
        return {str(x["lang"]).lower()[:2]}
    return detect_langs(x, x.get("title") or "", x.get("channel") or "", x.get("tags"))



def _title_base(x: Dict[str, Any]) -> str:
    """Rough song-title core from the item title (first pipe/colon segment, packaging stripped)."""
    t = x.get("title") or ""
    t = re.sub(r"(?i)^\s*(?:full\s+video\s*:\s*|video\s+song\s*:\s*)", "", t)
    head = re.split(r"[|｜]", t, 1)[0]
    head = re.split(r"\s[-–—]\s", head)[0]
    if ":" in head:
        left, right = head.split(":", 1)
        if _film_from_text(left) or len(_nf(left).split()) <= 3:
            head = right
    head = re.sub(r"[\(\[\{][^\)\]\}]*[\)\]\}]", " ", head)
    n = _nf(head)
    n = re.sub(r"\b(lyrical|lyric|lyrics|video|audio|official|full|song|songs|hd|4k|8k|telugu|tamil|hindi|kannada|malayalam)\b", " ", n)
    # Drop film tokens so "Naacho Naacho RRR" → "naacho naacho"
    n = re.sub(r"\b(rrr|pushpa|kgf(?:\s*chapter\s*\d+)?|baahubali|salaar|kalki)\b", " ", n)
    n = " ".join(n.split())
    return n

def _title_family(x: Dict[str, Any]) -> str:
    b = _title_base(x)
    if not b:
        return ""
    if b in _TITLE_ALIAS:
        return _TITLE_ALIAS[b]
    compact = b.replace(" ", "")
    for k, v in _TITLE_ALIAS.items():
        if compact == k.replace(" ", ""):
            return v
    return b

def lang_dub_rel(a: Dict[str, Any], b: Dict[str, Any]) -> str:
    """'merge' if dubbed/cross-lang same composition by film+composer+duration+lang; else 'unknown'."""
    fa, fb = _film_of(a), _film_of(b)
    if not fa or not fb or fa != fb:
        return "unknown"
    ca, cb = _composer_of(a), _composer_of(b)
    if not ca or not cb or ca != cb:
        return "unknown"
    da, db = _duration(a), _duration(b)
    if da is None or db is None or abs(da - db) > DUR_TOL:
        return "unknown"
    la, lb = _langs_of(a), _langs_of(b)
    if not la or not lb:
        return "unknown"
    if la & lb:
        return "unknown"
    # Title family: same core title OR registered dub alias (Naatu↔Naacho). Blocks same-film different songs (Srivalli vs Oo Solriya).
    ta, tb = _title_family(a), _title_family(b)
    if not ta or not tb or ta != tb:
        return "unknown"
    return "merge"


def fam_rel_with_lang(base_rel: str, a: Dict[str, Any], b: Dict[str, Any]) -> str:
    """Compose existing fam_rel label with lang-dub gate. Only upgrades unknown→merge."""
    if base_rel == "merge":
        return "merge"
    if lang_dub_rel(a, b) == "merge":
        return "merge"
    return base_rel


_mb_cache: Dict[str, Tuple[float, Any]] = {}
_MB_MIN_INTERVAL = 1.0


def mb_work_lookup(recording_hint: str, user_agent: str, session=None, enable: bool = False):
    """Optional MB recording→work lookup. Disabled unless enable=True. ≤1 req/s, requires User-Agent.
    Off hot path. Returns cached value or None; network left to caller when enable=True."""
    if not enable or not recording_hint or not user_agent:
        return None
    key = _nf(recording_hint)
    now = time.time()
    if key in _mb_cache and now - _mb_cache[key][0] < 86400:
        return _mb_cache[key][1]
    _mb_cache[key] = (now, None)
    return None


__all__ = [
    "DUR_TOL", "extract_composer", "extract_film", "detect_langs", "enrich",
    "lang_dub_rel", "fam_rel_with_lang", "mb_work_lookup",
]
