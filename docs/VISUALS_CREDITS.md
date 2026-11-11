# Visualizer credits (ms-v75)

| Mode | Code origin | Licence | Upstream |
|---|---|---|---|
| Neon Bars | JS port of Wave.js `src/animations/Lines.ts` + `src/util/AudioData.ts` + `src/util/Shapes.ts` (glow, gradient) | MIT, © 2023 Austin Michaud | https://github.com/foobar404/wave.js @ `7ed12c4fc32c3174e08e7622e34c47282919a888` |
| Spectrum (circular) | JS port of Wave.js `src/animations/Shine.ts` | MIT (same) | same |
| Glow Waves | JS port of Wave.js `src/animations/Wave.ts` (center, mirrored); **spark particles are original Music Stream code** | MIT (port) / project code | same |

Licence text: `vendor/ms/LICENSE-wave.js.txt` and the header of `vendor/ms/neonviz.js`. Licence verified 2026-11-08 via
GitHub API (`license.spdx_id = MIT`) and the repo `LICENSE` file at that commit. Input is the player's real Web Audio
`AnalyserNode` (frequency bytes per frame); no synthetic signal. Not used: Renderforest (pre-rendered, licensed),
Rainmeter/Wallpaper Engine skins (mostly CC BY-NC-SA or store-licensed) — "Rainmeter/Wallpaper Engine-style" describes the
look only. Existing modes (Ring, Particles, Bars, Wave, Stage) predate ms-v75; MilkDrop (butterchurn, MIT) was removed from the player on 2026-11-11; its vendored files remain on disk, unused.

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
