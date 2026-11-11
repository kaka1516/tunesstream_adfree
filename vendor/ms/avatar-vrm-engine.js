/* Music Stream VRM stage engine (ms-v77).
 * Stack: three.js (MIT), @pixiv/three-vrm (MIT). No motion files are loaded.
 * Dance: ORIGINAL procedural choreography written for Music Stream (not a port, not derived from any motion pack or
 * captured motion data): standard VRM humanoid bones are rotated by simple sine/ease curves driven by the audio
 * analyser frame (beat phase, BPM, energy, drop) or by an idle clock when nothing is playing.
 * The pixiv VRoid VRMA pack used up to ms-v76 is no longer referenced (its terms forbid extractable redistribution). */
import * as THREE from 'three';
import { GLTFLoader } from 'three/addons/loaders/GLTFLoader.js';
import { VRMLoaderPlugin, VRMUtils } from '@pixiv/three-vrm';
import { createDancer } from '/vendor/ms/vrm-dance.js?v=77';

function bone(h, n) {
  return h.getNormalizedBoneNode?.(n) || h.getBoneNode?.(n) || null;
}

export async function createOverlay(host, url, opts = {}) {
  const phone = !!opts.phone;
  const container = host.container;
  const renderer = new THREE.WebGLRenderer({ alpha: true, antialias: !phone, powerPreference: phone ? 'low-power' : 'high-performance', preserveDrawingBuffer: true });
  renderer.setClearColor(0x000000, 0);
  renderer.outputColorSpace = THREE.SRGBColorSpace;
  const canvas = renderer.domElement;
  canvas.style.cssText = 'position:absolute;inset:0;width:100%;height:100%;pointer-events:none';
  container.appendChild(canvas);
  let ctxLost = false;
  canvas.addEventListener('webglcontextlost', (e) => { ctxLost = true; try { e.preventDefault(); } catch (_) {} }, false);
  canvas.addEventListener('webglcontextrestored', () => { ctxLost = false; }, false);

  const scene = new THREE.Scene();
  const camera = new THREE.PerspectiveCamera(28, 1, 0.05, 40);
  camera.position.set(0, 1.35, 2.6);
  scene.add(new THREE.AmbientLight(0xffffff, 0.95));
  const key = new THREE.DirectionalLight(0xffffff, 1.2); key.position.set(1.2, 2.2, 2); scene.add(key);
  const fill = new THREE.DirectionalLight(0x99aaff, 0.4); fill.position.set(-2, 1, -1); scene.add(fill);

  const loader = new GLTFLoader();
  loader.register((p) => new VRMLoaderPlugin(p));

  const gltf = await loader.loadAsync(url);
  const vrm = gltf.userData.vrm;
  if (!vrm) throw new Error('not a VRM: ' + url);
  try { VRMUtils.removeUnnecessaryVertices(gltf.scene); } catch (_) {}
  try { VRMUtils.combineSkeletons(gltf.scene); } catch (_) {}
  scene.add(vrm.scene);
  if (vrm.meta && vrm.meta.metaVersion === '0') vrm.scene.rotation.y = Math.PI;  // VRM 0.x faces -Z; VRM 1.0 already faces the camera

  // Fit camera to humanoid height
  const hum = vrm.humanoid;
  const head = bone(hum, 'head') || bone(hum, 'hips');
  const hips = bone(hum, 'hips');
  let y = 1.2;
  if (head && hips) y = (head.getWorldPosition(new THREE.Vector3()).y + hips.getWorldPosition(new THREE.Vector3()).y) / 2 + 0.15;
  camera.position.set(0, y, phone ? 3.1 : 2.55);
  camera.lookAt(0, y - 0.15, 0);

  // ms-v77: original procedural dancer (vrm-dance.js); arm directions are measured in the VRM scene's local frame
  const dancer = createDancer(THREE, vrm, bone);

  let cssW = 1, cssH = 1, dpr = 1, visible = true, tier = 0, lastTap = 0;
  function resize(w, h, d) {
    cssW = w; cssH = h; dpr = Math.min(d || 1, phone ? 1.25 : 2);
    const q = tier >= 4 ? 0.55 : tier >= 3 ? 0.7 : 1;
    renderer.setPixelRatio(dpr * q);
    renderer.setSize(w, h, false);
    camera.aspect = w / Math.max(1, h);
    camera.updateProjectionMatrix();
  }
  if (host.canvas) resize(host.canvas.clientWidth || 360, host.canvas.clientHeight || 640, host.dpr || 1);

  return {
    mode: 'overlay',
    update(f) {
      if (!visible) return;
      if (ctxLost) throw new Error('VRM WebGL context lost');
      const dt = Math.min(0.05, (f.dt || 16) / 1000);
      dancer.update(f, dt);
      try { vrm.update(dt); } catch (_) {}
      // Look at pointer lightly
      try {
        if (f.pointer && f.pointer.active && vrm.lookAt) {
          vrm.lookAt.target = vrm.lookAt.target || new THREE.Object3D();
          vrm.lookAt.target.position.set((f.pointer.x - 0.5) * 2, 1.4 + (0.5 - f.pointer.y), 1);
        }
      } catch (_) {}
      renderer.render(scene, camera);
    },
    trigger(kind) {
      const now = performance.now();
      if (now - lastTap < 300) return;
      lastTap = now;
      dancer.trigger(kind === 'special' ? 'spin' : 'wave');
    },
    resize, setQuality(t) { tier = t || 0; resize(cssW, cssH, dpr); },
    setVisible(b) { visible = !!b; canvas.style.display = visible ? '' : 'none'; },
    setPalette() {},
    dispose() {
      try { dancer.reset(); } catch (_) {}
      try { VRMUtils.deepDispose(vrm.scene); } catch (_) {}
      // ms-v75: forceContextLoss frees the GL context immediately (leaked contexts evict older ones, e.g. the Live2D renderer)
      try { renderer.dispose(); renderer.forceContextLoss(); } catch (_) {}
      try { canvas.remove(); } catch (_) {}
    }
  };
}

/* MSGame character adapter (2d blit via offscreen three canvas) */
export async function createGameAdapter(id, file) {
  const host = {
    container: document.createElement('div'),
    canvas: { clientWidth: 288, clientHeight: 512 },
    dpr: 1, phone: true
  };
  host.container.style.cssText = 'position:fixed;left:-9999px;top:0;width:288px;height:512px;opacity:0;pointer-events:none';
  document.body.appendChild(host.container);
  const ov = await createOverlay(host, '/assets/chars/vrm/' + file, { phone: true, label: id });
  ov.resize(288, 512, 1);
  const blit = document.createElement('canvas'); blit.width = 288; blit.height = 512;
  const bctx = blit.getContext('2d');
  let pose = 'idle', last = performance.now();
  const inst = {
    loading: Promise.resolve(),
    model: true,
    setPose(p) { pose = p || 'idle'; if (p === 'jump' || p === 'up') ov.trigger('special'); },
    react(k) { if (k === 'drop' || k === 'ko') ov.trigger('special'); else if (k === 'p' || k === 'g') ov.trigger('tap'); },
    play(n) { if (n === 'spin' || n === 'drop') ov.trigger('special'); else ov.trigger('tap'); },
    poke() { ov.trigger('tap'); },
    draw(ctx, st) {
      const now = performance.now(), dt = Math.min(50, now - last); last = now;
      ov.update({
        dt, bpm: 120, beatPhase: st.beat || 0, energy: st.energy || 0.4,
        mood: 'energetic', beat: (st.beat || 0) < 0.08, downbeat: false, drop: false,
        reducedMotion: false, pointer: null, tier: st.lowFx ? 3 : 0
      });
      // read three canvas
      const src = host.container.querySelector('canvas');
      if (src) { bctx.clearRect(0, 0, 288, 512); bctx.drawImage(src, 0, 0); }
      const h = st.size * 1.38, w = h * 288 / 512;
      ctx.save();
      ctx.translate(st.x, st.y); ctx.scale(st.facing || 1, 1);
      ctx.drawImage(blit, -w / 2, -h, w, h);
      ctx.restore();
    },
    dispose() { ov.dispose(); try { host.container.remove(); } catch (_) {} }
  };
  return inst;
}

export async function registerGameCharacters() {
  if (!window.MSGame || !window.MSGame.registerCharacter) return false;
  const list = [
    ['vrm_darkness_shibu', 'Darkness Shibu', 'Darkness_Shibu.vrm', 'elegant night'],
    ['vrm_vivi', 'Vivi', 'Vivi.vrm', 'soft casual'],
    ['vrm_sendagaya_shibu', 'Sendagaya Shibu', 'Sendagaya_Shibu.vrm', 'school cool'],
    ['vrm_victoria', 'Victoria Rubin', 'Victoria_Rubin.vrm', 'frilly'],
    ['vrm_vita', 'Vita', 'Vita.vrm', 'cyber'],
    ['vrm_avatar_a', 'AvatarSample A', 'AvatarSample_A.vrm', 'everyday'],
    ['vrm_avatar_b', 'AvatarSample B', 'AvatarSample_B.vrm', 'street'],
    ['vrm_hair_f', 'HairSample F', 'HairSample_Female.vrm', 'hair physics'],
    ['vrm_sendagaya_shino', 'Sendagaya Shino', 'Sendagaya_Shino.vrm', 'school soft']
  ];
  for (const [id, name, file, vibe] of list) {
    try {
      window.MSGame.registerCharacter({
        id, name: name + ' (VRM)', short: name, vibe, kind: 'vrm',
        create(opts) {
          const stub = { loading: null, model: null, err: '', setPose() {}, react() {}, play() {}, poke() {}, draw(ctx, st) {
            const S = window.MSGame && window.MSGame.__silhouette; if (S) S.draw(ctx, st);
          }, dispose() {} };
          stub.loading = createGameAdapter(id, file).then((inst) => {
            Object.assign(stub, inst);
            return stub;
          }).catch((e) => { stub.err = String(e && e.message || e); });
          return stub;
        }
      });
    } catch (e) {}
  }
  return true;
}

// Auto-register when MSGame appears
(function waitGame() {
  if (registerGameCharacters()) return;
  let n = 0; const iv = setInterval(() => { if (registerGameCharacters() || ++n > 60) clearInterval(iv); }, 400);
})();
