/* Music Stream — Club Stage + Cinematic environments for the VRM dancer (own code, 2026-11-11).
 * Lights, floor, particles and camera are procedural. Optional CC0 Poly Haven HDRIs under /assets/viz/hdri/.
 * Safe: never throws into the audio path; missing assets are ignored.
 */
import * as THREE from 'three';
import { RGBELoader } from 'three/addons/loaders/RGBELoader.js';

const clamp = (v, a, b) => (v < a ? a : v > b ? b : v);
const HDRI_FALLBACK = {
  club: '/assets/viz/hdri/dikhololo_night_1k.hdr',
  cine: '/assets/viz/hdri/studio_small_09_1k.hdr',
  warm: '/assets/viz/hdri/venice_sunset_1k.hdr'
};
let HDRI = { ...HDRI_FALLBACK };
async function refreshHdriIndex() {
  try {
    const v = (typeof window !== 'undefined' && window.__MS_VIZ_REV) || '';
    const r = await fetch('/assets/viz/hdri/index.json?v=' + encodeURIComponent(v), { cache: 'no-store' });
    if (!r.ok) return;
    const j = await r.json();
    if (j && (j.club || j.cine || j.warm)) Object.assign(HDRI, j);
  } catch (_) {}
}

function gridTex(color = '#39f3ff') {
  const s = 256, c = document.createElement('canvas'); c.width = c.height = s;
  const g = c.getContext('2d');
  g.fillStyle = '#05050c'; g.fillRect(0, 0, s, s);
  g.strokeStyle = color; g.lineWidth = 2; g.shadowColor = color; g.shadowBlur = 8;
  g.beginPath();
  for (let i = 0; i <= 8; i++) { const p = i * s / 8; g.moveTo(p, 0); g.lineTo(p, s); g.moveTo(0, p); g.lineTo(s, p); }
  g.stroke();
  const t = new THREE.CanvasTexture(c); t.wrapS = t.wrapT = THREE.RepeatWrapping; t.repeat.set(12, 12); t.anisotropy = 4;
  return t;
}

function bokehTex() {
  const s = 64, c = document.createElement('canvas'); c.width = c.height = s;
  const g = c.getContext('2d');
  const gr = g.createRadialGradient(s / 2, s / 2, 0, s / 2, s / 2, s / 2);
  gr.addColorStop(0, 'rgba(255,255,255,0.85)'); gr.addColorStop(0.4, 'rgba(255,255,255,0.25)'); gr.addColorStop(1, 'rgba(255,255,255,0)');
  g.fillStyle = gr; g.fillRect(0, 0, s, s);
  const t = new THREE.CanvasTexture(c); t.needsUpdate = true; return t;
}

export function attachTheme(ctx) {
  const { THREE: T, scene, camera, renderer, phone, high } = ctx;
  const group = new T.Group(); group.name = 'msTheme'; scene.add(group);
  const env = { name: 'simple', lights: [], meshes: [], parts: [], fog: null, grain: null, bench: null };
  let hdriCache = {}, pmrem = null, particles = null, bars = null, barN = 0, beats = 0;
  let camHome = camera.position.clone(), look = new T.Vector3(0, 0.9, 0);
  let col1 = new T.Color(0xff4ad2), col2 = new T.Color(0x39f3ff);
  let quality = 1, visible = true;

  function clear() {
    for (const o of [...group.children]) {
      group.remove(o);
      o.traverse((n) => { if (n.geometry) n.geometry.dispose(); if (n.material) {
        const ms = Array.isArray(n.material) ? n.material : [n.material];
        for (const m of ms) { if (m.map && m.map.dispose && m.map !== hdriCache._keep) try { m.map.dispose(); } catch (_) {} try { m.dispose(); } catch (_) {} }
      } });
    }
    env.lights = []; env.meshes = []; env.parts = []; particles = null; bars = null;
    scene.fog = null; scene.background = null;
  }

  async function loadHDRI(url) {
    if (hdriCache[url]) return hdriCache[url];
    try {
      const tex = await new RGBELoader().loadAsync(url);
      tex.mapping = T.EquirectangularReflectionMapping;
      if (!pmrem) pmrem = new T.PMREMGenerator(renderer);
      const envMap = pmrem.fromEquirectangular(tex).texture;
      tex.dispose();
      hdriCache[url] = envMap;
      return envMap;
    } catch (e) { console.warn('hdri', url, e); return null; }
  }

  function addFloor(opts = {}) {
    const r = opts.radius || 6;
    const mat = new T.MeshStandardMaterial({
      color: opts.color || 0x0a0a12, metalness: opts.metal ?? 0.7, roughness: opts.rough ?? 0.25,
      map: opts.map || null, emissive: opts.emissive || 0x000000, emissiveIntensity: opts.emi || 0,
      transparent: !!opts.map, opacity: opts.map ? 0.95 : 1
    });
    const floor = new T.Mesh(new T.CircleGeometry(r, 64), mat);
    floor.rotation.x = -Math.PI / 2; floor.position.y = opts.y || 0; floor.receiveShadow = !!high;
    group.add(floor); env.meshes.push(floor);
    if (opts.platform) {
      const plat = new T.Mesh(new T.CylinderGeometry(0.95, 1.05, 0.06, 48), new T.MeshStandardMaterial({ color: 0x1a1020, metalness: 0.6, roughness: 0.3, emissive: 0x221133, emissiveIntensity: 0.4 }));
      plat.position.y = 0.03; plat.receiveShadow = !!high; plat.castShadow = !!high;
      group.add(plat); env.meshes.push(plat);
    }
    return floor;
  }

  function addSpot(color, pos, intensity) {
    const s = new T.SpotLight(color, intensity, 10, Math.PI / 5, 0.5, 1.2);
    s.position.copy(pos); s.target.position.set(0, 0.9, 0); group.add(s); group.add(s.target);
    if (high && quality > 0.7) { s.castShadow = true; s.shadow.mapSize.set(512, 512); s.shadow.bias = -0.0002; }
    env.lights.push(s); return s;
  }

  function makeParticles(n, size, cine) {
    const geo = new T.BufferGeometry();
    const pos = new Float32Array(n * 3), spd = new Float32Array(n * 3);
    for (let i = 0; i < n; i++) {
      pos[i * 3] = (Math.random() - 0.5) * (cine ? 5 : 6);
      pos[i * 3 + 1] = Math.random() * (cine ? 3.2 : 3.5);
      pos[i * 3 + 2] = (Math.random() - 0.5) * (cine ? 4 : 6);
      spd[i * 3] = (Math.random() - 0.5) * 0.15;
      spd[i * 3 + 1] = 0.05 + Math.random() * 0.2;
      spd[i * 3 + 2] = (Math.random() - 0.5) * 0.15;
    }
    geo.setAttribute('position', new T.BufferAttribute(pos, 3));
    geo.userData.spd = spd;
    const mat = new T.PointsMaterial({
      size: size, map: bokehTex(), transparent: true, depthWrite: false,
      blending: T.AdditiveBlending, color: cine ? 0xffe0b0 : 0xffffff, opacity: cine ? 0.55 : 0.7
    });
    particles = new T.Points(geo, mat); group.add(particles); env.parts.push(particles);
  }

  function makeBars(n) {
    const g = new T.BoxGeometry(0.08, 1, 0.08); const m = new T.MeshStandardMaterial({ color: 0xffffff, emissive: 0x39f3ff, emissiveIntensity: 1.2, metalness: 0.2, roughness: 0.4 });
    bars = new T.InstancedMesh(g, m, n); bars.instanceMatrix.setUsage(T.DynamicDrawUsage);
    const dummy = new T.Object3D();
    for (let i = 0; i < n; i++) {
      const a = (i / n) * Math.PI * 0.9 + Math.PI * 0.55, r = 2.4;
      dummy.position.set(Math.cos(a) * r, 0.5, Math.sin(a) * r - 0.4);
      dummy.scale.set(1, 0.2, 1); dummy.updateMatrix(); bars.setMatrixAt(i, dummy.matrix);
    }
    bars.count = n; group.add(bars); env.meshes.push(bars); barN = n;
  }

  function makeGrain() {
    const mat = new T.ShaderMaterial({
      transparent: true, depthTest: false, depthWrite: false,
      uniforms: { t: { value: 0 }, amp: { value: 0.07 } },
      vertexShader: 'varying vec2 vUv; void main(){ vUv=uv; gl_Position=vec4(position.xy,0.,1.); }',
      fragmentShader: `precision highp float; varying vec2 vUv; uniform float t,amp;
        float h(vec2 p){ return fract(sin(dot(p,vec2(12.9898,78.233)))*43758.5453); }
        void main(){ float n=h(vUv*vec2(640.,360.)+t*60.); gl_FragColor=vec4(vec3(n), amp); }`
    });
    const q = new T.Mesh(new T.PlaneGeometry(2, 2), mat);
    q.frustumCulled = false; q.renderOrder = 999; group.add(q); env.grain = q;
  }

  async function buildClub() {
    clear();
    scene.fog = new T.FogExp2(0x05010a, 0.12);
    const map = gridTex('#39f3ff');
    addFloor({ radius: 8, map, metal: 0.2, rough: 0.45, emi: 0.35, emissive: 0x0a2030, platform: true });
    const hemi = new T.HemisphereLight(0x6a3cff, 0x120810, 0.35); group.add(hemi); env.lights.push(hemi);
    addSpot(0xff4ad2, new T.Vector3(2.4, 3.2, 1.6), 6);
    addSpot(0x39f3ff, new T.Vector3(-2.2, 3.0, 1.8), 5);
    addSpot(0xffcf33, new T.Vector3(0.2, 3.4, -1.8), 4);
    if (!phone) addSpot(0x7cff9a, new T.Vector3(-1.6, 2.6, -1.2), 3);
    makeParticles(phone ? 80 : 220, phone ? 0.05 : 0.07, false);
    if (quality > 0.5) makeBars(phone ? 18 : 32);
    camera.fov = 38; camHome.set(0, 1.15, 4.1); look.set(0, 0.95, 0);
    camera.updateProjectionMatrix();
    const envMap = await loadHDRI(HDRI.club);
    if (envMap) { scene.environment = envMap; scene.environmentIntensity = 0.25; }
  }

  async function buildCine() {
    clear();
    scene.fog = new T.Fog(0x090704, 4, 14);
    addFloor({ radius: 7, color: 0x1a1410, metal: 0.15, rough: 0.7, y: 0 });
    const hemi = new T.HemisphereLight(0xffd8b0, 0x1a100c, 0.2); group.add(hemi); env.lights.push(hemi);
    const key = new T.DirectionalLight(0xffe0c0, 1.6); key.position.set(2.8, 3.6, 1.4); group.add(key); env.lights.push(key);
    if (high && quality > 0.7) { key.castShadow = true; key.shadow.mapSize.set(1024, 1024); key.shadow.camera.near = 0.5; key.shadow.camera.far = 12; key.shadow.camera.left = -3; key.shadow.camera.right = 3; key.shadow.camera.top = 3; key.shadow.camera.bottom = -1; }
    const rim = new T.DirectionalLight(0xffc08a, 2.0); rim.position.set(-2.2, 2.4, -2.6); group.add(rim); env.lights.push(rim);
    const fill = new T.DirectionalLight(0x6a80b0, 0.2); fill.position.set(-1.5, 1.4, 2.2); group.add(fill); env.lights.push(fill);
    makeParticles(phone ? 50 : 120, phone ? 0.08 : 0.12, true);
    if (quality > 0.45) makeGrain();
    camera.fov = 28; camHome.set(0.15, 1.25, 3.6); look.set(0, 1.0, 0);
    camera.updateProjectionMatrix();
    const envMap = await loadHDRI(HDRI.cine);
    if (envMap) { scene.environment = envMap; scene.environmentIntensity = 0.35; }
  }

  function buildSimple() {
    clear();
    scene.environmentIntensity = 1;
    camera.fov = 30; camHome.set(0, 0.95, camera.position.z || 3.4); look.set(0, 0.9, 0);
    camera.updateProjectionMatrix();
  }

  let buildTok = 0;
  async function setTheme(name) {
    try { await refreshHdriIndex(); } catch (_) {}
    const n = name === 'cinematic' ? 'cine' : (name || 'simple');
    if (n === env.name && group.children.length) return;
    env.name = n;
    const tok = ++buildTok;
    try {
      if (n === 'club') await buildClub();
      else if (n === 'cine') await buildCine();
      else buildSimple();
    } catch (e) { console.warn('theme', n, e); if (tok === buildTok) buildSimple(); }
  }

  const dummy = new T.Object3D();
  function update(s = {}) {
    if (!visible || env.name === 'simple') return;
    const dt = Math.min(0.05, s.dt || 0.016), bass = s.bass || 0, energy = s.energy || 0, mid = s.mid || 0;
    const paused = !!s.paused, t = s.t || 0;
    if (s.colors) {
      try { col1.set(s.colors[0] || col1); col2.set(s.colors[1] || col2); } catch (_) {}
    }
    if (s.beat) beats++;
    // spots orbit + pulse
    const live = paused ? 0 : 1;
    env.lights.forEach((L, i) => {
      if (L.isSpotLight) {
        const a = t * (0.25 + i * 0.07) + i * 1.7;
        L.position.x = Math.cos(a) * (2.2 + i * 0.15);
        L.position.z = Math.sin(a) * (1.8 + (i % 2) * 0.4);
        L.intensity = (3 + 4 * energy * live) * quality;
        if (i === 0) L.color.copy(col1); if (i === 1) L.color.copy(col2);
      }
    });
    if (particles) {
      const pos = particles.geometry.attributes.position, spd = particles.geometry.userData.spd;
      const n = pos.count, lift = (0.3 + energy * 1.4) * live;
      for (let i = 0; i < n; i++) {
        pos.array[i * 3] += spd[i * 3] * dt * live;
        pos.array[i * 3 + 1] += spd[i * 3 + 1] * dt * lift;
        pos.array[i * 3 + 2] += spd[i * 3 + 2] * dt * live;
        if (pos.array[i * 3 + 1] > 3.6) pos.array[i * 3 + 1] = 0;
      }
      pos.needsUpdate = true;
      particles.material.opacity = (env.name === 'cine' ? 0.4 : 0.55) + energy * 0.3 * live;
      particles.material.color.copy(env.name === 'cine' ? col1 : col2);
    }
    if (bars && s.bins) {
      const N = barN, bins = s.bins;
      for (let i = 0; i < N; i++) {
        const lo = Math.floor(Math.pow(i / N, 1.4) * (bins.length * 0.35)) + 1;
        const hi = Math.max(lo + 1, Math.floor(Math.pow((i + 1) / N, 1.4) * (bins.length * 0.35)) + 1);
        let m = 0; for (let k = lo; k < hi && k < bins.length; k++) m = Math.max(m, bins[k]);
        const h = 0.15 + (m / 255) * (1.6 + bass);
        const a = (i / N) * Math.PI * 0.9 + Math.PI * 0.55, r = 2.4;
        dummy.position.set(Math.cos(a) * r, h / 2, Math.sin(a) * r - 0.4);
        dummy.scale.set(1, h, 1); dummy.updateMatrix(); bars.setMatrixAt(i, dummy.matrix);
      }
      bars.instanceMatrix.needsUpdate = true;
      if (bars.material.emissive) bars.material.emissive.copy(col2);
    }
    if (env.grain) { env.grain.material.uniforms.t.value = t; env.grain.material.uniforms.amp.value = paused ? 0.03 : 0.06; env.grain.visible = quality > 0.45; }
    // cinematic camera drift (frozen on pause)
    if (env.name === 'cine' && !paused) {
      const yaw = Math.sin(t * 0.08) * 0.28, dolly = Math.sin(t * 0.05) * 0.18;
      camera.position.set(camHome.x + yaw, camHome.y + Math.sin(t * 0.06) * 0.05, camHome.z + dolly);
      camera.lookAt(look);
    } else if (env.name === 'club' && !paused) {
      const yaw = Math.sin(t * 0.15) * 0.12;
      camera.position.set(camHome.x + yaw, camHome.y, camHome.z);
      camera.lookAt(look);
    }
  }

  return {
    get name() { return env.name; },
    setTheme, update,
    setColors(a, b) { try { if (a) col1.set(a); if (b) col2.set(b); } catch (_) {} },
    setQuality(q) { quality = clamp(q, 0.35, 1); if (particles) particles.visible = q > 0.4; if (bars) bars.visible = q > 0.5; if (env.grain) env.grain.visible = q > 0.45; },
    setVisible(v) { visible = !!v; group.visible = visible; },
    dispose() { clear(); try { pmrem && pmrem.dispose(); } catch (_) {} scene.remove(group); }
  };
}
