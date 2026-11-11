# Music Stream visuals — credits (2026-11-11)

Built as two selectable modes: **Club Stage** and **Cinematic**. (A third, **Trippy** (MilkDrop / Butterchurn), was removed on 2026-11-11; saved Trippy settings move to Cinematic, or Neon Bars without WebGL 2. The `vendor/butterchurn/` files stay on disk but are not loaded.) All of this runs in the browser. If a visual fails, the song keeps playing. Pause still pauses video. No Mixamo assets were downloaded or shipped.

## Modes

| Mode | What you see | Tech | License of new code |
|---|---|---|---|
| Club Stage (`club`) | Neon grid floor, sweeping coloured spots, spectrum bars, sparks, VRM dancer | three.js WebGL dancer + WebGPU backdrop (WebGL2 fallback) | Original Music Stream code |
| Cinematic (`cine`) | Film lighting, slow camera, bokeh, grain, VRM dancer | same stack as Club | Original Music Stream code |
| Dancer (`dance`) | Existing simple stage + mocap dancer (unchanged look) | three.js + three-vrm | Existing |

WebGPU is used for the Club/Cinematic backdrop when the browser supports it; otherwise WebGL2 shaders; if both fail the three.js stage still runs. Auto-quality drops particles, shadows and resolution when FPS is low, then auto-falls back to Neon on a slow phone.

## Motion (new this round)

47 extra dance clips from [open-vrma](https://huggingface.co/datasets/Sanami/open-vrma) / [sanamiy/open-vrma](https://github.com/sanamiy/open-vrma) (conversion + metadata **CC0-1.0**).

- Files: `cmu_05_*` modern, `cmu_49_*` lyrical, `cmu_60_*` / `cmu_61_*` salsa, `cmu_94_*` Indian, `cmu_93_*` Charleston/Lindy, `cmu_85_02` / `cmu_85_12` breakdance, `cmu_90_31` Russian dance.
- Underlying motion: **CMU Graphics Lab Motion Capture Database** (`LicenseRef-CMU-Mocap`). *The data used in this project was obtained from mocap.cs.cmu.edu. The database was created with funding from NSF EIA-0196217.* Free to copy, modify and redistribute; may not be resold as data. BVH conversion by Bruce Hahne (cgspeed).
- Together with the clips already in `assets/dance/`, the library is 111 clips (also **Quaternius Universal Animation Library**, CC0-1.0).

Not used (licence / policy): Mixamo (Adobe terms), AIST++, Motorica, pixiv/VRoid sample VRMA packs, Bandai Namco Research (CC BY-NC).

Moves still switch by tempo and mood, avoid recent repeats, and cross-fade every 8–16 beats (existing `dance3d.js` picker).

## Models

Existing VRoid sample VRMs already in `assets/chars/vrm/` — no new character files this round:

| Model | Licence | Source |
|---|---|---|
| Darkness Shibu, Vivi, Sendagaya Shibu, Victoria Rubin, Vita, Sendagaya Shino, HairSample F | **CC0** | VRoid β samples, https://vroid.pixiv.help/hc/en-us/articles/4402614652569 |
| AvatarSample A, AvatarSample B | VRoid sample terms (free use/alter/redistribute; not CC0; do not sell the sample VRM) | https://vroid.pixiv.help/hc/en-us/articles/4402394424089 |

**Swimwear / romantic outfit:** no clearly adult, original, **and** CC0/CC-BY/permissive swimsuit VRM was found that also allows redistribution in this player. VRoid Hub swimsuit models checked (e.g. モブ子B “水着娘”) are marked adult, but forbid commercial / corporate use, so they were **not** downloaded. Romantic songs keep using the existing dressed CC0 models with lyrical / Indian / salsa mocap.

## HDRIs (Club + Cinematic lighting)

Poly Haven, **CC0 1.0**: https://polyhaven.com/

- `dikhololo_night_1k.hdr` — Club environment
- `studio_small_09_1k.hdr` — Cinematic environment
- `venice_sunset_1k.hdr` — reserved warm alternative

Shipped under `/assets/viz/hdri/` (about 4.6 MB total, 1k, already compact).

## Libraries (already vendored)

- three.js r170 — MIT
- @pixiv/three-vrm and @pixiv/three-vrm-animation 3.3.4 — MIT
- Butterchurn + presets — MIT (`vendor/butterchurn/`)

## New source files

- `vendor/ms/viz-gpu.js` — WebGPU / WebGL2 backdrop
- `vendor/ms/dance-themes.js` — Club + Cinematic three.js environments
- `vendor/ms/dance3d.js` — theme hook, live quality, auto-off callback
- `player.html` — Club Stage and Cinematic buttons (minimal hook; Trippy removed 2026-11-11, backup `player.html.bak-notrippy-20261111`). Backup: `player.html.bak-viz-20261111`

## Auto-update 2026-11-11 10:33 UTC+05:30

- Added 1 dance clip(s) from [open-vrma](https://huggingface.co/datasets/Sanami/open-vrma) (conversion CC0-1.0; underlying motion licence per item): cmu_90_36 (wide leg roll, LicenseRef-CMU-Mocap).

## 18+ visuals pack (2026-11-11 11:29 IST)

- Added a gated 18+ catalog at `assets/dance/adult/` (31 Latin clips: salsa and lambada; LicenseRef-CMU-Mocap via open-vrma, conversion CC0-1.0). Loaded only when an admin enables **18+ visuals** for the user. No compliant swimwear/club VRM character was found; no twerk/pole/dancehall clips were available from allowlisted sources. See `assets/dance/adult/CREDITS.md` for the per-item list.
