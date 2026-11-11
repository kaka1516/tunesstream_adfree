> **Status: Applied in ms-v49** (fam_filter + radio seeds + player famkey.js/famlang.js + SW cache).

# famlang hook patch (minimal — do not apply while lag worker holds music_server.py)

**Files added (safe now):**
- `famlang.py`
- `famlang.js`
- `tests/famlang_fixtures.json`
- `tests/test_famlang.py`
- `tests/test_famlang.js`

**Do not edit concurrently:** `music_server.py`, `player.html` (lag worker). `famkey.js` left untouched; compose at call sites.

## Python (`music_server.py`) — exact hook lines

After the existing song-family block (near `fam_rel` / `fam_filter`, currently ~L290–316), add import once:

```python
from famlang import enrich as famlang_enrich, lang_dub_rel, fam_rel_with_lang
```

### 1) Upgrade `fam_rel` composition (server-side decisions)

Replace call sites that use `fam_rel(a,b)` for radio suppression with:

```python
# a,b are fam_parse dicts OR enrich() item dicts that carry film/composer/duration/langs
def fam_rel_full(item_a, item_b, parsed_a=None, parsed_b=None):
    base = fam_rel(parsed_a or fam_parse(item_a.get("title",""), item_a.get("channel",""), item_a),
                   parsed_b or fam_parse(item_b.get("title",""), item_b.get("channel",""), item_b))
    ea, eb = famlang_enrich(item_a), famlang_enrich(item_b)
    return fam_rel_with_lang(base, ea, eb)
```

In `fam_filter`, change the inner check from `fam_same(f, g)` to also consult lang-dub on the raw items:

```python
# inside fam_filter loop, where x is a candidate dict and seeds hold dicts:
# keep existing fam_parse/fam_same, then:
if any(lang_dub_rel(famlang_enrich(x), famlang_enrich(s if isinstance(s, dict) else {"title": s[0], "channel": s[1]})) == "merge"
       for s in seeds if (s.get("title") if isinstance(s, dict) else s[0])):
    continue
```

Cleaner approach — single helper used by `fam_filter` and recommend:

```python
def fam_same_full(item_a, item_b):
    pa = fam_parse(item_a.get("title",""), item_a.get("channel",""), item_a)
    pb = fam_parse(item_b.get("title",""), item_b.get("channel",""), item_b)
    if fam_same(pa, pb):
        return True
    return lang_dub_rel(famlang_enrich(item_a), famlang_enrich(item_b)) == "merge"
```

Then `fam_filter` uses `fam_same_full(x, seed_item)` instead of `fam_same(fam_parse(...), ...)`.

**Line anchors (ms-v47 / concurrent tree; verify before patch):**
- `fam_rel` definition ~ music_server.py:290
- `fam_filter` ~ music_server.py:309
- recommend `fam_filter(ranked, …)` ~ music_server.py:474

### 2) Enrich on ingest (optional but recommended)

When building search/recommend item dicts from yt-dlp, attach fields once:

```python
item = famlang_enrich({
  "title": info.get("title"), "channel": info.get("channel") or info.get("uploader"),
  "duration": info.get("duration"), "description": info.get("description") or "",
  "track": info.get("track"), "album": info.get("album"), "artist": info.get("artist"),
  "tags": info.get("tags") or [],
})
# persists composer/film/langs for later fam_filter without re-parsing description
```

### 3) Client (`player.html` + `famkey.js`)

Load after famkey:

```html
<script src="/famlang.js"></script>
```

Wrap client filter (famkey `famFilter` / late append):

```javascript
function famSameFull(a, b) {
  if (famSame(famParse(a.title||'', a.channel||'', a), famParse(b.title||'', b.channel||'', b))) return true;
  return famlang.langDubRel(famlang.enrich(a), famlang.enrich(b)) === 'merge';
}
```

Use `famSameFull` in both main recommend append and the ~12s late append.

## Acceptance

```bash
python3 tests/test_famlang.py && node tests/test_famlang.js
python3 tests/test_family.py && node tests/test_family.js   # existing famkey suite must stay green
```

Real pairs in `tests/famlang_fixtures.json` must report exact `merge`/`unknown` labels (not merely merge-vs-not).
