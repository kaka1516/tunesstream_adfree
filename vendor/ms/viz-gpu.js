/* Music Stream — WebGPU audio backdrop with WebGL2 fallback (own code, 2026-11-11).
 * Used by Club Stage and Cinematic modes. If visuals fail, the caller keeps playing audio.
 * Photosensitivity: luminance pulses are capped; no full-frame strobe.
 */
const clamp = (v, a, b) => (v < a ? a : v > b ? b : v);

const WGSL = /* wgsl */ `
struct U {
  res: vec2f,
  t: f32,
  mode: f32,      // 0 club, 1 cine
  bass: f32,
  mid: f32,
  high: f32,
  energy: f32,
  beat: f32,      // decaying 0..1
  paused: f32,
  c1: vec3f,
  c2: vec3f,
};
@group(0) @binding(0) var<uniform> u: U;

fn hash(p: vec2f) -> f32 {
  return fract(sin(dot(p, vec2f(127.1, 311.7))) * 43758.5453);
}
fn noise(p: vec2f) -> f32 {
  let i = floor(p); let f = fract(p);
  let a = hash(i); let b = hash(i + vec2f(1.,0.));
  let c = hash(i + vec2f(0.,1.)); let d = hash(i + vec2f(1.,1.));
  let u2 = f * f * (3. - 2. * f);
  return mix(mix(a,b,u2.x), mix(c,d,u2.x), u2.y);
}
fn grid(uv: vec2f, w: f32) -> f32 {
  let g = abs(fract(uv) - 0.5);
  let l = smoothstep(w, 0., min(g.x, g.y));
  return l;
}

@vertex fn vs(@builtin(vertex_index) i: u32) -> @builtin(position) vec4f {
  var p = array<vec2f, 3>(vec2f(-1.,-1.), vec2f(3.,-1.), vec2f(-1.,3.));
  return vec4f(p[i], 0., 1.);
}

@fragment fn fs(@builtin(position) pos: vec4f) -> @location(0) vec4f {
  let res = max(u.res, vec2f(1.));
  var uv = (pos.xy / res);
  uv.y = 1. - uv.y;
  let aspect = res.x / res.y;
  var p = vec2f((uv.x - .5) * aspect, uv.y - .5);
  let t = u.t * (1. - u.paused * 0.85);
  var col = vec3f(0.);

  if (u.mode < 0.5) {
    // Club: neon perspective floor + orbs
    let horizon = 0.22 + u.bass * 0.04;
    var sky = mix(vec3f(0.02,0.01,0.06), u.c1 * 0.25, clamp(uv.y * 0.6, 0., 1.));
    sky += u.c2 * (0.04 + u.energy * 0.08) * smoothstep(0.6, 0.0, abs(uv.x));
    // stars
    let st = hash(floor(pos.xy * 0.35));
    if (st > 0.997) { sky += vec3f(0.6); }
    if (uv.y < horizon + 0.002) {
      let fy = max(horizon - uv.y, 0.002);
      var fu = vec2f((uv.x - .5) / fy, t * (0.25 + u.energy * 0.4) + 1. / fy);
      fu *= 4.;
      let line = grid(fu, 0.06 + u.bass * 0.04);
      let glow = grid(fu, 0.18) * 0.35;
      let fog = clamp(fy * 3., 0., 1.);
      var fl = u.c1 * (line * (0.55 + u.bass * 0.7) + glow * 0.4);
      fl += u.c2 * line * u.mid * 0.4;
      col = mix(sky, fl, 1. - fog * 0.85);
    } else {
      col = sky;
    }
    // beat orbs (capped)
    let pulse = 0.25 + 0.35 * u.beat * (1. - u.paused);
    for (var i = 0; i < 5; i++) {
      let fi = f32(i);
      let ang = fi * 1.2566 + t * 0.3;
      let rad = 0.18 + 0.08 * sin(t * 0.7 + fi);
      let c = vec2f(cos(ang) * rad * aspect, 0.18 + sin(ang) * rad * 0.4);
      let d = length(p - c);
      let hue = mix(u.c1, u.c2, fract(fi * 0.27));
      col += hue * pulse * 0.18 / (d * 28. + 0.12);
    }
  } else {
    // Cinematic: haze, bokeh, film grain, vignette
    let warm = mix(vec3f(0.04, 0.03, 0.03), u.c1 * 0.35, 0.5);
    let cool = mix(vec3f(0.02, 0.03, 0.05), u.c2 * 0.2, 0.5);
    col = mix(cool, warm, clamp(uv.y * 0.7 + 0.15, 0., 1.));
    col += u.c1 * 0.08 * smoothstep(0.55, 0.0, length(vec2f(p.x * 0.7, p.y + 0.1)));
    // drifting bokeh
    for (var i = 0; i < 8; i++) {
      let fi = f32(i);
      let q = vec2f(fract(sin(fi * 17.1) * 43758.5) * 2. - 1., fract(sin(fi * 31.7) * 23421.1) * 2. - 1.);
      let off = vec2f(sin(t * 0.07 + fi) * 0.15, cos(t * 0.05 + fi * 1.3) * 0.1);
      let d = length(p - (q * vec2f(.6,.4) + off));
      let r = 0.04 + 0.04 * fract(fi * 0.37) + u.mid * 0.02;
      let bokeh = smoothstep(r, r * 0.6, d) * (0.08 + u.energy * 0.08);
      col += mix(u.c1, u.c2, fract(fi * 0.2)) * bokeh * 0.6;
    }
    // soft curtain light
    col += u.c1 * (0.04 + 0.08 * u.energy) * smoothstep(0.35, 0., abs(p.x));
  }

  // film grain (cine heavier)
  let g = (hash(pos.xy + vec2f(t * 60., t)) - 0.5) * (0.04 + select(0.02, 0.07, u.mode > 0.5));
  col += g;
  // vignette
  let vig = smoothstep(1.15, 0.25, length(vec2f((uv.x-.5)*1.2, (uv.y-.5)*1.1)));
  col *= 0.55 + 0.45 * vig;
  // beat lift capped at +12%
  col *= 1. + 0.12 * u.beat * (1. - u.paused);
  col = clamp(col, vec3f(0.), vec3f(1.));
  return vec4f(col, 1.);
}
`;

const VERT = `attribute vec2 a; void main(){ gl_Position=vec4(a,0.,1.); }`;
const FRAG = `#version 300 es
precision highp float;
uniform vec2 u_res; uniform float u_t,u_mode,u_bass,u_mid,u_high,u_energy,u_beat,u_paused;
uniform vec3 u_c1,u_c2;
out vec4 o;
float hash(vec2 p){ return fract(sin(dot(p,vec2(127.1,311.7)))*43758.5453); }
float grid(vec2 uv,float w){ vec2 g=abs(fract(uv)-.5); return smoothstep(w,0.,min(g.x,g.y)); }
void main(){
  vec2 res=max(u_res,vec2(1.));
  vec2 uv=gl_FragCoord.xy/res; uv.y=1.-uv.y;
  float aspect=res.x/res.y;
  vec2 p=vec2((uv.x-.5)*aspect, uv.y-.5);
  float t=u_t*(1.-u_paused*.85);
  vec3 col=vec3(0.);
  if(u_mode<.5){
    float horizon=.22+u_bass*.04;
    vec3 sky=mix(vec3(.02,.01,.06), u_c1*.25, clamp(uv.y*.6,0.,1.));
    sky+=u_c2*(.04+u_energy*.08)*smoothstep(.6,0.,abs(uv.x));
    float st=hash(floor(gl_FragCoord.xy*.35)); if(st>.997) sky+=vec3(.6);
    if(uv.y<horizon+.002){
      float fy=max(horizon-uv.y,.002);
      vec2 fu=vec2((uv.x-.5)/fy, t*(.25+u_energy*.4)+1./fy)*4.;
      float line=grid(fu,.06+u_bass*.04);
      float glow=grid(fu,.18)*.35;
      float fog=clamp(fy*3.,0.,1.);
      vec3 fl=u_c1*(line*(.55+u_bass*.7)+glow*.4)+u_c2*line*u_mid*.4;
      col=mix(sky,fl,1.-fog*.85);
    } else col=sky;
    float pulse=.25+.35*u_beat*(1.-u_paused);
    for(int i=0;i<5;i++){
      float fi=float(i); float ang=fi*1.2566+t*.3; float rad=.18+.08*sin(t*.7+fi);
      vec2 c=vec2(cos(ang)*rad*aspect, .18+sin(ang)*rad*.4);
      float d=length(p-c);
      vec3 hue=mix(u_c1,u_c2,fract(fi*.27));
      col+=hue*pulse*.18/(d*28.+.12);
    }
  } else {
    vec3 warm=mix(vec3(.04,.03,.03),u_c1*.35,.5);
    vec3 cool=mix(vec3(.02,.03,.05),u_c2*.2,.5);
    col=mix(cool,warm,clamp(uv.y*.7+.15,0.,1.));
    col+=u_c1*.08*smoothstep(.55,0.,length(vec2(p.x*.7,p.y+.1)));
    for(int i=0;i<8;i++){
      float fi=float(i);
      vec2 q=vec2(fract(sin(fi*17.1)*43758.5)*2.-1., fract(sin(fi*31.7)*23421.1)*2.-1.);
      vec2 off=vec2(sin(t*.07+fi)*.15, cos(t*.05+fi*1.3)*.1);
      float d=length(p-(q*vec2(.6,.4)+off));
      float r=.04+.04*fract(fi*.37)+u_mid*.02;
      float bokeh=smoothstep(r,r*.6,d)*(.08+u_energy*.08);
      col+=mix(u_c1,u_c2,fract(fi*.2))*bokeh*.6;
    }
    col+=u_c1*(.04+.08*u_energy)*smoothstep(.35,0.,abs(p.x));
  }
  col+=(hash(gl_FragCoord.xy+vec2(t*60.,t))-.5)*(u_mode>.5?.07:.04);
  float vig=smoothstep(1.15,.25,length(vec2((uv.x-.5)*1.2,(uv.y-.5)*1.1)));
  col*=.55+.45*vig;
  col*=1.+.12*u_beat*(1.-u_paused);
  o=vec4(clamp(col,0.,1.),1.);
}`;

function hexToRgb(c) {
  const m = String(c || '').match(/[0-9a-f]{6}/i);
  if (!m) return [1, 0.8, 0.2];
  const n = parseInt(m[0], 16);
  return [((n >> 16) & 255) / 255, ((n >> 8) & 255) / 255, (n & 255) / 255];
}

async function createWebGPU(canvas, glHint) {
  if (!navigator.gpu) return null;
  const adapter = await navigator.gpu.requestAdapter({ powerPreference: glHint === 'low-power' ? 'low-power' : 'high-performance' });
  if (!adapter) return null;
  const device = await adapter.requestDevice();
  const ctx = canvas.getContext('webgpu');
  if (!ctx) return null;
  const fmt = navigator.gpu.getPreferredCanvasFormat();
  ctx.configure({ device, format: fmt, alphaMode: 'opaque' });
  const shader = device.createShaderModule({ code: WGSL });
  const pipe = device.createRenderPipeline({
    layout: 'auto',
    vertex: { module: shader, entryPoint: 'vs' },
    fragment: { module: shader, entryPoint: 'fs', targets: [{ format: fmt }] },
    primitive: { topology: 'triangle-list' }
  });
  const ubo = device.createBuffer({ size: 80, usage: GPUBufferUsage.UNIFORM | GPUBufferUsage.COPY_DST });
  const bind = device.createBindGroup({ layout: pipe.getBindGroupLayout(0), entries: [{ binding: 0, resource: { buffer: ubo } }] });
  const f32 = new Float32Array(20);
  return {
    kind: 'webgpu',
    draw(s) {
      const w = canvas.width, h = canvas.height;
      if (!w || !h) return;
      f32[0] = w; f32[1] = h; f32[2] = s.t; f32[3] = s.mode;
      f32[4] = s.bass; f32[5] = s.mid; f32[6] = s.high; f32[7] = s.energy;
      f32[8] = s.beat; f32[9] = s.paused; f32[10] = 0; f32[11] = 0;
      f32[12] = s.c1[0]; f32[13] = s.c1[1]; f32[14] = s.c1[2]; f32[15] = 0;
      f32[16] = s.c2[0]; f32[17] = s.c2[1]; f32[18] = s.c2[2]; f32[19] = 0;
      device.queue.writeBuffer(ubo, 0, f32);
      const enc = device.createCommandEncoder();
      const pass = enc.beginRenderPass({
        colorAttachments: [{ view: ctx.getCurrentTexture().createView(), clearValue: { r: 0, g: 0, b: 0, a: 1 }, loadOp: 'clear', storeOp: 'store' }]
      });
      pass.setPipeline(pipe); pass.setBindGroup(0, bind); pass.draw(3); pass.end();
      device.queue.submit([enc.finish()]);
    },
    dispose() { try { device.destroy(); } catch (_) {} }
  };
}

function createWebGL2(canvas) {
  const gl = canvas.getContext('webgl2', { alpha: false, antialias: false, powerPreference: 'low-power', preserveDrawingBuffer: false });
  if (!gl) return null;
  const sh = (type, src) => { const s = gl.createShader(type); gl.shaderSource(s, src); gl.compileShader(s); if (!gl.getShaderParameter(s, gl.COMPILE_STATUS)) { console.warn('viz-gpu', gl.getShaderInfoLog(s)); return null; } return s; };
  const vs = sh(gl.VERTEX_SHADER, VERT), fs = sh(gl.FRAGMENT_SHADER, FRAG);
  if (!vs || !fs) return null;
  const pr = gl.createProgram(); gl.attachShader(pr, vs); gl.attachShader(pr, fs); gl.linkProgram(pr);
  if (!gl.getProgramParameter(pr, gl.LINK_STATUS)) { console.warn('viz-gpu', gl.getProgramInfoLog(pr)); return null; }
  const buf = gl.createBuffer(); gl.bindBuffer(gl.ARRAY_BUFFER, buf);
  gl.bufferData(gl.ARRAY_BUFFER, new Float32Array([-1, -1, 3, -1, -1, 3]), gl.STATIC_DRAW);
  const loc = gl.getAttribLocation(pr, 'a');
  const U = {};
  for (const n of ['u_res','u_t','u_mode','u_bass','u_mid','u_high','u_energy','u_beat','u_paused','u_c1','u_c2']) U[n] = gl.getUniformLocation(pr, n);
  return {
    kind: 'webgl2',
    draw(s) {
      const w = canvas.width, h = canvas.height;
      if (!w || !h) return;
      gl.viewport(0, 0, w, h); gl.useProgram(pr);
      gl.bindBuffer(gl.ARRAY_BUFFER, buf); gl.enableVertexAttribArray(loc); gl.vertexAttribPointer(loc, 2, gl.FLOAT, false, 0, 0);
      gl.uniform2f(U.u_res, w, h); gl.uniform1f(U.u_t, s.t); gl.uniform1f(U.u_mode, s.mode);
      gl.uniform1f(U.u_bass, s.bass); gl.uniform1f(U.u_mid, s.mid); gl.uniform1f(U.u_high, s.high);
      gl.uniform1f(U.u_energy, s.energy); gl.uniform1f(U.u_beat, s.beat); gl.uniform1f(U.u_paused, s.paused);
      gl.uniform3fv(U.u_c1, s.c1); gl.uniform3fv(U.u_c2, s.c2);
      gl.drawArrays(gl.TRIANGLES, 0, 3);
    },
    dispose() { try { gl.getExtension('WEBGL_lose_context')?.loseContext(); } catch (_) {} }
  };
}

export async function createBackdrop(container, opts = {}) {
  const phone = !!opts.phone;
  const canvas = document.createElement('canvas');
  canvas.id = 'vizgpu';
  canvas.style.cssText = 'position:absolute;inset:0;width:100%;height:100%;pointer-events:none;z-index:0;display:none';
  container.insertBefore(canvas, container.firstChild);
  let backend = null, mode = 'club', visible = false, quality = phone ? 0.6 : 1, beat = 0, t0 = performance.now();
  let colors = ['#ff4ad2', '#39f3ff'];
  try { backend = await createWebGPU(canvas, phone ? 'low-power' : 'high-performance'); } catch (e) { console.warn('webgpu backdrop', e); }
  if (!backend) { try { backend = createWebGL2(canvas); } catch (e) { console.warn('webgl2 backdrop', e); } }
  function fit() {
    const w = container.clientWidth || 360, h = container.clientHeight || 360;
    const pr = Math.min(window.devicePixelRatio || 1, phone ? 1 : 1.5) * quality;
    const W = Math.max(1, Math.round(w * pr)), H = Math.max(1, Math.round(h * pr));
    if (canvas.width !== W || canvas.height !== H) { canvas.width = W; canvas.height = H; }
  }
  const api = {
    backend: () => (backend ? backend.kind : 'none'),
    setTheme(name) { mode = name === 'cine' || name === 'cinematic' ? 'cine' : 'club'; },
    setVisible(v) { visible = !!v && !!backend; canvas.style.display = visible ? '' : 'none'; if (visible) fit(); },
    setQuality(q) { quality = clamp(q, 0.35, 1); fit(); },
    setColors(c1, c2) { colors = [c1 || colors[0], c2 || colors[1]]; },
    frame(s = {}) {
      if (!visible || !backend) return;
      fit();
      beat = Math.max(s.beat ? 1 : beat * 0.9, 0);
      const now = (performance.now() - t0) / 1000;
      try {
        backend.draw({
          t: now, mode: mode === 'cine' ? 1 : 0,
          bass: clamp(s.bass || 0, 0, 1), mid: clamp(s.mid || 0, 0, 1),
          high: clamp(s.high || 0, 0, 1), energy: clamp(s.energy || 0, 0, 1),
          beat, paused: s.paused ? 1 : 0, c1: hexToRgb(colors[0]), c2: hexToRgb(colors[1])
        });
      } catch (e) { console.warn('backdrop frame', e); }
    },
    dispose() { try { backend && backend.dispose(); } catch (_) {} canvas.remove(); }
  };
  return api;
}
