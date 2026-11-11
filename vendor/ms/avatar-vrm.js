/* Music Stream — VRM dancers for MSViz + MSGame (ms-v77).
 * Stack: three.js MIT, @pixiv/three-vrm MIT. Dance = original procedural choreography (vendor/ms/vrm-dance.js), no motion files.
 * Models: 9 VRoid sample avatars (7 CC0 + AvatarSample A/B under VRoid sample terms) — see docs/GAME_CREDITS.md.
 * Runa Inoue is NOT registered: its embedded VRM meta (allowedUserName=OnlyAuthor) conflicts with the MIT GitHub release.
 * Lazy: three/VRM fetched only when a VRM avatar is picked. */
(function () {
  'use strict';
  if (!window.MSViz || !window.MSViz.registerAvatar) return;
  if (window.__msAvatarVrm) return; window.__msAvatarVrm = 1;

  var MODELS = [
    ['vrm_darkness_shibu', 'Darkness Shibu (VRM)', 'Darkness_Shibu.vrm'],
    ['vrm_vivi', 'Vivi (VRM)', 'Vivi.vrm'],
    ['vrm_sendagaya_shibu', 'Sendagaya Shibu (VRM)', 'Sendagaya_Shibu.vrm'],
    ['vrm_victoria', 'Victoria Rubin (VRM)', 'Victoria_Rubin.vrm'],
    ['vrm_vita', 'Vita (VRM)', 'Vita.vrm'],
    ['vrm_avatar_a', 'AvatarSample A (VRM)', 'AvatarSample_A.vrm'],
    ['vrm_avatar_b', 'AvatarSample B (VRM)', 'AvatarSample_B.vrm'],
    ['vrm_hair_f', 'HairSample F (VRM)', 'HairSample_Female.vrm'],
    ['vrm_sendagaya_shino', 'Sendagaya Shino (VRM)', 'Sendagaya_Shino.vrm']
  ];
  var BASE = '/assets/chars/vrm/';
  var mods = null;

  function ensureImportMap() {
    if (document.getElementById('ms-three-importmap')) return;
    var s = document.createElement('script');
    s.type = 'importmap'; s.id = 'ms-three-importmap';
    s.textContent = JSON.stringify({
      imports: {
        three: '/vendor/three/three.module.js',
        'three/addons/': '/vendor/three/examples/jsm/',
        '@pixiv/three-vrm': '/vendor/three-vrm/three-vrm.module.js'
      }
    });
    document.head.prepend(s);
  }

  function loadMods() {
    if (mods) return mods;
    ensureImportMap();
    mods = import('/vendor/ms/avatar-vrm-engine.js?v=77');
    return mods;
  }

  function factory(file, label) {
    return function (host) {
      return loadMods().then(function (E) {
        return E.createOverlay(host, BASE + file, {
          phone: !!(host && host.phone),
          reducedMotion: !!(host && host.reducedMotion),
          label: label
        });
      });
    };
  }

  MODELS.forEach(function (m) {
    try { window.MSViz.registerAvatar(m[0], { label: m[1], factory: factory(m[2], m[1]) }); } catch (e) {}
  });

  /* Also expose for MSGame character registration once engine loads (lazy) */
  window.MSVrmAvatars = {
    models: MODELS.map(function (m) { return { id: m[0], label: m[1], file: m[2] }; }),
    preload: loadMods
  };
})();
