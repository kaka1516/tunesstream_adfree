# Music Stream games — credits & licences

`game.js` (msgame-2) is **original vanilla JS** written for Music Stream. No third-party source code,
assets, sounds, fonts or charts were copied. The projects below were opened on 2026-11-06 and their licence
verified from the repository (GitHub licence metadata / LICENCE file). They were used for **design ideas only**
unless stated otherwise.

| Project | URL | Licence (verified) | What we took | Idea / code |
|---|---|---|---|---|
| claudetarhero (petehottelet) | https://github.com/petehottelet/claudetarhero | MIT | Map per-band spectral flux to lanes (they use 5 bands → 5 frets; we use 4 bands → 4 lanes), adaptive-threshold onset picking, difficulty = onset-density filter + anti-jack lane clamping, chords on strongest hits | Idea |
| realtime-bpm-analyzer (dlepaux) | https://github.com/dlepaux/realtime-bpm-analyzer | Apache-2.0 | Live tempo from inter-onset intervals folded into one octave and histogram-voted (our version: 80–160 BPM fold, ±18 ms buckets, slow blend) | Idea |
| Meyda | https://github.com/meyda/meyda | MIT | Spectral-flux feature definition (sum of positive magnitude change per frame) on Web Audio `AnalyserNode` data | Idea |
| AutoRhythm (Garlov) | https://github.com/Garlov/AutoRhythm | MIT | Rhythm game that generates its own note maps from frequency content; per-song scoring | Idea |
| osu! (ppy/osu, game client) | https://github.com/ppy/osu | MIT (code; osu! resources are separately licensed and were NOT used) | Approach-circle (shrinking ring) read for Beat Tap; Taiko ruleset concept: two hit types (centre “don” / rim “ka”), big notes, ~300/100/miss judgement tiers, combo multiplier | Idea |
| Piano-Tiles (AJLoveChina) | https://github.com/AJLoveChina/Piano-Tiles | MIT | 4-column falling-tile layout & D F J K / 1–4 keymap convention (also used by zardoy/piano-tiles, MIT) | Idea |
| Js-Interpreter-GeometryDash (F6Exp) | https://github.com/F6Exp/Js-Interpreter-GeometryDash | MIT | Minimal GD-style loop: auto-scroll, gravity jump, spikes, score | Idea |
| geometry-dash (jonathanleahy) | https://github.com/jonathanleahy/geometry-dash | README says MIT, but **no LICENSE file** in repo → treated as unlicensed; only the generic genre ideas (rotating cube while airborne, jump buffering, orbs) which are not copyrightable | Idea only (no code viewed/copied) |

## Looked at and deliberately NOT used
- **Frets on Fire** — https://github.com/fretsonfire — GPL-2.0/GPL-3.0. Genre reference only (lane highway is a generic mechanic); no code or assets.
- **osu-web** — https://github.com/ppy/osu-web — AGPL-3.0. Not used.
- **taiko-web (bui)** — source pulled after a legal request from Bandai Namco (Jan 2023); licence status unclear → not used at all.
- **opendash** (Hassunaama) — GPL-3.0. Not used.
- No proprietary charts (Guitar Hero, Clone Hero, Taiko no Tatsujin, Beat Saber, Geometry Dash levels) are included. All charts are generated live from whatever song is playing.

## How the live charting works (our own design)
1. A second, low-smoothing `AnalyserNode` (fft 1024, smoothing 0.25) is fanned out from the player's `MediaElementSource`
   (`window.__msSrc`) through a zero-gain node; the playback graph is untouched. Falls back to `window.msAnalyser` / `__msAnalyser`.
2. Per frame: band levels + positive spectral flux for bass 30–150 Hz, low-mid 150–600, mid 600–2.5k, treble 2.5–9k.
   Onset = weighted flux > mean + 1.25·sd over ~0.7 s; the dominant band (flux ÷ its running mean) is the onset's “colour”.
   Onset times are shifted by `outputLatency + baseLatency` so notes land when the sound is heard.
3. Tempo from inter-onset histogram; phase nudged toward strong onsets.
4. **Bar echo:** each future 8th-note slot copies the strongest onset found at the same position 1–3 bars earlier.
   Music repeats bar-to-bar, so notes coincide with the song, and every song / section gives a different chart.
5. Difficulty filters slots (Easy ≈ half-notes + strong beats, Normal = beats with onsets, Hard = all onsets incl. 8ths),
   scroll speed and hit windows (Easy 75/160 ms, Normal 55/125, Hard 42/100 perfect/good).
6. No analyser, silence or paused music → deterministic song-seeded 4-bar pattern at the tempo timer (120 BPM,
   adapting to the player's own steady tapping).

## msgame-4 (Dance Battle, Character Runner, Rhythm Fight)
No third-party code, art, charts or assets were added. The genre mechanics are generic and not copyrightable: copy-the-leader dance arrows, jump/slide endless runner, and timed punches on approach rings. The placeholder silhouette (a canvas stick figure with joint-angle forward kinematics and pose blending) and the `MSGame.registerCharacter` adapter API are original to this project. No AGPL/GPL sources were consulted for v4. Future VRM/three.js avatars must arrive as separately licensed adapters (three.js and @pixiv/three-vrm are MIT; check each model's own VRM licence).


## msgame-4.1 — Live2D characters (Hiyori, Haru, Mao, Rice)
| Component | Source | Licence | Use |
|---|---|---|---|
| Hiyori, Haru, Mao, Rice models | Live2D Cubism Web Samples (`Samples/Resources/*`) | Live2D Free Material License + Live2D Sample Model Terms (each folder has `LIVE2D_LICENSE.md`) | Redistributed unmodified art; only `model3.json` refs fixed (Haru sound refs removed, Haru/Mao Pose refs restored). Mark, Wanko, Ren, Natori not shipped. |
| Live2D Cubism Core (`live2dcubismcore.min.js`) | Live2D Inc. | Live2D Proprietary Software License (Redistributable Code) | Runtime |
| pixi-live2d-display 0.4.0 (cubism4 build) | https://github.com/guansss/pixi-live2d-display | MIT; bundled Cubism 4 Web Framework (guansss/CubismWebFramework @1f9cdfd) is under the Live2D Open Software License (`assets/chars/lib/LICENSE-CubismWebFramework-cubism4.md`) | Runtime (`assets/chars/lib/LICENSE-pixi-live2d-display.txt`) |
| PixiJS 6.5.2 | https://github.com/pixijs/pixijs | MIT | Runtime (`assets/chars/lib/LICENSE-pixi.txt`) |

Business-use note: Live2D requires a Cubism SDK Release License for businesses with annual revenue ≥ ¥10M.

**Dance motions:** no third-party `.motion3.json` files were added. Beat-synced moves (hip-sway idle, nod/shoulder pop,
4-count arm pattern, winks, kisses, pouts, spins, drop poses) are authored procedurally in `assets/chars/live2d.js`
on each model's own parameters, expressions and its bundled `TapBody` motions.

## Groove Brawl — design inspiration only
| Work | Licence | What we took |
|---|---|---|
| *Dead as Disco* (Brain Jar Games) — rhythm beat-'em-up | Proprietary (commercial game) | **Design inspiration only**: the genre idea of a brawler where strikes, dodges and counters land on the beat. No code, art, audio, names, characters, UI or branding used; all names (Groove Brawl, Groove Break, the Dropper, mosh/hype foes) are our own. |

## msgame / Stage — VRM dancers + expanded Live2D (ms-v71)

### VRM models (`/assets/chars/vrm/`)
| File | Licence | Notes |
|---|---|---|
| Darkness_Shibu, Vivi, Sendagaya_Shibu, Victoria_Rubin, Vita, Sendagaya_Shino, HairSample_Female | **CC0** (VRoid β samples) | https://vroid.pixiv.help/hc/en-us/articles/4402614652569 |
| AvatarSample_A, AvatarSample_B | VRoid sample terms (free use/alter/free redistrib; do not set CC0; do not sell sample VRM) | https://vroid.pixiv.help/hc/en-us/articles/4402394424089 |
| ~~Runa_Inoue~~ | **Withdrawn in ms-v77, not shipped or served.** The GitHub release is MIT, but the file's own embedded VRM meta says `allowedUserName: OnlyAuthor`, and the author's table says "Impersonating models: Not allowed" and "Usages on VRoid-linked app: Not allowed". These cannot be reconciled from the sources. The original file is kept privately outside the web root (`<private-folder-outside-the-repo>/vrm/`). | https://github.com/Runa-Chin/runa-inoue-vrm |

### VRM dance motion (ms-v77)
**Original procedural choreography** in `vendor/ms/vrm-dance.js`, written for Music Stream (original code; project licence not yet chosen, see `THIRD_PARTY_NOTICES.md`). It is not a
port and not derived from any motion file, motion pack or captured performance. Standard VRM humanoid bones are rotated with
sine/ease curves driven by the audio analyser (beat phase, BPM, energy, drop) or an idle clock. Moves: groove, pump, clap-step,
overhead sway, idle breathing, tap wave, drop spin.

**Withdrawn: pixiv VRoid Project VRMA 7-set** (used up to ms-v76). Its terms (Readme §2) forbid distributing the motions "in a way
that can be rigged or extracted" and forbid use "for specific religious beliefs or political purposes". A web server hands the raw
files to every browser, and any package or image contains them. Putting them behind auth would not make that permitted. So in ms-v77:
- The files were moved byte-for-byte (sha256 verified) to `<private-folder-outside-the-repo>/vrma/`, outside the served and packaged tree.
  `/assets/chars/vrma/*` now returns 404.
- The runtime no longer references them: no loader plugin, no clip list, no import-map entry, no credit line needed.
- `.dockerignore` and `.gitignore` exclude them. `scripts/check-restricted-assets.sh` (also run in the Dockerfile) fails if any
  `.vrma` or Runa file is found.

### Runtime
| Lib | Licence |
|---|---|
| three.js 0.170 | MIT (`/vendor/three`) |
| @pixiv/three-vrm 3.3.4 | MIT |
| @pixiv/three-vrm-animation 3.3.4 | MIT. Vendored but unused since ms-v77 (no motion files). |

### Additional Live2D (`/assets/chars/`)
| Model | Licence |
|---|---|
| Mao Pro, Shizuku, Koharu | Live2D Free Material License + Sample Data Terms |
| Cyannyan | **CC BY-SA 4.0** — https://github.com/jupiterbjy/Live2DPractice-Cyannyan (character rights: Cyannyan) |
| Arch-chan | **CC0 1.0** — https://github.com/Speykious/arch-chan |
| Amahane Hikari / SuJiangXue | Model Attribution + No-AI License 1.0 — https://github.com/luomo66ccff/Amahane-Hikari-Live2D (credit required; no AI/ML training on assets) |

### Cubism 5 web path (Amahane)
| Lib | Licence |
|---|---|
| untitled-pixi-live2d-engine 1.4.0 | MIT for the engine code; its bundled Cubism Web Framework part is under the **Live2D Open Software License** (not MIT). Locally modified, see `assets/chars/lib/cubism5/NOTICE.md` |
| PixiJS 8.22.0 | MIT (bundles earcut ISC, tiny-lru BSD-3-Clause and MIT deps; `licenses/pixi.js-8.22.0-bundled-deps.txt`) |
| live2dcubismcore.06.min.js | Live2D Proprietary Software License (Redistributable Code) |

Tasteful playful reactions only (winks/smiles/bouncy demo). No erotic content (Live2D sample terms + house rule).

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
