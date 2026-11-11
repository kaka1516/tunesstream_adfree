# Third-party notices and release blockers (ms-v79, checked 2026-11-08 IST)

**Music Stream's own code** is original work. The owner has **not chosen a licence yet (unspecified)**, so no licence is granted for it. It is
credited here and in `docs/`. Do not call the package "open source" until a licence is chosen. Any licence chosen later must **exclude the
Live2D files**: Live2D licences forbid releasing their code under a licence that is not from Live2D (Open Software License 5.6/5.7,
Proprietary License 6.8). Model and art assets are governed by `docs/ASSET_LICENSES.md` and `docs/GAME_CREDITS.md`.

## Shipped third-party code: provenance verified against npm
Each tarball sha1 equals the registry `dist.shasum`. "Identical" means the shipped file is byte-identical to the file in that tarball.

| Shipped file(s) | Package@version | Licence | Identical? | Licence text in tree |
|---|---|---|---|---|
| `assets/chars/lib/cubism5/index.es.js` | untitled-pixi-live2d-engine@1.4.0 ([repo](https://github.com/Untitled-Story/untitled-pixi-live2d-engine) @b4d6a31) | MIT for the engine code; **the bundled Cubism Web Framework is under the Live2D Open Software License** | yes | `licenses/untitled-pixi-live2d-engine-1.4.0.LICENSE.txt`, `licenses/CubismWebFramework-Untitled-Story-8df8478.LICENSE.md` (copies in `assets/chars/lib/cubism5/`) |
| `assets/chars/lib/cubism5/cubism.es.js` | same | same | **modified** (render-order fix; notice in `assets/chars/lib/cubism5/NOTICE.md`) | same |
| `assets/chars/lib/cubism5/pixi.min.js` | pixi.js@8.22.0 `dist/pixi.min.mjs` | MIT; bundles earcut 3.2.4 (ISC), tiny-lru 11.4.7 (BSD-3-Clause), eventemitter3, ismobilejs, parse-svg-path and @pixi/colord (MIT). Texts for undetected declared dependencies are kept conservatively | yes | `licenses/pixi.js-8.22.0.LICENSE.txt`, `licenses/pixi.js-8.22.0-bundled-deps.txt` |
| `assets/chars/lib/pixi.min.js` | pixi.js@6.5.2 | MIT (an embedded BSD notice for webgl-meincraft stays inside the bundle) | yes | `assets/chars/lib/LICENSE-pixi.txt` (= npm LICENSE) |
| `assets/chars/lib/cubism4.min.js` | pixi-live2d-display@0.4.0 | MIT; the **bundled Cubism 4 Framework** ([guansss/CubismWebFramework](https://github.com/guansss/CubismWebFramework) @1f9cdfd) is under the Live2D Open Software License | yes | `assets/chars/lib/LICENSE-pixi-live2d-display.txt`, `assets/chars/lib/LICENSE-CubismWebFramework-cubism4.md` |
| `vendor/three/three.module.js`, `vendor/three/examples/jsm/**` (66 files), `vendor/three-addons/GLTFLoader.js` | three@0.170.0 | MIT | yes (all) | `vendor/three/LICENSE` |
| `vendor/three-vrm/three-vrm.module.js` (`nodes/` not compared) | @pixiv/three-vrm@3.3.4 | MIT | yes (module) | `vendor/three-vrm/LICENSE` |
| `vendor/three-vrm-animation/*` (loaded again since v80 by `vendor/ms/dance3d.js`) | @pixiv/three-vrm-animation@3.3.4 | MIT | yes | `vendor/three-vrm-animation/LICENSE` |
| `vendor/butterchurn/butterchurn.min.js` | butterchurn@2.6.7 | MIT (+ @babel/runtime helpers, MIT, exact version not determinable) | yes | `vendor/butterchurn/LICENSE-butterchurn.txt`, `licenses/babel-runtime.LICENSE.txt` |
| `vendor/butterchurn/presets-all.min.js`, `presets-curated.js` | butterchurn-presets@2.4.7 | MIT | the "all" file = `lib/butterchurnPresets.min.js`; curated is a subset | `vendor/butterchurn/LICENSE-butterchurn-presets.txt` (= npm LICENSE) |
| `vendor/ms/neonviz.js` (ported parts) | Wave.js @7ed12c4 | MIT | port (adapted) | header + `vendor/ms/LICENSE-wave.js.txt` |
| `assets/chars/lib/live2dcubismcore.min.js` | Live2D Cubism Core 5.1.0 | Live2D Proprietary Software License, Redistributable Code | = https://cubism.live2d.com/sdk-web/cubismcore/live2dcubismcore.min.js (sha256 25ae938c…) | header kept |
| `assets/chars/lib/live2dcubismcore.06.min.js` | Live2D Cubism Core 6.0.1 | same | **not matched to a public artifact (B2)** | header kept |

ecma-proposal-math-extensions@0.0.2 (a butterchurn dependency) declares MIT in package.json only; neither the package nor its repo has a licence text. This is a minor notice gap.

Sources (the URLs are authoritative; reference copies are in `licenses/`):
- https://www.live2d.com/eula/live2d-open-software-license-agreement_en.html (v1.4, revised 2025-02-03)
- https://www.live2d.com/eula/live2d-proprietary-software-license-agreement_en.html (v2.1, revised 2025-02-03)
- https://www.live2d.com/en/download/cubism-sdk/release-license/

## Release blockers (do not publish or distribute a package with the Live2D path until these are resolved)
- **B1: Live2D publication licence and "Expandable Application".**
  - Publishing a Derivative Work that uses Cubism needs a Live2D Publication License Agreement.
  - General Users, individuals and Small-Scale Enterprises (< ¥10M sales) are exempt, **except for an Expandable Application**, meaning one that "uses … any indefinite number of models by adding … files (e.g. avatars …)" (OSL 1.5 and 2.3; Proprietary 1.5, 2.1, 2.2 and 6.3).
  - Music Stream has a pluggable avatar slot and 19 characters, so Live2D may treat it as expandable. Only Live2D decides.
  - Options: ask Live2D, or ship a build without the Live2D path (the 7 CC0 VRM characters are fully FOSS).
- **B2: Core 6.0.1 provenance.** `live2dcubismcore.06.min.js` (sha256 8741f739779b5d5210872bd3d7d99f0f1e56e6c87409e7d26d6bb4b80aa1ef47, csmGetVersion 0x06000001) does not match any official public file; the CDN currently serves 5.1.0. Fix: the owner re-downloads it from the official Cubism SDK for Web (this means accepting Live2D's licence) and compares the hash.
- **B3: project licence unspecified.** This is the owner's choice.
- **B4: Live2D sample models and Amahane's custom licence.** Their terms apply (see ASSET_LICENSES).

No reverse engineering was done. The Core is unmodified and only its public JS API is used. The Framework fix is a source-level alteration under OSL 2.1, and the licence indications are kept.

## v80 (2026-11-09) — Dancer + Rhythm game replaced

### Added
- **Neolution** rhythm game — by GareBear99, https://github.com/GareBear99/Neolution (MIT, commit 2aa6f0e).
  Vendored at `vendor/neolution/` (`LICENSE-neolution.txt`, unmodified `upstream-index.html`, modified `game.html`; edits marked `MS:`).
  Notes are generated from the song that is playing (OfflineAudioContext decode → onset peaks).
- **Dance motions** — VRMA files from the **open-vrma** dataset, https://github.com/sanamiy/open-vrma / https://huggingface.co/datasets/Sanami/open-vrma
  (conversion and metadata CC0-1.0). Stored in `assets/dance/` (license text in `assets/dance/LICENSE-open-vrma.md`; per-clip license in each `.motion.json`).
  - CMU subjects 94, 85, 90, 103, 61, 60 — **CMU Graphics Lab Motion Capture Database** (`LicenseRef-CMU-Mocap`: may be copied, modified and redistributed; must not be resold as data).
    *The data used in this project was obtained from mocap.cs.cmu.edu. The database was created with funding from NSF EIA-0196217.*
    BVH conversion by Bruce Hahne (cgspeed) via https://github.com/Shriinivas/cmubvh.
  - `quaternius_ual1_Dance_Loop`, `quaternius_ual1_Idle_Loop` — Quaternius Universal Animation Library (CC0-1.0). Animations by Quaternius (https://quaternius.com/).
- Runtime: three.js (MIT), @pixiv/three-vrm + @pixiv/three-vrm-animation 3.3.4 (MIT) — already vendored.
- `vendor/ms/dance3d.js` — own code: beat tracker (spectral flux + autocorrelation + PLL) and beat-synced VRM clip player.

### Removed (backed up in `backup-v80/` and `*.pre-v80.*`)
- viz.js scenes: Marigold Burst, Neon Ghat Steps, Confetti cannons, Stage lights, Tap pads, Beat paint.
- Avatars: avatar-hiyori (Live2D), avatar-vrm / avatar-vrm-engine, vrm-dance.
- Old built-in game.js mini-games (replaced by Neolution).

## Dance motion clips added 2026-11-10 (dancefix)

15 more motion-capture clips from the open-vrma dataset (https://huggingface.co/datasets/Sanami/open-vrma, converter
https://github.com/sanamiy/open-vrma), same source and licence as the v80 clips: cmu_111_05, cmu_113_04, cmu_120_06,
cmu_120_07, cmu_143_35, cmu_55_02, cmu_60_01, cmu_60_02, cmu_94_03, cmu_94_14, cmu_05_12, cmu_49_09, cmu_90_30, cmu_85_04,
cmu_85_11 (files in assets/dance/). Licence: LicenseRef-CMU-Mocap. "The data used in this project was obtained from
mocap.cs.cmu.edu. The database was created with funding from NSF EIA-0196217." See assets/dance/LICENSE-open-vrma.md.

## "Fast" dancer models (assets/chars/vrm/lite/*.vrm.gz)

Lower-texture-resolution, gzip-compressed copies of the existing VRoid sample models already listed above (same
licences/terms as the originals; mesh, rig and VRM metadata unchanged, textures downscaled to <=1024 px).

## AMD FidelityFX Super Resolution 1 (FSR 1) — EASU + RCAS (enhance-20261111)
Used by: `vendor/enhance/enhance.js` (video Sharpen / Upscale). The EASU and RCAS shader algorithms were re-implemented in WGSL (WebGPU) and GLSL ES (WebGL) from AMD's reference `ffx_fsr1.h`.
Source: https://github.com/GPUOpen-Effects/FidelityFX-FSR — License: MIT

Copyright (c) 2021 Advanced Micro Devices, Inc. All rights reserved.

Permission is hereby granted, free of charge, to any person obtaining a copy of this software and associated documentation files (the "Software"), to deal in the Software without restriction, including without limitation the rights to use, copy, modify, merge, publish, distribute, sublicense, and/or sell copies of the Software, and to permit persons to whom the Software is furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE SOFTWARE.
