/* famlang.js — cross-language / dubbed-version family gate (mirror of famlang.py).
   Additive to famkey.js. Returns only 'merge' | 'unknown'. Never title-fuzz merge. */
(function (G) {
  const DUR_TOL = 6;
  const TITLE_ALIAS = {
    'naatu naatu': 'naatu naatu', 'natu natu': 'naatu naatu',
    'naacho naacho': 'naatu naatu', 'nacho nacho': 'naatu naatu'
  };
  const COMPOSER_ALIAS = {
    dsp: 'devi sri prasad', 'devi sri prasad': 'devi sri prasad', 'd s p': 'devi sri prasad',
    'mm keeravaani': 'mm keeravaani', 'm m keeravaani': 'mm keeravaani', keeravaani: 'mm keeravaani',
    'm m kreem': 'mm keeravaani', 'mm kreem': 'mm keeravaani', kreem: 'mm keeravaani',
    'ravi basrur': 'ravi basrur'
  };
  const LANG_WORD = {
    telugu: 'te', tollywood: 'te', tamil: 'ta', kollywood: 'ta', hindi: 'hi', bollywood: 'hi',
    kannada: 'kn', sandalwood: 'kn', malayalam: 'ml', mollywood: 'ml',
    bengali: 'bn', punjabi: 'pa', marathi: 'mr', english: 'en'
  };
  const SCRIPTS = [
    ['te', /[\u0C00-\u0C7F]/], ['ta', /[\u0B80-\u0BFF]/], ['kn', /[\u0C80-\u0CFF]/],
    ['ml', /[\u0D00-\u0D7F]/], ['hi', /[\u0900-\u097F]/], ['bn', /[\u0980-\u09FF]/]
  ];
  const FILM_STOP = /\b(songs?|movie|film|ost|soundtrack|full|video|audio|lyrical|official|hit|hits)\b/gi;
  const COMPOSER_TITLE = /\b(dsp|devi\s+sri\s+prasad|m\.?\s*m\.?\s*keeravaani|m\.?\s*m\.?\s*kreem|ravi\s+basrur)\b/i;

  const nf = s => {
    const t = (s || '').normalize('NFKC').toLowerCase().replace(/[^\p{L}\p{M}\p{N}]+/gu, ' ');
    return t.trim().replace(/\s+/g, ' ');
  };
  function composerKey(name) {
    const n = nf(name);
    if (COMPOSER_ALIAS[n]) return COMPOSER_ALIAS[n];
    const compact = n.replace(/\s+/g, '');
    for (const k of Object.keys(COMPOSER_ALIAS)) {
      if (compact === k.replace(/\s+/g, '')) return COMPOSER_ALIAS[k];
    }
    return n;
  }
  function extractComposer(meta, description, title) {
    meta = meta || {};
    if (meta.composer) return composerKey(String(meta.composer));
    const blob = description || meta.description || '';
    const patterns = [
      /^\s*music\s*director\s*[:\-]\s*(.+)$/im,
      /^\s*music\s*composer\s*[:\-]\s*(.+)$/im,
      /^\s*composer\s*[:\-]\s*(.+)$/im,
      /^\s*music\s*by\s*[:\-]?\s*(.+)$/im,
      /^\s*music\s*[:\-]\s*(.+)$/im,
      /\bmusic\s+composed\s+by\s+([^\n.|,]+)/im,
      /\bcomposed\s+by\s+([^\n.|,]+)/im
    ];
    for (const pat of patterns) {
      const m = blob.match(pat);
      if (!m) continue;
      let val = m[1].trim().split(/[|\n•]/)[0].trim().replace(/[#@].*$/, '').trim();
      const low = val.toLowerCase();
      if (low.startsWith('label') || /http|amazon|wynk|apple/.test(low)) continue;
      if (nf(val).length < 2) continue;
      return composerKey(val);
    }
    const t = title || meta.title || '';
    const m = t.match(COMPOSER_TITLE);
    return m ? composerKey(m[1]) : '';
  }
  function filmKey(s) {
    let n = nf(s).replace(FILM_STOP, ' ').replace(/\bthe\s+rise\b/g, ' ');
    n = n.replace(/\s+/g, ' ').trim();
    n = n.replace(/\bkgf\s*chapter\s*2\b/g, 'kgf chapter 2').replace(/\bkgf\s*ch(?:apter)?\s*2\b/g, 'kgf chapter 2');
    if (n.startsWith('rrr')) return 'rrr';
    if (n.startsWith('pushpa')) return 'pushpa';
    return n;
  }
  function filmFromText(s) {
    if (!s) return '';
    let m = s.match(/\b(kgf\s*chapter\s*\d+|kgf\s*ch(?:apter)?\s*\d+|kgf)\b/i);
    if (m) return filmKey(m[1]);
    m = s.match(/\b(rrr)\b/i);
    if (m) return 'rrr';
    m = s.match(/\b(pushpa(?:\s*-\s*the\s+rise)?)\b/i);
    if (m) return 'pushpa';
    m = s.match(/\b(baahubali|salaar|kalki)\b/i);
    if (m) return filmKey(m[1]);
    return '';
  }
  function extractFilm(meta, title, description) {
    meta = meta || {};
    if (meta.film) return filmKey(String(meta.film));
    if (meta.album) return filmKey(String(meta.album));
    const t = title || meta.title || '';
    const blob = description || meta.description || '';
    const parts = t.split(/\s*[|｜]\s*/).map(x => x.trim()).filter(Boolean);
    for (const p of parts) { const h = filmFromText(p); if (h) return h; }
    let hit = filmFromText(t); if (hit) return hit;
    const m = blob.match(/from\s+the\s+movie\s+["'#]*\s*([A-Za-z0-9][A-Za-z0-9 .'\-]{1,60})/i);
    if (m) return filmKey(m[1]);
    for (const p of parts) {
      const n = nf(p);
      if (/\bsongs?\b/i.test(p) && n.split(' ').length <= 5) {
        const k = filmKey(p.replace(FILM_STOP, ' '));
        if (k) return k;
      }
    }
    return '';
  }
  function detectLangs(meta, title, channel, tags) {
    meta = meta || {};
    const found = new Set();
    if (meta.lang) found.add(String(meta.lang).toLowerCase().slice(0, 2));
    const t = title || meta.title || '';
    const ch = channel || meta.channel || '';
    for (const [word, code] of Object.entries(LANG_WORD)) {
      if (new RegExp('[\\(\\[]\\s*' + word + '\\s*[\\)\\]]', 'i').test(t) || new RegExp('\\b' + word + '\\b', 'i').test(t))
        found.add(code);
      if (new RegExp('\\b' + word + '\\b', 'i').test(ch)) found.add(code);
    }
    // Bare T-Series (no language suffix) → Hindi catalog default for official dubs.
    if (/^t\s*series$/.test(nf(ch))) found.add('hi');
    for (const [code, rx] of SCRIPTS) if (rx.test(t)) found.add(code);
    const tagList = tags != null ? tags : meta.tags;
    if (tagList) {
      const blob = Array.isArray(tagList) ? tagList.join(' ') : String(tagList);
      for (const [word, code] of Object.entries(LANG_WORD)) {
        if (new RegExp('\\b' + word + '\\b', 'i').test(blob)) found.add(code);
      }
    }
    return found;
  }
  function enrich(item) {
    const x = Object.assign({}, item);
    const title = x.title || '', ch = x.channel || '', desc = x.description || '';
    if (!x.composer) x.composer = extractComposer(x, desc, title);
    if (!x.film) x.film = x.album ? filmKey(String(x.album)) : extractFilm(x, title, desc);
    x.langs = Array.from(detectLangs(x, title, ch, x.tags)).sort();
    if (x.duration == null && x.dur != null) x.duration = x.dur;
    return x;
  }
  function durationOf(x) {
    for (const k of ['duration', 'dur', 'length']) {
      if (x[k] == null || x[k] === '') continue;
      const n = Number(x[k]); if (!Number.isNaN(n)) return n;
    }
    return null;
  }
  function filmOf(x) {
    if (x.film) return filmKey(String(x.film));
    if (x.album) return filmKey(String(x.album));
    return extractFilm(x, x.title || '', x.description || '');
  }
  function composerOf(x) {
    if (x.composer) return composerKey(String(x.composer));
    return extractComposer(x, x.description || '', x.title || '');
  }
  function langsOf(x) {
    if (x.langs && x.langs.length) return new Set(x.langs);
    if (x.lang) return new Set([String(x.lang).toLowerCase().slice(0, 2)]);
    return detectLangs(x, x.title || '', x.channel || '', x.tags);
  }

  function titleBase(x){
    let t=x.title||'';
    t=t.replace(/^\s*(?:full\s+video\s*:\s*|video\s+song\s*:\s*)/i,'');
    let head=t.split(/\s*[|｜]\s*/)[0]||'';
    head=head.split(/\s[-–—]\s/)[0]||head;
    if(head.includes(':')){const [left,...rest]=head.split(':'); const right=rest.join(':'); if(filmFromText(left)||nf(left).split(' ').length<=3) head=right}
    head=head.replace(/[\(\[\{][^\)\]\}]*[\)\]\}]/g,' ');
    let n=nf(head).replace(/\b(lyrical|lyric|lyrics|video|audio|official|full|song|songs|hd|4k|8k|telugu|tamil|hindi|kannada|malayalam)\b/g,' ');
    n=n.replace(/\b(rrr|pushpa|kgf(?:\s*chapter\s*\d+)?|baahubali|salaar|kalki)\b/g,' ');
    return n.replace(/\s+/g,' ').trim();
  }
  function titleFamily(x){
    const b=titleBase(x); if(!b) return '';
    if(TITLE_ALIAS[b]) return TITLE_ALIAS[b];
    const compact=b.replace(/\s+/g,'');
    for(const k of Object.keys(TITLE_ALIAS)){ if(compact===k.replace(/\s+/g,'')) return TITLE_ALIAS[k]; }
    return b;
  }

  function langDubRel(a, b) {
    const fa = filmOf(a), fb = filmOf(b);
    if (!fa || !fb || fa !== fb) return 'unknown';
    const ca = composerOf(a), cb = composerOf(b);
    if (!ca || !cb || ca !== cb) return 'unknown';
    const da = durationOf(a), db = durationOf(b);
    if (da == null || db == null || Math.abs(da - db) > DUR_TOL) return 'unknown';
    const la = langsOf(a), lb = langsOf(b);
    if (!la.size || !lb.size) return 'unknown';
    for (const x of la) if (lb.has(x)) return 'unknown';
    const ta = titleFamily(a), tb = titleFamily(b);
    if (!ta || !tb || ta !== tb) return 'unknown';
    return 'merge';
  }
  function famRelWithLang(baseRel, a, b) {
    if (baseRel === 'merge') return 'merge';
    if (langDubRel(a, b) === 'merge') return 'merge';
    return baseRel;
  }
  const api = { DUR_TOL, extractComposer, extractFilm, detectLangs, enrich, langDubRel, famRelWithLang };
  G.famlang = api;
  if (typeof module !== 'undefined') module.exports = api;
})(typeof window !== 'undefined' ? window : globalThis);
