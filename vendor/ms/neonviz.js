/* Music Stream — Neon analyser visuals (ms-v75): "Neon Bars", "Spectrum" (circular), "Glow Waves".
 *
 * PORTED CODE (JavaScript port, adapted): Wave.js by Austin Michaud — https://github.com/foobar404/wave.js
 *   commit 7ed12c4fc32c3174e08e7622e34c47282919a888 (main, fetched 2026-11-08), MIT License (full text below and in
 *   /vendor/ms/LICENSE-wave.js.txt). Ported pieces: src/util/AudioData.ts (setFrequencyBand, scaleData),
 *   src/animations/Lines.ts (bottom bars, mirroredX), src/animations/Shine.ts (circular spokes, rotate/offset),
 *   src/animations/Wave.ts (center polygon, mirroredY), src/util/Shapes.ts (line/polygon + glow = shadowBlur,
 *   gradient fill). Adaptations: plain JS, gradient colours from the app skin, per-frame peak smoothing,
 *   phone/reduced-motion budgets.
 * ORIGINAL CODE (not from Wave.js): the spark particles riding the Glow Waves crest, the smoothing/budget layer.
 * Input: the app's real Web Audio AnalyserNode data (getByteFrequencyData / time domain) passed in each frame;
 * nothing here synthesises a music response.
 *
 * MIT License — Copyright (c) 2023 Austin Michaud λ
 * Permission is hereby granted, free of charge, to any person obtaining a copy of this software and associated
 * documentation files (the "Software"), to deal in the Software without restriction, including without limitation
 * the rights to use, copy, modify, merge, publish, distribute, sublicense, and/or sell copies of the Software, and to
 * permit persons to whom the Software is furnished to do so, subject to the following conditions:
 * The above copyright notice and this permission notice shall be included in all copies or substantial portions of
 * the Software.
 * THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE
 * WARRANTIES OF MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE AUTHORS OR
 * COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR
 * OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE SOFTWARE.
 */
(function () {
  'use strict';
  if (window.MSNeon) return;
  /* --- Wave.js AudioData port --- */
  function setFrequencyBand(data, band) {
    var baseLength = Math.floor(data.length * .0625), lowsLength = Math.floor(data.length * .0625), midsLength = Math.floor(data.length * .375);
    if (band === 'base') return data.slice(0, baseLength);
    if (band === 'lows') return data.slice(baseLength + 1, baseLength + lowsLength);
    if (band === 'mids') return data.slice(baseLength + lowsLength + 1, baseLength + lowsLength + midsLength);
    return data.slice(baseLength + lowsLength + midsLength + 1);
  }
  function scaleData(data, maxSize) { // Wave.js scales only when maxSize < 255; we always scale to the canvas size (adaptation)
    var out = new Float32Array(data.length);
    for (var i = 0; i < data.length; i++) out[i] = maxSize * (Math.round((data[i] / 255) * 100) / 100);
    return out;
  }
  function mirrorX(d) { var n = 1, h = Math.ceil(d.length / 2); for (var i = h; i < d.length; i++) { d[i] = d[h - n]; n++; } return d; }
  /* --- Wave.js Shapes port: gradient + glow --- */
  function makeGradient(g, w, h, colors, rotate) {
    var sx = 0, sy = h / 2, ex = w, ey = h / 2;
    if (rotate) { var a = rotate * Math.PI / 180, ox = w / 2, oy = h / 2, rp = function (x, y) { return [Math.cos(a) * (x - ox) - Math.sin(a) * (y - oy) + ox, Math.sin(a) * (x - ox) + Math.cos(a) * (y - oy) + oy]; };
      var s = rp(sx, sy), e = rp(ex, ey); sx = s[0]; sy = s[1]; ex = e[0]; ey = e[1]; }
    var gr = g.createLinearGradient(sx, sy, ex, ey); colors.forEach(function (c, i) { gr.addColorStop((1 / colors.length) * i, c); }); return gr;
  }
  function style(g, o) { g.lineWidth = o.lineWidth || 1; g.shadowColor = o.glowColor || 'rgba(0,0,0,0)'; g.shadowBlur = o.glow || 0; g.shadowOffsetX = 0; g.shadowOffsetY = 0; g.lineCap = o.cap || 'butt'; }

  function create(opts) {
    opts = opts || {};
    var phone = !!opts.phone, S = { peaks: null, sm: null, rot: 0, sparks: [], frame: 0 };
    function smooth(arr, rm) { // original: attack fast, release slow (stops jitter); heavier in reduced-motion
      if (!S.sm || S.sm.length !== arr.length) S.sm = new Float32Array(arr.length);
      var up = rm ? .25 : .6, down = rm ? .06 : .18;
      for (var i = 0; i < arr.length; i++) { var v = arr[i], c = S.sm[i]; S.sm[i] = c + (v - c) * (v > c ? up : down); }
      return S.sm;
    }
    /* Lines.ts port (bottom, mirroredX) + neon glow */
    function bars(g, w, h, dpr, freq, C, rm) {
      var count = phone ? 32 : 64, d = setFrequencyBand(freq, 'mids'); d = scaleData(d, Math.min(w, h) * .9); d = mirrorX(d); d = smooth(d, rm);
      style(g, { lineWidth: Math.max(2, (w / count) * .55), glow: (phone ? 8 : 18) * dpr * (rm ? .5 : 1), glowColor: C[0], cap: 'round' });
      g.strokeStyle = makeGradient(g, w, h, C, 90);
      var nz = 0;
      for (var i = 1; i <= count; i++) {
        var v = d[Math.floor(d.length / count) * i] || 0; if (v > 1) nz++;
        var x = (w / (count + 1)) * i; g.beginPath(); g.moveTo(x, h); g.lineTo(x, h - v); g.stroke();
      }
      return nz;
    }
    /* Shine.ts port (circular spokes, rotate, offset) */
    function spectrum(g, w, h, dpr, freq, C, rm, t) {
      var count = phone ? 48 : 96, diameter = Math.min(w, h) / 3, d = setFrequencyBand(freq, 'mids'); d = scaleData(d, Math.min(w, h) * .5); d = smooth(d, rm);
      if (!rm) S.rot = (S.rot + .15) % 360;
      var cx = w / 2, cy = h / 2, deg = 360 / count, nz = 0;
      style(g, { lineWidth: Math.max(2, 3 * dpr), glow: (phone ? 8 : 16) * dpr * (rm ? .5 : 1), glowColor: C[1] || C[0], cap: 'round' });
      g.strokeStyle = makeGradient(g, w, h, C, S.rot);
      for (var i = 0; i < count; i++) {
        var v = d[Math.floor(d.length / count) * i] || 0; if (v > 1) nz++;
        var r = (deg * i + S.rot) * Math.PI / 180, d1 = diameter - v / 2, d2 = diameter + v;
        g.beginPath(); g.moveTo((d1 / 2) * Math.cos(r) + cx, (d1 / 2) * Math.sin(r) + cy); g.lineTo((d2 / 2) * Math.cos(r) + cx, (d2 / 2) * Math.sin(r) + cy); g.stroke();
      }
      return nz;
    }
    /* Wave.ts port (center polygon, mirroredY) + original crest sparks */
    function waves(g, w, h, dpr, freq, C, rm) {
      var count = phone ? 32 : 64, d = setFrequencyBand(freq, 'mids'); d = scaleData(d, Math.min(w, h) * .42); d = mirrorX(d); d = smooth(d, rm);
      var nz = 0, pts = [];
      for (var i = 0; i <= count; i++) { var v = d[Math.floor(d.length / count) * i] || 0; if (v > 1) nz++; pts.push([Math.floor(w / count) * i, v]); }
      style(g, { lineWidth: 2 * dpr, glow: (phone ? 10 : 22) * dpr * (rm ? .5 : 1), glowColor: C[0] });
      var fill = makeGradient(g, w, h, C, 0);
      [-1, 1].forEach(function (sgn) {
        g.beginPath(); g.moveTo(0, h / 2); pts.forEach(function (p) { g.lineTo(p[0], h / 2 + sgn * p[1]); }); g.lineTo(w, h / 2); g.closePath();
        g.globalAlpha = .35; g.fillStyle = fill; g.fill(); g.globalAlpha = 1; g.strokeStyle = fill; g.stroke();
      });
      // original: sparks spawn on loud crest points, drift and fade (none in reduced-motion)
      if (!rm) {
        var cap = phone ? 60 : 220;
        for (var k = 0; k < pts.length && S.sparks.length < cap; k += 2) { var p = pts[k]; if (p[1] > h * .12 && Math.random() < .25) S.sparks.push({ x: p[0], y: h / 2 - p[1], vx: (Math.random() - .5) * .6 * dpr, vy: -(.4 + Math.random()) * dpr, a: 1, s: (1 + Math.random() * 2) * dpr }); }
        g.shadowBlur = phone ? 4 * dpr : 10 * dpr; g.shadowColor = C[1] || C[0]; g.fillStyle = C[1] || C[0];
        for (var j = S.sparks.length - 1; j >= 0; j--) { var q = S.sparks[j]; q.x += q.vx; q.y += q.vy; q.a -= .02; if (q.a <= 0) { S.sparks.splice(j, 1); continue; } g.globalAlpha = q.a; g.beginPath(); g.arc(q.x, q.y, q.s, 0, 6.2832); g.fill(); }
        g.globalAlpha = 1;
      } else S.sparks.length = 0;
      return nz;
    }
    return {
      /* freq: Uint8Array from AnalyserNode.getByteFrequencyData (real audio). returns non-zero bin count drawn, or -1 if skipped */
      draw: function (g, w, h, dpr, t, freq, colors, kind, rm) {
        S.frame++;
        if (phone && (S.frame & 1)) return -1; // phone: ~30 fps (previous frame stays on the canvas)
        var C = (colors && colors.length ? colors : ['#00e5ff', '#ff2bd6']).slice(0, 3);
        g.save(); g.globalCompositeOperation = 'source-over'; g.shadowBlur = 0; g.fillStyle = '#05050a'; g.fillRect(0, 0, w, h);
        g.globalCompositeOperation = 'lighter';
        var nz = kind === 'spectrum' ? spectrum(g, w, h, dpr, freq, C, rm, t) : kind === 'glow' ? waves(g, w, h, dpr, freq, C, rm) : bars(g, w, h, dpr, freq, C, rm);
        g.restore(); return nz;
      },
      dispose: function () { S.sparks.length = 0; S.sm = null; S.peaks = null; },
      stats: function () { return { sparks: S.sparks.length, phone: phone }; }
    };
  }
  window.MSNeon = { create: create, version: 'neon r1 (Wave.js 7ed12c4 port)', kinds: ['neon', 'spectrum', 'glow'] };
})();
