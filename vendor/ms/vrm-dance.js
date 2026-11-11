/* Music Stream — original procedural VRM dancer (ms-v77).
 * Written from scratch for this project, original Music Stream code (project licence not yet chosen by the owner; see THIRD_PARTY_NOTICES.md). Not a port and not derived from any
 * motion file, motion pack or captured performance. It only rotates standard VRM humanoid bones (hips, spine, chest,
 * neck, head, upper/lower arms, upper/lower legs) with plain sine / ease curves.
 * Inputs per frame (all optional): beatPhase 0..1, bpm, energy 0..1, drop, mood, idle, reducedMotion.
 * With no music (idle / no beat) it falls back to a slow breathing sway driven by its own clock.
 * Axis signs are measured from the model's rest pose (which side each arm points to) plus the VRM version (0.x faces -Z,
 * 1.0 faces +Z), so the same code lowers both arms and bends elbows/knees forward on either rig. */
const NAMES = ['hips', 'spine', 'chest', 'upperChest', 'neck', 'head', 'leftUpperArm', 'rightUpperArm', 'leftLowerArm', 'rightLowerArm',
  'leftHand', 'rightHand', 'leftUpperLeg', 'rightUpperLeg', 'leftLowerLeg', 'rightLowerLeg'];
const TAU = Math.PI * 2;
const MOVES = ['groove', 'pump', 'clap', 'sway'];
const ease = (t) => t < 0 ? 0 : t > 1 ? 1 : t * t * (3 - 2 * t);

export function createDancer(THREE, vrm, boneOf) {
  const hum = vrm && vrm.humanoid;
  const B = {};
  for (const n of NAMES) B[n] = hum ? boneOf(hum, n) : null;
  const fz = vrm && vrm.meta && vrm.meta.metaVersion === '0' ? -1 : 1;   // model forward along local Z
  // which way each arm points in the rest pose, in the VRM scene's local frame (independent of any later scene rotation)
  function armDir(a, b, dflt) {
    try {
      if (!a || !b || !vrm.scene) return dflt;
      vrm.scene.updateMatrixWorld(true);
      const pa = a.getWorldPosition(new THREE.Vector3()), pb = b.getWorldPosition(new THREE.Vector3());
      vrm.scene.worldToLocal(pa); vrm.scene.worldToLocal(pb);
      const d = pb.x - pa.x; return Math.abs(d) > 1e-4 ? Math.sign(d) : dflt;
    } catch (_) { return dflt; }
  }
  const dxL = armDir(B.leftUpperArm, B.leftHand || B.leftLowerArm, fz === -1 ? -1 : 1);
  const dxR = armDir(B.rightUpperArm, B.rightHand || B.rightLowerArm, -dxL);
  const hipsY0 = B.hips ? B.hips.position.y : 0, hipsX0 = B.hips ? B.hips.position.x : 0;
  const cur = {};          // smoothed rotations per bone [x,y,z]
  let t = 0, phase = 0, lastPh = 0, beats = 0, move = 0, phraseStart = 0, dropUntil = -1;
  let wave = -1, spin = -1, blinkAt = 2.5, blink = 0;

  // pose helpers (targets are absolute Euler angles on the normalized rig, whose rest pose is all zeros)
  function armPose(T, side, raise, fwd, elbow, twist = 0) {
    const dx = side === 'left' ? dxL : dxR;
    T[side + 'UpperArm'] = [-fz * fwd, twist, -dx * (1.25 - raise)];      // raise 0 = arm down, 1.25 = T-pose, ~2.5 = overhead
    T[side + 'LowerArm'] = [0, -fz * dx * elbow, 0];                        // elbow bends toward the front
  }
  function legPose(T, side, thigh, knee, spread = 0) {
    T[side + 'UpperLeg'] = [-fz * thigh, 0, spread];
    T[side + 'LowerLeg'] = [fz * knee, 0, 0];
  }

  function targets(f, amp, idle) {
    const T = {}, s = Math.sin, c = Math.cos, p = phase * TAU, half = (beats % 2 + phase) * Math.PI;  // half: one cycle per 2 beats
    const bounce = Math.max(0, s(phase * Math.PI));   // 0 at the beat, peak between beats
    const hit = Math.pow(1 - phase, 3);               // sharp accent right on the beat
    let hipsDrop = 0, hipsShift = 0;
    const name = idle ? 'idle' : t < dropUntil ? 'pump' : MOVES[move % MOVES.length];
    if (name === 'idle') {             // breathing sway, no beat
      const b = s(t * 1.3), w = s(t * 0.55);
      T.hips = [0, w * 0.06, 0]; T.spine = [fz * b * 0.02, 0, w * 0.03]; T.head = [fz * 0.04 + b * 0.015, -w * 0.08, 0];
      armPose(T, 'left', 0.05 + b * 0.02, 0.05, 0.18); armPose(T, 'right', 0.05 - b * 0.02, 0.05, 0.18);
      legPose(T, 'left', 0, 0); legPose(T, 'right', 0, 0);
    } else if (name === 'groove') {   // bob on the beat, sway each two beats, swinging arms
      const sw = s(half);
      hipsDrop = hit * 0.035; hipsShift = sw * 0.03;
      T.hips = [0, sw * 0.18, sw * 0.05]; T.spine = [fz * 0.05 * hit, 0, -sw * 0.08]; T.chest = [0, -sw * 0.1, 0];
      T.head = [fz * 0.14 * hit, sw * 0.12, -sw * 0.06];
      armPose(T, 'left', 0.12, 0.35 * sw, 0.45 + 0.25 * bounce); armPose(T, 'right', 0.12, -0.35 * sw, 0.45 + 0.25 * bounce);
      legPose(T, 'left', 0.12 * hit, 0.25 * hit); legPose(T, 'right', 0.12 * hit, 0.25 * hit);
    } else if (name === 'pump') {     // fists pumped up on alternate beats, knees bounce
      const up = beats % 2 === 0;
      hipsDrop = hit * 0.06;
      T.hips = [0, 0, 0]; T.spine = [-fz * 0.05, 0, 0]; T.head = [-fz * 0.08 + fz * 0.15 * hit, 0, 0];
      armPose(T, 'left', up ? 2.3 - 0.4 * phase : 1.0, 0.15, up ? 0.3 : 1.3); armPose(T, 'right', up ? 1.0 : 2.3 - 0.4 * phase, 0.15, up ? 1.3 : 0.3);
      legPose(T, 'left', 0.25 * hit, 0.5 * hit); legPose(T, 'right', 0.25 * hit, 0.5 * hit);
    } else if (name === 'clap') {     // hands meet in front on the beat, step side to side
      const side = beats % 2 ? 1 : -1, close = hit;
      hipsShift = side * 0.04 * ease(phase * 2); hipsDrop = hit * 0.03;
      T.hips = [0, side * 0.12, 0]; T.spine = [fz * 0.06, 0, -side * 0.05]; T.head = [fz * 0.1 * hit, side * 0.15, 0];
      armPose(T, 'left', 0.55, 0.85 + 0.2 * close, 1.1, -dxL * fz * 0.5 * close); armPose(T, 'right', 0.55, 0.85 + 0.2 * close, 1.1, -dxR * fz * 0.5 * close);
      legPose(T, 'left', side < 0 ? 0.25 : 0.05, side < 0 ? 0.45 : 0.1); legPose(T, 'right', side > 0 ? 0.25 : 0.05, side > 0 ? 0.45 : 0.1);
    } else {                          // 'sway': both arms overhead, swaying over two beats
      const sw = s(half);
      hipsShift = -sw * 0.04;
      T.hips = [0, 0, -sw * 0.08]; T.spine = [0, 0, sw * 0.12]; T.chest = [0, 0, sw * 0.08]; T.head = [fz * 0.06 * hit, 0, sw * 0.1];
      armPose(T, 'left', 2.2 + 0.25 * sw, 0.1, 0.35); armPose(T, 'right', 2.2 - 0.25 * sw, 0.1, 0.35);
      legPose(T, 'left', 0.1 * hit, 0.2 * hit); legPose(T, 'right', 0.1 * hit, 0.2 * hit);
    }
    if (wave >= 0) {                   // tap: right-hand wave, 1.6 s
      const k = ease(Math.min(1, wave / 0.25)) * ease(Math.min(1, (1.6 - wave) / 0.25));
      const W = {}; armPose(W, 'right', 2.1, 0.1, 1.2 + 0.45 * s(wave * 14));
      for (const n of ['rightUpperArm', 'rightLowerArm']) T[n] = (T[n] || [0, 0, 0]).map((v, i) => v + (W[n][i] - v) * k);
    }
    // global amplitude (energy / reduced motion) scales everything around the rest pose
    for (const n in T) T[n] = T[n].map((v) => v * amp);
    // arms keep their 'down' baseline even at low amplitude, so they never snap back to a T-pose
    for (const side of ['left', 'right']) {
      const dx = side === 'left' ? dxL : dxR, k = side + 'UpperArm';
      if (T[k]) T[k][2] = -dx * 1.25 + (T[k][2] + dx * 1.25 * amp);
    }
    return { T, hipsDrop: hipsDrop * amp, hipsShift: hipsShift * amp, name };
  }

  function update(f = {}, dt = 1 / 60) {
    t += dt;
    const idle = !!f.idle || !(f.bpm > 0) || (f.energy != null && f.energy < 0.03);
    const bpm = Math.max(60, Math.min(180, f.bpm || 100));
    let ph = typeof f.beatPhase === 'number' && !idle ? ((f.beatPhase % 1) + 1) % 1 : (lastPh + dt * bpm / 60) % 1;
    if (ph < lastPh - 0.5) {           // new beat
      beats++;
      if (beats - phraseStart >= 8 && !f.reducedMotion) { phraseStart = beats; move++; }
    }
    lastPh = ph; phase = ph;
    if (f.drop && !f.reducedMotion) { dropUntil = t + 4 * 60 / bpm; if (spin < 0) spin = 0; }
    const energy = f.energy == null ? 0.5 : Math.max(0, Math.min(1, f.energy));
    const amp = (idle ? 1 : 0.55 + 0.6 * energy) * (f.reducedMotion ? 0.35 : 1);
    const { T, hipsDrop, hipsShift, name } = targets(f, amp, idle);
    const k = 1 - Math.exp(-dt * (f.reducedMotion ? 6 : 14));
    for (const n in T) {
      const b = B[n]; if (!b) continue;
      const c = cur[n] || (cur[n] = [b.rotation.x, b.rotation.y, b.rotation.z]);
      for (let i = 0; i < 3; i++) c[i] += (T[n][i] - c[i]) * k;
      b.rotation.set(c[0], c[1], c[2]);
    }
    if (B.hips) {
      let sp = 0;
      if (spin >= 0) { spin += dt; const d = f.reducedMotion ? 0 : 1.1; sp = d ? ease(spin / d) * TAU : 0; if (spin >= d) spin = -1, sp = 0; }
      B.hips.rotation.y += sp;
      B.hips.position.y = hipsY0 - hipsDrop; B.hips.position.x = hipsX0 + hipsShift;
    }
    if (wave >= 0) { wave += dt; if (wave > 1.6) wave = -1; }
    // blink (expression preset present on VRM 0.x and 1.0)
    try {
      const em = vrm.expressionManager;
      if (em) {
        if (t > blinkAt) { blink = 0.18; blinkAt = t + 2.5 + ((t * 7.31) % 3); }
        blink = Math.max(0, blink - dt); em.setValue('blink', blink > 0 ? Math.sin((0.18 - blink) / 0.18 * Math.PI) : 0);
      }
    } catch (_) {}
    return name;
  }
  function trigger(kind) { if (kind === 'spin') { if (spin < 0) spin = 0; } else wave = 0; }
  function reset() {
    for (const n in cur) if (B[n]) B[n].rotation.set(0, 0, 0);
    if (B.hips) { B.hips.position.y = hipsY0; B.hips.position.x = hipsX0; }
  }
  return { update, trigger, reset, info: { fz, dxL, dxR, bones: NAMES.filter((n) => B[n]).length } };
}
