/* Music Stream — beat-synced 3D dancer (ms-v80).
 * Replaces the ms-v77 procedural stage dancer + 2D scenes (backed up in /backup-v80).
 *
 * Third-party pieces (all fetched by URL at runtime from this server, licences in /licenses and /assets/dance):
 *  - three.js (MIT) https://github.com/mrdoob/three.js
 *  - @pixiv/three-vrm + @pixiv/three-vrm-animation 3.3.4 (MIT) https://github.com/pixiv/three-vrm
 *  - Dance clips: open-vrma dataset (https://huggingface.co/datasets/Sanami/open-vrma, converter https://github.com/sanamiy/open-vrma)
 *      * CMU Graphics Lab Motion Capture Database clips (cmu_*.vrma) — "The data used in this project was obtained from
 *        mocap.cs.cmu.edu. The database was created with funding from NSF EIA-0196217." Free to copy/modify/redistribute,
 *        may not be resold as data.
 *      * Quaternius Universal Animation Library (quaternius_*.vrma) — CC0-1.0, animations by Quaternius (https://quaternius.com/)
 *  - VRM models: VRoid sample avatars already shipped in /assets/chars/vrm (see docs/GAME_CREDITS.md).
 * The beat tracker, tempo-warp, phase-lock and phrase switching below are original Music Stream code.
 *
 * How it stays on the beat:
 *  1. BeatTracker reads a dedicated low-smoothing AnalyserNode fanned off the player's real MediaElementSource,
 *     computes spectral flux per frame, estimates tempo by autocorrelation of the last ~8 s of flux (70-180 BPM,
 *     octave-folded), and locks a beat clock (phase-locked loop) to the strongest comb alignment.
 *  2. Each clip carries its own motion tempo + first-beat offset (open-vrma metadata). Playback rate =
 *     songBPM / clipBPM (choosing the clip tempo octave closest to the song), so one clip beat = one song beat.
 *  3. On every song beat the clip's beat phase is measured and the rate is nudged (phase lock), so motion
 *     accents keep landing on the beat even if either tempo estimate drifts.
 *  4. Every 16 beats (a phrase) the next clip is cross-faded in over one beat, started exactly on one of its beats.
 *  5. A small additive groove (hips dip + head nod) is driven straight from the beat clock.
 */
import * as THREE from 'three';
import { GLTFLoader } from 'three/addons/loaders/GLTFLoader.js';
import { VRMLoaderPlugin, VRMUtils } from '@pixiv/three-vrm';
import { VRMAnimationLoaderPlugin, createVRMAnimationClip } from '@pixiv/three-vrm-animation';
import { RoomEnvironment } from 'three/addons/environments/RoomEnvironment.js';
import { attachTheme } from './dance-themes.js?v=18';
import { createBackdrop } from './viz-gpu.js?v=18';

const TAU = Math.PI * 2;
const clamp = (v, a, b) => (v < a ? a : v > b ? b : v);

/* ---------------- beat tracker ---------------- */
export class BeatTracker {
  constructor(AC, src, fallbackAnalyser) {
    this.AC = AC;
    let an = null;
    try {
      if (AC && src) {
        an = AC.createAnalyser(); an.fftSize = 1024; an.smoothingTimeConstant = 0.1;
        src.connect(an); const z = AC.createGain(); z.gain.value = 0; an.connect(z); z.connect(AC.destination);
        this._own = true;
      }
    } catch (e) { an = null; }
    this.an = an || fallbackAnalyser;
    this.n = this.an ? this.an.frequencyBinCount : 0;
    this.cur = new Uint8Array(this.n); this.prev = new Uint8Array(this.n);
    this.T = []; this.F = [];            // frame times (s) and flux
    this.bpm = 0; this.conf = 0; this.period = 0.5; this.t0 = 0; this.locked = false;
    this.energy = 0; this.lastEst = 0; this.cand = 0; this.candN = 0; this.beatIdx = 0; this.lastBeatSeen = -1;
    this.history = [];                   // bpm estimates for logging
  }
  now() { return this.AC ? this.AC.currentTime : performance.now() / 1000; }
  frame(paused) {
    if (!this.an) return;
    const t = this.now();
    if (t === this._lastT) return; this._lastT = t;
    this.an.getByteFrequencyData(this.cur);
    let flux = 0, e = 0; const hi = Math.min(this.n, 186); // ~0-8 kHz
    for (let i = 1; i < hi; i++) {
      const d = this.cur[i] - this.prev[i]; const w = i < 7 ? 2.2 : i < 30 ? 1.2 : 0.7;
      if (d > 0) flux += d * w; e += this.cur[i];
    }
    this.prev.set(this.cur);
    this.energy = this.energy * 0.9 + 0.1 * (e / (hi * 255));
    if (paused) return;
    this.T.push(t); this.F.push(flux);
    while (this.T.length && t - this.T[0] > 10) { this.T.shift(); this.F.shift(); }
    if (t - this.lastEst > 0.75 && this.T.length > 60 && t - this.T[0] > 4) { this.lastEst = t; this.estimate(t); }
  }
  /* resample flux to 100 Hz, autocorrelate, comb-search phase */
  estimate(now) {
    const R = 100, T = this.T, F = this.F, t0 = T[0], N = Math.floor((now - t0) * R);
    if (N < 300) return;
    const x = new Float32Array(N); let j = 0;
    for (let i = 0; i < N; i++) {
      const tt = t0 + i / R; while (j < T.length - 2 && T[j + 1] < tt) j++;
      const a = T[j], b = T[j + 1] || a, f = b > a ? (tt - a) / (b - a) : 0; x[i] = F[j] * (1 - f) + (F[j + 1] || F[j]) * f;
    }
    // local-mean removal (0.4 s) + half-wave rectify => onset novelty
    const W = 20, y = new Float32Array(N); let s = 0;
    for (let i = 0; i < N; i++) { s += x[i]; if (i >= W) s -= x[i - W]; const m = s / Math.min(i + 1, W); y[i] = Math.max(0, x[i] - m); }
    let mean = 0; for (let i = 0; i < N; i++) mean += y[i]; mean /= N;
    if (mean < 0.5) { this.conf *= 0.9; return; }
    const ac = (lag) => { let r = 0; for (let i = lag; i < N; i++) r += (y[i] - mean) * (y[i - lag] - mean); return r / (N - lag); };
    const r0 = ac(0) || 1;
    const acf = (L) => { const l0 = Math.floor(L), fr = L - l0; return (ac(l0) * (1 - fr) + ac(l0 + 1) * fr) / r0; };
    // score = periodicity at one beat + at two beats (bar-level repetition), weighted by a broad tempo prior around 118 BPM
    const score = (bpm) => { const L = 60 / bpm * R; const prior = Math.exp(-0.5 * Math.pow(Math.log2(bpm / 118) / 0.55, 2)); return (acf(L) + 0.5 * acf(2 * L)) * (0.45 + 0.55 * prior); };
    let best = -1, bestBpm = 0;
    for (let bpm = 70; bpm <= 160; bpm += 0.5) { const sc = score(bpm); if (sc > best) { best = sc; bestBpm = bpm; } }   // >160 folds to half-time
    let rb = bestBpm, rv = -1;
    for (let bpm = bestBpm - 1; bpm <= bestBpm + 1; bpm += 0.1) { const v = acf(60 / bpm * R); if (v > rv) { rv = v; rb = bpm; } }
    bestBpm = rb;
    const conf = clamp(best, 0, 1);
    if (!this.bpm) { this.bpm = bestBpm; this.candN = 0; }
    else if (Math.abs(bestBpm - this.bpm) / this.bpm < 0.035) { this.bpm = this.bpm * 0.75 + bestBpm * 0.25; this.candN = 0; }
    else {
      // keep the current tempo unless a different one is clearly better three estimates in a row (stops 2:1 / 3:2 flips)
      let cb = this.bpm, cv = -1; for (let bpm = this.bpm * 0.98; bpm <= this.bpm * 1.02; bpm += 0.1) { const v = score(bpm); if (v > cv) { cv = v; cb = bpm; } }
      if (best > cv * 1.35 && Math.abs(bestBpm - this.cand) / bestBpm < 0.035) { if (++this.candN >= 4) { this.bpm = bestBpm; this.candN = 0; this.switches = (this.switches || 0) + 1; } }
      else { this.cand = bestBpm; this.candN = best > cv * 1.35 ? 1 : 0; this.bpm = this.bpm * 0.8 + cb * 0.2; }
    }
    this.conf = this.conf * 0.6 + conf * 0.4;
    const P = 60 / this.bpm, PL = P * R;
    // phase: comb over the last 6 beats, find offset φ (s before now) of the most recent beat
    let bp = 0, bv = -1; const K = Math.min(8, Math.floor((N - 1) / PL));
    for (let ph = 0; ph < PL; ph += 1) {
      let v = 0; for (let k = 0; k < K; k++) { const idx = Math.round(N - 1 - ph - k * PL); if (idx >= 1) v += y[idx] + 0.5 * (y[idx - 1] + (y[idx + 1] || 0)); }
      if (v > bv) { bv = v; bp = ph; }
    }
    const lastBeat = now - bp / R;
    if (!this.locked) { this.period = P; this.t0 = lastBeat; this.locked = true; }
    else {
      this.period = this.period * 0.6 + P * 0.4;
      // move t0 to the predicted beat nearest lastBeat, then correct 35% of the error
      const k = Math.round((lastBeat - this.t0) / this.period); const pred = this.t0 + k * this.period; let err = lastBeat - pred;
      if (Math.abs(err) > this.period / 2) err = 0;
      this.t0 = pred + 0.35 * err;
    }
    this.history.push({ t: +now.toFixed(2), bpm: +this.bpm.toFixed(1), conf: +this.conf.toFixed(2) }); if (this.history.length > 60) this.history.shift();
  }
  /* sample the analyser ~100x/s independent of the render frame rate (onset timing no longer quantised to 33-66 ms frames) */
  run(isPaused) { this.stop(); this._iv = setInterval(() => { try { this.frame(isPaused()); } catch (_) {} }, 10); }
  stop() { if (this._iv) clearInterval(this._iv); this._iv = 0; }
  reset() { this.T.length = 0; this.F.length = 0; this.bpm = 0; this.conf = 0; this.locked = false; this.cand = 0; this.candN = 0; this.lastEst = 0; }
  latency() { return this.AC ? ((this.AC.outputLatency || 0) + (this.AC.baseLatency || 0)) : 0; }
  /* first predicted beat at or after time t (in the analyser's clock) */
  nextBeatAfter(t) { if (!this.locked) return null; const k = Math.ceil((t - this.t0) / this.period - 1e-6); return this.t0 + k * this.period; }
}

/* ---------------- dancefix (2026-11-10): model download ----------------
 * Wi-Fi links here cap each TCP connection at ~65-80 KB/s but scale with parallel connections, so a model is
 * fetched as 256 KB byte ranges over 6 connections. Progress is bytes received / known file size (from
 * Content-Range), reported only when it goes up. Loads are abortable (switching model cancels the old one).
 * The bytes are kept in IndexedDB (works on plain-http LAN pages, unlike Cache Storage) so the next load is instant.
 * "lite" models are /assets/chars/vrm/lite/<name>.vrm.gz: same mesh/rig, smaller textures, gzip-compressed;
 * they are inflated here with DecompressionStream. */
const MDB = 'ms-dance-models', MST = 'm', MKEY = 'df1|';
function mdb() { return new Promise((res, rej) => { if (!self.indexedDB) return rej(new Error('noidb')); const r = indexedDB.open(MDB, 1); r.onupgradeneeded = () => r.result.createObjectStore(MST); r.onsuccess = () => res(r.result); r.onerror = () => rej(r.error); }); }
async function mGet(k) { try { const db = await mdb(); return await new Promise((res) => { const q = db.transaction(MST, 'readonly').objectStore(MST).get(k); q.onsuccess = () => res(q.result || null); q.onerror = () => res(null); }); } catch (_) { return null; } }
async function mPut(k, v) { try { const db = await mdb(); await new Promise((res) => { const tx = db.transaction(MST, 'readwrite'); tx.objectStore(MST).put(v, k); tx.oncomplete = res; tx.onerror = res; tx.onabort = res; }); } catch (_) {} }
async function inflate(buf) { return await new Response(new Blob([buf]).stream().pipeThrough(new DecompressionStream('gzip'))).arrayBuffer(); }
export async function fetchModelBytes(url, o = {}) {
  const prog = o.onProgress || (() => {}), sig = o.signal, CH = o.chunk || 262144, N = o.conc || (location.protocol === 'https:' ? 2 : 4), gz = /\.gz$/.test(url);
  const out = (b) => (gz ? inflate(b) : b);
  const hit = await mGet(MKEY + url);
  if (hit && hit.byteLength) { prog(1, hit.byteLength, hit.byteLength, true); return out(hit); }
  if (sig && sig.aborted) throw new DOMException('aborted', 'AbortError');
  let total = 0, done = 0, best = -1, buf = null;
  const rep = () => { if (!total) return; const p = Math.min(1, done / total); if (p > best) { best = p; prog(p, Math.min(done, total), total, false); } };
  async function rd(r, a) {           // stream a response body into buf at offset a, counting progress
    const rdr = r.body.getReader(); let at = a, got = 0;
    try { for (;;) { const { done: d, value } = await rdr.read(); if (d) break; if (at + value.length > buf.length) throw new Error('range overflow'); buf.set(value, at); at += value.length; got += value.length; done += value.length; rep(); } }
    catch (e) { done -= got; throw e; }
    return got;
  }
  // first range tells us the size and whether ranges work
  let r = await fetch(url, { headers: { Range: `bytes=0-${CH - 1}` }, signal: sig });
  if (!r.ok) throw new Error('model HTTP ' + r.status);
  if (r.status === 200) {               // no range support: one stream, size from Content-Length
    total = +(r.headers.get('Content-Length') || 0);
    if (!total || r.headers.get('Content-Encoding')) { const b = await r.arrayBuffer(); total = b.byteLength; done = total; rep(); await mPut(MKEY + url, b); return out(b); }
    buf = new Uint8Array(total); await rd(r, 0);
  } else {
    const m = /\/(\d+)\s*$/.exec(r.headers.get('Content-Range') || ''); total = m ? +m[1] : 0; if (!total) throw new Error('model size unknown');
    buf = new Uint8Array(total); await rd(r, 0);
    const q = []; for (let a = CH; a < total; a += CH) q.push([a, Math.min(total, a + CH) - 1]);
    async function worker() {
      while (q.length) {
        const [a, b] = q.shift();
        for (let tries = 0; ; tries++) {
          try {
            const x = await fetch(url, { headers: { Range: `bytes=${a}-${b}` }, signal: sig });
            if (x.status !== 206) throw new Error('range HTTP ' + x.status);
            const got = await rd(x, a); if (got !== b - a + 1) { done -= got; throw new Error('short range'); }
            break;
          } catch (e) { if ((sig && sig.aborted) || tries >= 3) throw e; await new Promise((z) => setTimeout(z, 400 * (tries + 1))); }
        }
      }
    }
    await Promise.all(Array.from({ length: Math.min(N, q.length || 1) }, worker));
  }
  done = total; rep();
  const ab = buf.buffer; await mPut(MKEY + url, ab); return out(ab);
}

/* ---------------- dancer ---------------- */
/* latency-20261110 (sharp desktop dancer): desktops / non-mobile wide screens on a link that isn't measured slow get
 * antialiasing, devicePixelRatio up to 2, ACES filmic tone mapping, 3-point + hemisphere light, a RoomEnvironment IBL,
 * 2048 px soft shadows and anisotropic texture filtering. Phones and slow links keep the light path. */
export function linkLooksSlow() {
  try { const c = navigator.connection || navigator.mozConnection || navigator.webkitConnection;
    if (c && (c.saveData || /(^|-)2g$|^3g$/.test(c.effectiveType || '') || (typeof c.downlink === 'number' && c.downlink > 0 && c.downlink < 1.5))) return true; } catch (_) {}
  return false;
}
export function highQualityDevice(phone) {
  const uaMobile = /Mobile|Android|iPhone|iPod|iPad/i.test(navigator.userAgent || '');
  return !phone && !uaMobile && (window.innerWidth || 0) >= 700 && !linkLooksSlow();
}
const MOODS_OK = ['romantic', 'sad', 'party', 'chill', 'happy', 'devotional'];
export function clipMoods(c) { return [].concat(c.mood || [], c.moods || []); }
export async function createDance(container, opts) {
  const phone = !!opts.phone, base = opts.base || '/assets/dance/';
  const high = opts.highQuality != null ? !!opts.highQuality : highQualityDevice(phone);
  // dancefix: begin the (big) model download right away instead of after clips.json + 3 clips
  let pre = null;
  if (opts.modelUrl) { const P = pre = { url: opts.modelUrl, ac: new AbortController(), onp: (...a) => { if (opts.onProgress) opts.onProgress(...a); } }; P.p = fetchModelBytes(P.url, { signal: P.ac.signal, onProgress: (...a) => P.onp(...a) }); P.p.catch(() => {}); }
  let _rev = (typeof window !== 'undefined' && window.__MS_VIZ_REV) || 'vizadv';
  if (typeof window !== 'undefined' && !window.__MS_VIZ_REV) {
    try {
      await new Promise((res) => {
        const s = document.createElement('script');
        s.src = '/assets/viz/rev.js?t=' + Date.now();
        s.onload = s.onerror = () => res();
        document.head.appendChild(s);
      });
      if (window.__MS_VIZ_REV) _rev = window.__MS_VIZ_REV;
    } catch (_) {}
  }
  const manifest = await (await fetch(base + 'clips.json?v=' + encodeURIComponent(_rev))).json();
  // adult-viz-20261111: merge the gated 18+ catalog only when the user flag is on. Never request it otherwise.
  try {
    const adultOn = (typeof window !== 'undefined' && typeof window.__msAdultViz === 'function') ? !!window.__msAdultViz() : false;
    if (adultOn) {
      const ar = await fetch('/assets/dance/adult/clips.json?v=' + encodeURIComponent(_rev), { cache: 'no-store' });
      if (ar.ok) {
        const aj = await ar.json();
        const extra = (aj && aj.clips) || [];
        const list = Array.isArray(manifest.clips) ? manifest.clips.slice() : [];
        const ix = new Map(list.map((c, i) => [c && c.id, i]));
        for (const c of extra) {
          if (!c || !c.id || !c.file) continue;
          const rec = Object.assign({}, c, { adult: true });
          if (ix.has(rec.id)) list[ix.get(rec.id)] = rec;
          else { ix.set(rec.id, list.length); list.push(rec); }
        }
        manifest.clips = list;
        manifest.adultLoaded = true;
      }
    }
  } catch (e) { console.warn('adult catalog', e); }
  const renderer = new THREE.WebGLRenderer({ alpha: true, antialias: high || !phone, powerPreference: phone ? 'low-power' : 'high-performance' });
  renderer.setClearColor(0, 0); renderer.outputColorSpace = THREE.SRGBColorSpace;
  if (high) { renderer.toneMapping = THREE.ACESFilmicToneMapping; renderer.toneMappingExposure = 1.05; renderer.shadowMap.enabled = true; renderer.shadowMap.type = THREE.PCFSoftShadowMap; }
  const cvs = renderer.domElement; cvs.id = 'vizdance';
  cvs.style.cssText = 'position:absolute;inset:0;width:100%;height:100%;pointer-events:none;z-index:1';
  container.appendChild(cvs);
  let lost = false; cvs.addEventListener('webglcontextlost', (e) => { lost = true; e.preventDefault(); });
  cvs.addEventListener('webglcontextrestored', () => { lost = false; });

  const scene = new THREE.Scene();
  const cam = new THREE.PerspectiveCamera(30, 1, 0.05, 50);
  // 3-point light + hemisphere (latency-20261110); desktop adds image-based light and soft shadows
  // Hidden when Club / Cinematic themes bring their own lights.
  const baseLights = new THREE.Group(); baseLights.name = 'msBaseLights'; scene.add(baseLights);
  baseLights.add(new THREE.HemisphereLight(0xe8f0ff, 0x3a2a22, high ? 0.55 : 0.75));
  if (!high) baseLights.add(new THREE.AmbientLight(0xffffff, 0.45));
  const key = new THREE.DirectionalLight(0xfff4e8, high ? 1.55 : 1.3); key.position.set(2.2, 3.4, 2.6); baseLights.add(key);
  const fill = new THREE.DirectionalLight(0xb8d4ff, high ? 0.55 : 0.35); fill.position.set(-2.4, 1.8, 1.4); baseLights.add(fill);
  const rim = new THREE.DirectionalLight(0xff66cc, high ? 1.1 : 0.8); rim.position.set(-1.6, 2.2, -2.4); baseLights.add(rim);
  if (high) {
    key.castShadow = true; key.shadow.mapSize.set(2048, 2048); key.shadow.camera.near = 0.3; key.shadow.camera.far = 14;
    key.shadow.camera.left = -2; key.shadow.camera.right = 2; key.shadow.camera.top = 2.6; key.shadow.camera.bottom = -0.8; key.shadow.bias = -0.00025; key.shadow.normalBias = 0.03;
    try { const pm = new THREE.PMREMGenerator(renderer); scene.environment = pm.fromScene(new RoomEnvironment(), 0.04).texture; pm.dispose(); } catch (e) { console.warn('dance env', e); }
    const ground = new THREE.Mesh(new THREE.CircleGeometry(1.6, 64), new THREE.ShadowMaterial({ opacity: 0.32 }));
    ground.rotation.x = -Math.PI / 2; ground.position.y = 0.002; ground.receiveShadow = true; scene.add(ground);
  }
  // floor ring that flashes on beats
  const ringMat = new THREE.MeshBasicMaterial({ color: 0xffb627, transparent: true, opacity: 0.5, side: THREE.DoubleSide, depthWrite: false });
  const ring = new THREE.Mesh(new THREE.RingGeometry(0.45, 0.62, phone ? 40 : 72), ringMat); ring.rotation.x = -Math.PI / 2; ring.position.y = 0.005; scene.add(ring);
  const discMat = new THREE.MeshBasicMaterial({ color: 0x220a2a, transparent: true, opacity: 0.55, depthWrite: false });
  const disc = new THREE.Mesh(new THREE.CircleGeometry(0.45, phone ? 32 : 64), discMat); disc.rotation.x = -Math.PI / 2; disc.position.y = 0.004; scene.add(disc);

  const loader = new GLTFLoader();
  loader.register((p) => new VRMLoaderPlugin(p));
  loader.register((p) => new VRMAnimationLoaderPlugin(p));

  let themeName = (opts.theme === 'cinematic' ? 'cine' : (opts.theme || 'simple'));
  if (themeName !== 'club' && themeName !== 'cine') themeName = 'simple';
  const theme = attachTheme({ THREE, scene, camera: cam, renderer, phone, high });
  let backdrop = null, qLive = 1, lowFpsN = 0, lastBeatFlag = false, visibleSince = 0;
  // smooth-20261111: perf governor. Ignores load/compile warm-up, hidden time and long gaps; steps quality down first
  // (shadows off -> lower pixel ratio -> fewer particles), and asks for a fallback only after ~8 s sustained < 20 fps at the lowest level.
  let prScale = 1, perfLvl = 0, lowSec = 0, warmUntil = (typeof performance !== 'undefined' ? performance.now() : 0) + 5000, perfLog = [];
  const PERF_LVL = [[1, 1], [0.8, 0.85], [0.6, 0.7], [0.45, 0.55]];   // [theme quality, pixel-ratio scale]
  function warmFor(ms) { const t = performance.now() + (ms || 5000); if (t > warmUntil) warmUntil = t; lowSec = 0; }
  try { document.addEventListener('visibilitychange', () => { if (!document.hidden) warmFor(3000); }); } catch (_) {}
  function perfSec(now) {
    if (fps < 20) lowSec++; else lowSec = 0;
    if (lowSec >= 3 && perfLvl < PERF_LVL.length - 1) {
      perfLvl++; lowSec = 0; const L = PERF_LVL[perfLvl]; qLive = L[0]; prScale = L[1];
      try { renderer.shadowMap.enabled = false; } catch (_) {}
      try { theme && theme.setQuality(qLive); } catch (_) {}
      try { backdrop && backdrop.setQuality(qLive); } catch (_) {}
      try { fit(); } catch (_) {}
      perfLog.push([Math.round(now), 'step', perfLvl, fps]); warmFor(2000); return;
    }
    if (lowSec >= 8 && perfLvl >= PERF_LVL.length - 1) {
      perfLog.push([Math.round(now), 'fallback', perfLvl, fps]); lowSec = 0; warmFor(5000);
      if (typeof opts.onLowFps === 'function') { try { opts.onLowFps('slow'); } catch (_) {} }
    }
  }
  createBackdrop(container, { phone }).then((b) => {
    backdrop = b; b.setTheme(themeName);
    b.setVisible(visible && themeName !== 'simple');
  }).catch((e) => console.warn('backdrop', e));
  try { theme.setTheme(themeName); } catch (e) { console.warn('theme', e); }
  if (baseLights) baseLights.visible = themeName === 'simple';
  if (ring) ring.visible = themeName === 'simple';
  if (typeof disc !== 'undefined' && disc) disc.visible = themeName === 'simple';

  const tracker = new BeatTracker(opts.audioCtx, opts.source, opts.analyser);
  const anims = {};          // id -> VRMAnimation (model independent)
  function clipUrl(c) { // adult-viz-20261111
    if (c && c.url) return c.url;
    const f = (c && c.file) || '';
    if (f.startsWith('/')) return f;
    if (c && c.adult) return '/assets/dance/adult/' + f;
    return base + f;
  }
  async function loadAnim(c) { if (!anims[c.id]) anims[c.id] = loader.loadAsync(clipUrl(c)).then((g) => g.userData.vrmAnimations[0]); return anims[c.id]; }

  let vrm = null, mixer = null, actions = {}, curClip = null, curAct = null, hipsN = null, headN = null, spineN = null, modelUrl = '';
  let nextBeat = null, lastBeatT = null, beatCount = 0, beatsInClip = 0, phraseLen = 16, hold = false, rate = 1, baseRate = 1, clipBpm = 120;
  const log = [], phaseErr = [];
  let visible = true, frameN = 0, lastT = 0, fps = 0, fpsN = 0, fpsT = 0, clipIdx = -1, err = '';

  function clipFor(c) {
    if (actions[c.id]) return actions[c.id];
    const va = anims[c.id] && anims[c.id].__v; if (!va) return null;
    const clip = createVRMAnimationClip(va, vrm);
    // keep the dancer on its spot: freeze horizontal hips travel, keep vertical bounce
    for (const tr of clip.tracks) {
      if (hipsN && tr.name === hipsN.name + '.position') { const v = tr.values, x0 = v[0], z0 = v[2]; for (let i = 0; i < v.length; i += 3) { v[i] = x0; v[i + 2] = z0; } }
    }
    const a = mixer.clipAction(clip); a.setLoop(THREE.LoopRepeat, Infinity); a.clampWhenFinished = false; actions[c.id] = a; return a;
  }
  async function primeAnims(list) { for (const c of list) { /* resfix: while the video is shown, don't compete with it for the link (one shared HTTP/2 connection on the Funnel) */ while (globalThis.__msNetHold) await new Promise((r) => setTimeout(r, 1000)); try { const va = await loadAnim(c); anims[c.id].__v = va; } catch (e) { console.warn('dance clip', c.id, e); } } }

  function fit() {
    const w = container.clientWidth || 360, h = container.clientHeight || 360;
    const pr = Math.max(0.5, Math.min(window.devicePixelRatio || 1, high ? 2 : phone ? 1 : 1.5) * prScale);
    renderer.setPixelRatio(pr); renderer.setSize(w, h, false); cam.aspect = w / Math.max(1, h);
    // frame a ~1.75 m tall dancer fully; portrait screens need more distance
    if (theme && theme.name && theme.name !== 'simple') { cam.updateProjectionMatrix(); return; }
    const fovV = cam.fov * Math.PI / 180, needH = 2.05, needW = 1.6;
    const dH = needH / 2 / Math.tan(fovV / 2), dW = needW / 2 / (Math.tan(fovV / 2) * cam.aspect);
    const d = Math.max(dH, dW) * 0.94; cam.position.set(0, 0.95, d); cam.lookAt(0, 0.9, 0); cam.updateProjectionMatrix();
  }

  let loadSeq = 0, loadAC = null, loadedUrl = '', pendUrl = '', pendP = null;
  async function setModel(url) {
    if (url === pendUrl && pendP) return pendP;                       // same model already loading: join it
    if (url === loadedUrl && vrm) { loadSeq++; if (loadAC) try { loadAC.abort(); } catch (_) {} loadAC = null; pendUrl = ''; pendP = null; return { stale: false }; }
    const seq = ++loadSeq; if (loadAC) try { loadAC.abort(); } catch (_) {}
    let bytesP;
    if (pre && pre.url === url) {      // adopt the download started in createDance; its progress counts only while current
      const P = pre; pre = null; loadAC = P.ac; bytesP = P.p; P.onp = (...a) => { if (seq === loadSeq && opts.onProgress) opts.onProgress(...a); };
    } else {
      if (pre) { pre.onp = () => {}; try { pre.ac.abort(); } catch (_) {} pre = null; }
      loadAC = new AbortController();
      bytesP = fetchModelBytes(url, { signal: loadAC.signal, onProgress: (...a) => { if (seq === loadSeq && opts.onProgress) opts.onProgress(...a); } });
    }
    pendUrl = url;
    const run = (async () => {
      const bytes = await bytesP; if (seq !== loadSeq) return { stale: true };
      const g = await loader.parseAsync(bytes, url.replace(/[^/]*$/, '')); if (seq !== loadSeq) return { stale: true };
      return { g };
    })();
    pendP = run.then(async (res) => { if (res.stale) return res; await install(res.g, url); return { stale: false }; })
      .finally(() => { if (seq === loadSeq) { pendUrl = ''; pendP = null; } });
    return pendP;
  }
  async function install(g, url) {
    loadedUrl = modelUrl = url;
    const v = g.userData.vrm; if (!v) throw new Error('not a VRM');
    try { VRMUtils.removeUnnecessaryVertices(g.scene); } catch (_) {}
    try { (VRMUtils.combineSkeletons || VRMUtils.removeUnnecessaryJoints)(g.scene); } catch (_) {}
    try { VRMUtils.rotateVRM0(v); } catch (_) {}
    let ani = 1; try { ani = high ? Math.min(16, renderer.capabilities.getMaxAnisotropy()) : 1; } catch (_) {}
    v.scene.traverse((o) => { o.frustumCulled = false; if (high && o.isMesh) { o.castShadow = true; }
      for (const m of [].concat(o.material || [])) { try { for (const t of ['map', 'normalMap', 'emissiveMap', 'shadeMultiplyTexture']) if (m[t]) { m[t].anisotropy = ani; m[t].needsUpdate = true; } } catch (_) {} } });
    if (vrm) { scene.remove(vrm.scene); try { VRMUtils.deepDispose(vrm.scene); } catch (_) {} }
    vrm = v; scene.add(vrm.scene);
    mixer = new THREE.AnimationMixer(vrm.scene); actions = {}; curAct = null; curClip = null; add.k = 0;
    const H = vrm.humanoid; hipsN = H.getNormalizedBoneNode('hips'); headN = H.getNormalizedBoneNode('head'); spineN = H.getNormalizedBoneNode('spine');
    fit(); warmFor(5000);   // smooth-20261111: shader compile + first frames of a new model are not measured
    startClip(pickNext(true), 0);
  }


  function clipRateFor(c, bpm) {
    // choose the clip tempo octave that is nearest to the song tempo
    const cands = [c.bpm, ...(c.alts || [])].filter(Boolean);
    let best = c.bpm, bd = 9;
    for (const b of cands) { const d = Math.abs(Math.log2(bpm / b)); if (d < bd) { bd = d; best = b; } }
    return best;
  }
  function pickNext(first) {
    const C = manifest.clips.filter((c) => anims[c.id] && anims[c.id].__v);
    if (!C.length) return null;
    const bpm = tracker.bpm || 110, en = tracker.energy;
    // dancefix: mood-aware + variety. Romantic songs prefer the slow sway / salsa / lambada / graceful clips;
    // clips used recently are penalised and the random share is larger, so the same moves don't repeat every song.
    const mood = opts.mood ? (opts.mood() || '') : '', romantic = mood === 'romantic';
    const want = romantic ? 2 : mood === 'sad' || mood === 'chill' || mood === 'devotional' ? 2 : mood === 'party' ? 5 : en > 0.42 ? 5 : en > 0.3 ? 4 : 3;
    const scored = C.filter((c) => c !== curClip).map((c) => {
      const cb = clipRateFor(c, bpm), r = bpm / cb;
      const tempoFit = Math.abs(Math.log2(r)), enFit = Math.abs(c.energy - want) / 4;
      const ri = recent.lastIndexOf(c.id), rec = ri < 0 ? 0 : 0.6 + 0.25 * (ri - recent.length + 6);
      const cm = clipMoods(c), moodFit = !MOODS_OK.includes(mood) ? 0 : cm.includes(mood) ? -1.2 : romantic ? (c.energy >= 5 ? 0.8 : 0.3) : 0.35;
      return { c, s: tempoFit * 1.6 + enFit + Math.max(0, rec) + moodFit + Math.random() * 0.9 };
    }).sort((a, b) => a.s - b.s);
    return (scored[0] || { c: C[0] }).c;
  }
  function startClip(c, fade) {
    if (!c || !mixer) return; const a = clipFor(c); if (!a) return;
    const bpm = tracker.bpm || 110; clipBpm = clipRateFor(c, bpm);
    const cbeat = 60 / clipBpm, dur = a.getClip().duration;
    // start on one of the clip's own beats, leaving room for a phrase before the clip loops
    const usable = Math.max(1, Math.floor((dur - c.firstBeat - phraseLen * cbeat) / cbeat));
    const n = usable > 1 ? Math.floor(Math.random() * usable) : 0;
    a.reset(); a.time = c.firstBeat + n * cbeat; a.enabled = true; a.setEffectiveWeight(1);
    baseRate = rate = clamp(bpm / clipBpm, 0.55, 1.8); a.setEffectiveTimeScale(rate); a.play();
    if (curAct && curAct !== a && fade > 0) curAct.crossFadeTo(a, fade, false); else if (curAct && curAct !== a) curAct.stop();
    curAct = a; curClip = c; beatsInClip = 0; clipIdx++; lastCum = null; recent.push(c.id); if (recent.length > 6) recent.shift();
    log.push({ at: +tracker.now().toFixed(2), clip: c.id, songBpm: +(tracker.bpm || 0).toFixed(1), clipBpm, rate: +rate.toFixed(3) }); if (log.length > 40) log.shift();
    if (opts.onClip) try { opts.onClip(c); } catch (_) {}
  }

  let cumClipBeats = 0, lastCum = null; const perBeat = []; const recent = [];
  function onBeat(bi, late) {
    if (!curAct || !curClip) return;
    beatsInClip++;
    if (lastCum !== null) { perBeat.push(cumClipBeats - lastCum); if (perBeat.length > 16) perBeat.shift(); } lastCum = cumClipBeats;
    // phase lock: where was the clip on its own beat grid at the exact beat instant? (late = seconds since the beat)
    const cbeat = 60 / clipBpm; let ph = ((curAct.time - late * rate - curClip.firstBeat) / cbeat) % 1; if (ph < 0) ph += 1;
    const e = ph > 0.5 ? ph - 1 : ph;                         // -0.5..0.5 beats (positive = clip ahead)
    phaseErr.push(e); if (phaseErr.length > 64) phaseErr.shift();
    baseRate = clamp((tracker.bpm || 110) / clipBpm, 0.55, 1.8);
    rate = clamp(baseRate * (1 - clamp(0.4 * e, -0.15, 0.15)), 0.5, 2);
    curAct.setEffectiveTimeScale(rate);
    ringMat.opacity = 0.95;
    if (!hold && beatsInClip >= phraseLen && bi % 4 === 0) {
      const nx = pickNext(false); if (nx && nx !== curClip) startClip(nx, (60 / (tracker.bpm || 110)));
    }
  }

  let raf = 0, idleW = 0; const add = { k: 0 };
  function tick(now) {
    raf = 0; if (!visible) return;
    const dtR = lastT ? (now - lastT) / 1000 : 0.016;
    if (phone && lastT && dtR < 1 / 34) { raf = requestAnimationFrame(tick); return; }   // ~30 fps cap on phones
    lastT = now; const dt = Math.min(0.1, dtR);
    if (now < warmUntil || dtR > 0.25 || (typeof document !== 'undefined' && document.hidden)) { fpsN = 0; fpsT = now; }   // smooth-20261111
    else { fpsN++; if (now - fpsT >= 1000) { fps = Math.round(fpsN * 1000 / (now - fpsT)); fpsN = 0; fpsT = now; perfSec(now); } }
    const paused = opts.isPaused ? opts.isPaused() : false;
    const t = tracker.now() - tracker.latency();   // what is being heard right now
    const live = !paused && tracker.locked && tracker.energy > 0.02;
    let bp = null;
    if (live) {
      if (nextBeat == null || t - nextBeat > tracker.period * 1.5) nextBeat = tracker.nextBeatAfter(t);
      if (t >= nextBeat) { const late = t - nextBeat; lastBeatT = nextBeat; beatCount++; lastBeatFlag = true; onBeat(beatCount, late); nextBeat = tracker.nextBeatAfter(nextBeat + tracker.period * 0.5); }
      if (lastBeatT != null) bp = beatCount + clamp((t - lastBeatT) / tracker.period, 0, 1);
    } else nextBeat = null;
    if (mixer) {
      // idle: slow everything down smoothly when paused/silent
      idleW += ((live ? 0 : 1) - idleW) * Math.min(1, dt * 3);
      if (curAct) { const ts = rate * (1 - 0.85 * idleW); curAct.setEffectiveTimeScale(ts); cumClipBeats += dt * ts * clipBpm / 60; }
      // undo last frame's additive groove (bones without a track in the clip would otherwise accumulate it)
      if (add.k && hipsN) { hipsN.position.y += 0.025 * add.k; if (headN) headN.rotation.x -= 0.07 * add.k; if (spineN) spineN.rotation.x -= 0.03 * add.k; add.k = 0; }
      mixer.update(dt);
      if (bp != null && hipsN && !opts.reducedMotion) {
        const ph = bp - Math.floor(bp), d = 0.5 + 0.5 * Math.cos(ph * TAU), amp = (1 - idleW) * clamp(tracker.energy * 2.2, 0.25, 1);
        add.k = amp * d;
        hipsN.position.y -= 0.025 * add.k;
        if (headN) headN.rotation.x += 0.07 * add.k;
        if (spineN) spineN.rotation.x += 0.03 * add.k;
      }
      try { vrm.update(dt); } catch (_) {}
    }
    ringMat.opacity = Math.max(0.25, ringMat.opacity - dt * 2.2); ring.scale.setScalar(1 + (ringMat.opacity - 0.25) * 0.25);
    if (opts.colors && (frameN++ % 60 === 0)) { try { const c = opts.colors(); ringMat.color.set(c[0]); rim.color.set(c[1] || c[0]); if (theme) theme.setColors(c[0], c[1] || c[0]); if (backdrop) backdrop.setColors(c[0], c[1] || c[0]); } catch (_) {} }
    try {
      let bass = 0, mid = 0, highB = 0; const cur = tracker.cur, n = tracker.n || 0;
      if (cur && n) {
        const bH = Math.min(8, n), mH = Math.min(40, n);
        for (let i = 1; i < bH; i++) bass += cur[i];
        for (let i = bH; i < mH; i++) mid += cur[i];
        for (let i = mH; i < Math.min(120, n); i++) highB += cur[i];
        bass /= Math.max(1, bH - 1) * 255; mid /= Math.max(1, mH - bH) * 255; highB /= Math.max(1, Math.min(120, n) - mH) * 255;
      }
      const feat = { t: now / 1000, dt, bass, mid, high: highB, energy: tracker.energy, beat: lastBeatFlag, paused, bins: cur, colors: opts.colors && opts.colors() };
      if (theme && themeName !== 'simple') theme.update(feat);
      if (backdrop) backdrop.frame(feat);
      lastBeatFlag = false;
    } catch (e) { /* visuals must never stop audio */ }
    // smooth-20261111: old per-frame low-fps counter removed (it stepped down 3 levels and fell back within one bad second)
    if (!lost) renderer.render(scene, cam);
    raf = requestAnimationFrame(tick);
  }

  const ro = new ResizeObserver(() => fit()); ro.observe(container);
  // clips: two first (fast start), the rest in the background
  // dancefix: shuffled start (different first moves each session); romantic songs prime romantic clips first
  const shuf = manifest.clips.slice().sort(() => Math.random() - 0.5);
  { const m0 = opts.mood ? opts.mood() : ''; if (m0) shuf.sort((a, b) => (clipMoods(b).includes(m0) ? 1 : 0) - (clipMoods(a).includes(m0) ? 1 : 0)); }
  await primeAnims(shuf.slice(0, 3));
  if (vrm && !curAct) startClip(pickNext(true), 0);
  primeAnims(shuf.slice(3)).catch(() => {});

  const api = {
    manifest, tracker,
    setModel: (u) => setModel(u).catch((e) => { if (e && e.name === 'AbortError') return { stale: true }; err = String(e && e.message || e); throw e; }),
    loading: () => !!pendP,
    setVisible(v) { const was = visible; visible = !!v; cvs.style.display = v ? '' : 'none'; if (v && !was) { visibleSince = (typeof performance!=='undefined'?performance.now():0); warmFor(5000); tracker.run(() => (opts.isPaused ? opts.isPaused() : false)); } if (!v && was) tracker.stop(); try { theme && theme.setVisible(!!v); } catch (_) {} try { backdrop && backdrop.setVisible(!!v && themeName !== 'simple'); } catch (_) {} if (v && !raf) { lastT = 0; raf = requestAnimationFrame(tick); } },
    async setTheme(n) {
      themeName = (n === 'cinematic' || n === 'cine') ? 'cine' : (n === 'club' ? 'club' : 'simple');
      warmFor(5000); try { await theme.setTheme(themeName); } catch (e) { console.warn('setTheme', e); } warmFor(4000);
      try { if (backdrop) { backdrop.setTheme(themeName); backdrop.setVisible(visible && themeName !== 'simple'); } } catch (_) {}
      if (baseLights) baseLights.visible = themeName === 'simple';
      if (ring) ring.visible = themeName === 'simple';
      if (typeof disc !== 'undefined' && disc) disc.visible = themeName === 'simple';
      try { fit(); } catch (_) {}
    },
    setHold(h) { hold = !!h; },
    newTrack() { tracker.reset(); nextBeat = null; lastBeatT = null; }, next() { const n = pickNext(false); if (n) startClip(n, 0.4); },
    stats() {
      const pe = phaseErr.slice(-16); const mabs = pe.length ? pe.reduce((s, x) => s + Math.abs(x), 0) / pe.length : null;
      return { bpm: tracker.bpm ? +tracker.bpm.toFixed(1) : 0, conf: +tracker.conf.toFixed(2), locked: tracker.locked, energy: +tracker.energy.toFixed(3),
        clip: curClip && curClip.id, clipLabel: curClip && curClip.label, clipBpm, rate: +rate.toFixed(3),
        animTempo: curClip ? +(clipBpm * rate).toFixed(1) : 0,
        animBeatsPerSongBeat: perBeat.length ? +(perBeat.slice(-8).reduce((a, b) => a + b, 0) / Math.min(8, perBeat.length)).toFixed(3) : null,
        animTempoMeasured: perBeat.length && tracker.bpm ? +(tracker.bpm * perBeat.slice(-8).reduce((a, b) => a + b, 0) / Math.min(8, perBeat.length)).toFixed(1) : null, phaseErrBeats: mabs == null ? null : +mabs.toFixed(3),
        phaseErrMs: mabs == null || !tracker.bpm ? null : Math.round(mabs * 60000 / tracker.bpm), clipsLoaded: Object.keys(anims).filter((k) => anims[k].__v).length,
        clipsSwitched: clipIdx, mood: opts.mood ? opts.mood() : '', clipsTotal: manifest.clips.length, recent: recent.slice(), beats: beatCount, tempoSwitches: tracker.switches || 0, high, fps, model: modelUrl.split('/').pop(), err, ownAnalyser: !!tracker._own, theme: themeName, gpu: backdrop ? backdrop.backend() : 'pending', quality: +qLive.toFixed(2), perfLvl, prScale, lowSec, warm: Math.max(0, Math.round(warmUntil - performance.now())), perfLog: perfLog.slice(-12) };
    },
    log: () => ({ clips: log.slice(), bpm: tracker.history.slice(), phaseErr: phaseErr.slice() }),
    dispose() { visible = false; loadSeq++; if (loadAC) try { loadAC.abort(); } catch (_) {} if (pre) try { pre.ac.abort(); } catch (_) {} tracker.stop(); cancelAnimationFrame(raf); ro.disconnect(); try { theme && theme.dispose(); } catch (_) {} try { backdrop && backdrop.dispose(); } catch (_) {} try { if (vrm) VRMUtils.deepDispose(vrm.scene); } catch (_) {} renderer.dispose(); cvs.remove(); }
  };
  tracker.run(() => (opts.isPaused ? opts.isPaused() : false));
  raf = requestAnimationFrame(tick);
  return api;
}
