# Stage avatar slot (MSViz 1.1)

The chibi dancers (Tara/Kavi/Rivo) were rejected and are **not** used. The Stage now has an empty,
pluggable avatar slot. A real anime avatar renderer (VRM via three-vrm, or Live2D) plugs in later
without touching the beat engine, scenes, interaction or toys.

## Register
```js
MSViz.registerAvatar('my-vrm', { label: 'Aiko (VRM)', factory: async host => adapter });
```
Load the adapter script after `/vendor/ms/viz.js`. It appears in **Visuals settings → Avatar**.
The choice is saved in `localStorage['ms.viz'].avatar`.

`host` = `{container, canvas, audioCtx, phone, dpr, dprCap, reducedMotion, box}`
- `container`: an absolutely positioned layer over the stage canvas (pointer-events:none). Overlay renderers append their own `<canvas>` here (three.js WebGL, Pixi/Live2D).
- `box`: the normalized avatar box `{x (centre), y (feet), w, h}`. The user can drag it (feet band 62–98%).

## Adapter
| member | required | notes |
|---|---|---|
| `mode` | – | `'overlay'` (own canvas in container) or `'2d'` (draws into the stage ctx via `draw`). Default `'2d'`. |
| `update(frame)` | yes | Called synchronously every stage frame. **Render here** (e.g. `renderer.render()` / `app.render()`), not in your own rAF, so the cost counts against the §6 budget and the tier ladder. |
| `draw(g,w,h,boxPx)` | 2d only | device-pixel box `{x,y,w,h}` |
| `trigger(kind,info)` | – | `'tap'` (cheer) or `'special'`. Already quantized to the next beat and rate-limited (1/beat, special 1/16 beats). |
| `hitTest(x,y)` | – | normalized stage coords; default = box test |
| `resize(cssW,cssH,dpr)`, `setPalette(pal)`, `setVisible(b)`, `setQuality(tier 0–5)`, `dispose()` | – | `pal` = `{bg,primary,secondary,glow}` from album art (OKLab k-means) |

`frame` (AvatarFrame): `t, dt, bpm, conf, idle, beat, beatN, beatPhase (0–1), bar, downbeat, onset, strength,
drop, energy, bass, mid, high, centroid, mood (devotional|energetic|romantic|sad|calm), style, key, intensity
(0.15 in reduced motion), reducedMotion, pointer {x,y,active}, box, tier`.

If `update` throws 3 frames in a row, the slot disables itself (`stats().avatarErr`).

## VRM sketch (three-vrm)
```js
MSViz.registerAvatar('vrm', { label: 'VRM', factory: async host => {
  const THREE = await import('/vendor/three/three.module.js'); /* + GLTFLoader + VRMLoaderPlugin */
  const r = new THREE.WebGLRenderer({ alpha: true, antialias: false }); host.container.appendChild(r.domElement);
  /* load the .vrm, build a scene and a camera */
  return { mode: 'overlay',
    update(f) { /* drive humanoid bones from f.beatPhase, f.energy, f.mood; blink and expressions from f.onset */ vrm.update(f.dt / 1000); r.render(scene, cam); },
    trigger(k) { /* play a cheer or special clip */ },
    resize(w, h, dpr) { r.setPixelRatio(Math.min(dpr, host.dprCap)); r.setSize(w, h); },
    setQuality(t) { r.setPixelRatio(t >= 3 ? 0.75 : Math.min(devicePixelRatio, host.dprCap)); },
    dispose() { r.dispose(); r.domElement.remove(); } };
}});
```
For Live2D, use the same shape with pixi-live2d-display: `app.ticker.stop()`, then call `app.render()` inside `update`.
Check the model licence (VRM meta / Live2D sample licence) before shipping any model.
