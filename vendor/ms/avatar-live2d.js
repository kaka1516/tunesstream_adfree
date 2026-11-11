/* Music Stream Stage — Live2D avatars for the MSViz avatar slot. v3
 * Hiyori·Haru·Mao·Rice + Mao Pro·Shizuku·Koharu·Cyannyan·Arch-chan + Haru 27-motion aliases.
 * Thin bridge over /assets/chars/live2d.js. avatar-hiyori.js is a copy of this file. */
(function () {
  'use strict';
  if (!window.MSViz || !window.MSViz.registerAvatar) return;
  if (window.__msAvatarLive2D && window.__msAvatarLive2D >= 4) return; window.__msAvatarLive2D = 4;
  var SRC = '/assets/chars/live2d.js?v=8';
  var IDS = [
    ['hiyori', 'Hiyori (Live2D)'], ['haru', 'Haru (Live2D)'], ['mao', 'Mao (Live2D)'], ['rice', 'Rice (Live2D)'],
    ['mao_pro', 'Mao Pro (Live2D)'], ['shizuku', 'Shizuku (Live2D)'], ['koharu', 'Koharu (Live2D)'],
    ['cyannyan', 'Cyannyan (Live2D)'], ['archchan', 'Arch-chan (Live2D)']
  ];
  // Haru's 27 authored motions as separate picker entries (idle + m01..m26)
  var HARU_MOTIONS = ['idle'].concat(Array.from({ length: 26 }, function (_, i) {
    return 'm' + String(i + 1).padStart(2, '0');
  }));
  var loading = null;
  function loadRuntime() {
    if (window.MSGameLive2D && window.MSGameLive2D.adapters && window.MSGameLive2D.v >= 5) return Promise.resolve(window.MSGameLive2D);
    if (loading) return loading;
    loading = new Promise(function (res, rej) {
      var s = document.createElement('script'); s.src = SRC; s.async = true;
      s.onload = function () { window.MSGameLive2D && window.MSGameLive2D.adapters ? res(window.MSGameLive2D) : rej(new Error('live2d adapters missing')); };
      s.onerror = function () { loading = null; rej(new Error('could not load live2d runtime')); };
      document.head.appendChild(s);
    });
    return loading;
  }
  var SEQ = {
    energetic: ['left', 'right', 'up', 'right', 'left', 'down', 'up', 'jump'],
    devotional: ['up', 'idle', 'up', 'idle'],
    romantic: ['left', 'idle', 'right', 'idle'],
    sad: ['idle', 'down', 'idle', 'idle'],
    calm: ['idle', 'left', 'idle', 'right']
  };
  function wrap(inst, host, forceMotion) {
    var S = { pose: 'idle', prev: 'idle', at: performance.now(), hold: 0, f: null, pal: null, facing: 1, i: 0, lastCheek: 0, motion: forceMotion || null };
    function set(p, holdMs) { if (p === S.pose && !holdMs) return; S.prev = S.pose; S.pose = p; S.at = performance.now(); S.hold = holdMs ? S.at + holdMs : 0; try { inst.setPose(p, {}); } catch (e) {} }
    if (forceMotion) {
      try { inst.playMotion && inst.playMotion(forceMotion, 0); } catch (e) {}
      // re-trigger periodically so the motion loops even if Cubism ends it
      S.motionTimer = setInterval(function () {
        try { if (inst.model) inst.playMotion(forceMotion, 0); } catch (e) {}
      }, 4500);
    }
    function playHaruMotion(name) {
      var g = String(name || '').replace(/^haru_g_/, '').replace(/^haru_/, '');
      if (g === 'haru' || !g) g = 'idle';
      S.motion = g;
      try { return !!inst.playMotion(g, 0); } catch (e) { return false; }
    }
    window.__msPlayHaruMotion = playHaruMotion;
    return {
      mode: '2d',
      _playHaruMotion: playHaruMotion,
      _live2dCache: function () { return inst.cv || null; },
      update: function (f) {
        S.f = f; var now = performance.now();
        if (f.pointer && f.pointer.active) S.facing = f.pointer.x < f.box.x - .05 ? -1 : f.pointer.x > f.box.x + .05 ? 1 : S.facing; else S.facing = 1;
        if (f.drop && !f.reducedMotion) { try { inst.react('drop'); } catch (e) {} set('jump', 600); return; }
        if (S.hold && now < S.hold) return;
        // When a forced Haru motion is active, keep idle pose params and let Cubism drive the rest
        if (S.motion) { if (S.pose !== 'idle') set('idle'); return; }
        if (f.idle && f.conf < .3 && !f.beat) { if (S.pose !== 'idle' && now - S.at > 600) set('idle'); return; }
        if (!f.beat) return;
        if (f.downbeat && f.strength > .8 && now - S.lastCheek > 7000 && !f.reducedMotion) { S.lastCheek = now; try { inst.play(['wink', 'kiss', 'flip', 'tease'][(f.bar || 0) % 4]); } catch (e) {} }
        var mood = f.mood in SEQ ? f.mood : 'calm', seq = SEQ[mood];
        var every = mood === 'energetic' ? (f.intensity < .6 ? 2 : 1) : 2;
        if (f.beatN % every) return;
        S.i = (S.i + 1) % seq.length;
        var p = seq[S.i];
        if (mood === 'energetic' && f.energy > .8 && f.high > .6 && !(S.i % 4)) p = 'run';
        if (f.reducedMotion && (p === 'jump' || p === 'run')) p = 'up';
        set(p);
      },
      draw: function (g, w, h, b) {
        var f = S.f || {}, now = performance.now(), poseT = now - S.at;
        var size = b.h / 1.38;
        inst.draw(g, { x: b.x + b.w / 2, y: b.y + b.h, size: size, pose: S.pose, prevPose: S.prev, poseT: poseT, blend: Math.min(1, poseT / 140),
          t: now, beat: f.beatPhase || 0, facing: S.facing, role: 'lead', variant: '', color: (S.pal && S.pal.glow) || '#ffd27a',
          dpr: (host && host.dpr) || 1, colors: S.pal || {}, energy: f.bass || 0, lowFx: (f.tier || 0) >= 3 });
      },
      trigger: function (kind, info) {
        if (kind === 'special') { try { inst.play('drop'); } catch (e) {} set(S.f && S.f.reducedMotion ? 'up' : 'jump', 700); return; }
        var p = S.f && S.f.pointer, part = 'body';
        if (p && S.f.box) part = p.y < S.f.box.y - S.f.box.h * .73 ? 'head' : 'body';
        try { inst.poke(part); } catch (e) {} if (part === 'body') set('up', 450);
      },
      hitTest: null,
      setPalette: function (p) { S.pal = p; },
      dispose: function () {
        if (S.motionTimer) try { clearInterval(S.motionTimer); } catch (e) {}
        try { inst.dispose(); } catch (e) {}
      }
    };
  }
  function factory(id, forceMotion) {
    return function (host) {
      return loadRuntime().then(function (L) {
        var modelId = id.indexOf('haru') === 0 ? 'haru' : id;
        var A = L.adapters[modelId]; if (!A) throw new Error('no live2d adapter ' + modelId);
        var inst = A.create({ role: 'lead' });
        return Promise.resolve(inst.loading).then(function () {
          if (!inst.model) throw new Error(inst.err || 'live2d model failed');
          return wrap(inst, host, forceMotion || null);
        });
      });
    };
  }
  IDS.forEach(function (m) { try { window.MSViz.registerAvatar(m[0], { label: m[1], factory: factory(m[0]) }); } catch (e) {} });
  HARU_MOTIONS.forEach(function (g) {
    var id = 'haru_' + g;
    var label = 'Haru · ' + g;
    try { window.MSViz.registerAvatar(id, { label: label, factory: factory('haru', g) }); } catch (e) {}
  });
})();
