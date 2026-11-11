# Music Stream — Visual Direction: Visualizer, Dancers, Interaction, Toys
Owner: Product Design (art direction) · 2026-11-06 IST · Status: v1 spec for builder
Scope: box only, `player.html` is implemented by the builder from this doc. Design did not touch player.html, the server, or :8120.
Styles in scope: **Hollywood** (Western pop / hip-hop / EDM), **Tollywood** (Telugu film), **Kollywood** (Tamil film). All poses are original and generic. They do not copy any named choreography, actor, or existing character.

---
## 0. Honest constraints (read first)
- **Audio access.** `player.html` already has `AC.createMediaElementSource(AUD)` → `window.__msSrc`, and line ~1299 makes an `AnalyserNode` (fftSize 2048). Media must stay **same-origin** (server-proxied `/audio`, `/stream`) or CORS + `crossorigin=anonymous`. Otherwise the analyser returns zeros. **Video mode:** if the video element isn't routed through the same AudioContext, the viz has no signal. In that case use the idle groove (below) and hide the beat-sync claims.
- **Beat/BPM is approximate.** Use onset energy (spectral flux on 40–180 Hz plus 180–2k Hz), an adaptive threshold, and autocorrelation of the onset envelope over the last ~8 s at 60–180 BPM. Fold results to 70–140 for the dancers. Use a median of the last 5 estimates and a confidence of peak/mean. Expect **half/double-tempo errors**, especially on dhol/thappu/tabla syncopation, rubato intros, and ambient tracks. A stable reading takes ~6–10 s after play or seek.
- **Fallback idle groove.** If confidence < 0.3 for 4 s, or there is no signal, run the internal 96 BPM clock. Dancers use `idle_sway`, and intensity follows RMS only.
- **Mood = heuristics, not ML.** Mood comes from tempo, RMS energy, bass ratio, spectral centroid, onset density, and optional title/channel keywords plus language. It will be wrong sometimes, so the user can always pin a scene.
- **Key detection** (for toys) uses a 12-bin chroma average vs Krumhansl major/minor profiles. It is approximate. Below confidence, fall back to a neutral **major pentatonic on C** (always consonant-ish).
- **Album-art palette** needs a same-origin thumbnail (the `/art` proxy). A cross-origin `ytimg` taints the canvas, so fall back to skin tokens.
- **Measure, don't claim.** Every perf number below is a gate to be measured with the harness in §6. None of them is a promise.

## 1. Signal layer (shared by all scenes, dancers, toys)
Sample the analyser once per rAF (desktop) or every other frame (phone). Outputs, all smoothed (EMA α≈0.2 unless noted):
| feature | definition |
|---|---|
| `bass` | mean dB→lin of bins 40–150 Hz, 0..1 normalized by a rolling 10 s max |
| `mid`, `high` | 150–2k Hz, 2k–10k Hz, same normalization |
| `energy` | RMS of time-domain, 0..1 rolling-normalized |
| `centroid` | spectral centroid Hz → 0..1 over 200–5000 Hz (log) |
| `onset` | event: flux > median(1 s)·1.5 + 0.02, refractory 120 ms; `strength` 0..1 |
| `bpm`, `conf` | ACF tempo (above), confidence 0..1 |
| `beatPhase` | 0..1 PLL: advances at bpm; on onset within ±80 ms of predicted beat, nudge phase 10% toward it |
| `bar` | beat counter mod 4 (downbeat guess = strongest-bass beat of the last 4; approximate) |
| `drop` | event: energy rises > +0.35 in < 1 beat after ≥ 4 beats of energy < 0.4 (build-up→drop) |
| `lyricLine` | event from existing synced-lyrics code (only when synced lyrics exist) |
| `chroma[12]`, `key`, `keyConf` | 8 s chroma average → key estimate (for toys) |
On **pause**, freeze the features and decay the visuals to calm over 600 ms. On **seek**, clear the onset/ACF history, keep the last bpm as a prior, and set conf=0 until re-lock. On **track change**, also reset the palette and mood.

### Mood + style classifier (heuristic)
- **Style:** Telugu script (U+0C00–0C7F) or `telugu|tollywood` in the title/channel/existing famlang tag → `tollywood`. Tamil script (U+0B80–0BFF) or `tamil|kollywood|kuthu` → `kollywood`. Otherwise `hollywood`.
- **Mood:** scores are updated every 2 s, and the result needs 2 consecutive agreeing windows before it changes (hysteresis).
  - `devotional`: keywords (`bhakti|stotram|aarti|bhajan|mantra|devotional|keerthana|suprabhatam`), or calm + low centroid
  - `energetic`: bpm ≥ 115 && energy ≥ 0.55 || onset density ≥ 2.5/s
  - `romantic`: 70–110 bpm, mid-dominant, keywords (`love|prema|kadhal|manasu|heart`)
  - `sad`: bpm < 90, energy < 0.35, low centroid, keywords (`sad|alone|pain|soga|baadha`)
  - `calm`: everything else that is low-energy

## 2. Scenes (6 original concepts; none are bars)
The palette rule is shared and described after the table.
| # | Scene | Best moods / styles | Renderer | Motion language |
|---|---|---|---|---|
| S1 | **Marigold Burst** | energetic; Tollywood/Kollywood mass songs | Canvas2D | Petal/streamer particles fall at a speed ∝ bpm. Onset → radial petal burst from the stage floor. Bass → floor rangoli-ring scale 1.0–1.08. Downbeat → ring rotates 1/16 turn. Drop → full confetti cannon pair (toy T5 reuse). |
| S2 | **Neon Ghat Steps** | energetic/EDM; Hollywood dance, remixes | WebGL (fallback 2D) | Receding stepped terraces in neon outline (an original "steps-to-water" geometry, not a synthwave copy). Lines scroll toward the viewer once per beat. Bass → glow width. Highs → water shimmer noise. Drop → camera dips 1 step plus a bloom flash (luminance-capped). |
| S3 | **Ink Monsoon** | sad, calm; any | WebGL, low-res feedback buffer 0.5× | Ink blots bloom and diffuse (curl-noise advection). Rain streak density ∝ high. Each lyric line change drops one large ink bloom at a random third. Onsets add only ripples, never flashes. |
| S4 | **Paper Kite Sky** | pop, romantic, upbeat; Hollywood pop, film melodies | Canvas2D (matches Side Cut) | 3–4 parallax paper-cut layers (hills, rooftops, clouds) sway on half-beats. Kites tug up on each beat with string catenary. The sun disk uses the album dominant color and pulses with bass. Lyric line → a kite changes color. |
| S5 | **Lamp Orbit** | devotional, calm | Canvas2D | Concentric rings of small lamp flames orbit at bpm/8 revolutions per bar and "breathe" at a period of 2 beats. Sustained energy → a slow golden spiral trail. High-band onsets → tiny bell-sparkles. No strobe at all. |
| S6 | **Night Tape Bokeh** | romantic, sad, lo-fi; any | Canvas2D (prebaked bokeh sprites) | Soft bokeh discs drift; size ∝ mid. A cassette-reel ring spins at bpm/60 rps. Film grain and light leak cross once per bar. On beat → slight focus breathe. |
**Auto** (default) picks the scene from the mood:
- energetic → S1 (film styles) or S2 (hollywood)
- romantic → S4/S6
- sad → S3
- devotional → S5
- calm → S6
Changes happen only at track change or after 30 s of stable new mood, with a 1.2 s crossfade.

### Palette rule (all scenes)
1. Draw the art thumbnail at 32×32 to an OffscreenCanvas. Run k-means k=5 in OKLab with 8 iterations, seeded by the median-cut top-5.
2. Assign roles:
   - `bg` = the darkest populous cluster, clamped to OKLCH L ≤ 0.18 (dark stage) or L ≥ 0.92 for Side Cut paper scenes.
   - `primary` = the highest population × chroma.
   - `secondary` = the next cluster ≥ 40° hue away (else rotate primary by 150°).
   - `glow` = primary at L 0.75, C ×1.2.
3. **Contrast guard:** glow/particles vs bg ≥ 3:1 and any text ≥ 4.5:1. If a check fails, step L in OKLCH by 0.05 until it passes. Clusters with chroma < 0.03 can't be accents.
4. **Fallback:** the skin tokens `--acc --tom --mus --cob` on `--bg`.
5. Recompute only on track change and transition over 800 ms.

### Skin integration
| Skin | Viz treatment |
|---|---|
| Side Cut | paper-grain overlay (existing `textures/paper.svg`), 2 px riso offset ghost on dancers, `--ink` outlines |
| Classic Deck | 2 px scanline overlay, pixel-snapped transforms, 4 px black outlines, faceplate label "VIS" in VT323 |
| Glass Stage | soft glow (shadowBlur ≤ 12 desktop / 0 phone), translucent 2 px outlines; `html.solid` → no glow |

## 3. Dancers (original chibi cast; layered SVG rig)
Files are in `assets/dancers/` (§9). All art is original and CC0.
| id | Name | Home style | Silhouette / outfit | Base palette |
|---|---|---|---|---|
| `tara` | **Tara** | Tollywood mass | tall swept high ponytail + hair-clip, cropped jacket with mirror dots over a yellow top, flared pants, drop earrings | red/amber/gold |
| `kavi` | **Kavi** | Kollywood kuthu | round curly mop, checked short-sleeve shirt with rolled sleeves, towel-scarf over shoulder, shorts, white sneakers | teal/cream/orange |
| `rivo` | **Rivo** | Hollywood pop/hip-hop/EDM | spiky violet hair with pink visor band, oversized dark hoodie with pocket, neck headphones, joggers, chunky sneakers | charcoal/mint/pink |
**Recolor:** parts use `style="fill:var(--d-main,#hex)"` slots (`--d-skin --d-skin-sh --d-hair --d-main --d-alt --d-trim --d-line --d-eye --d-blush`).
- At load, the runtime string-replaces the vars with the resolved palette.
- `--d-main/alt/trim` = 50% mix of the character base and the album `primary/secondary/glow`.
- Skin and hair are **never** taken from album art. Offer 4 user skin-tone presets.
- `--d-line` comes from the skin outline rule.

### Rig (`rig.json`)
- **Joints:** root(hip) → torso → head; torso → uarmL/R → larmL/R → handL/R; root → thighL/R → shinL/R.
- **Pivots** (px @1x, y down): neck (0,−58), shoulders (±20,−50), elbow +24, wrist +22, hips (±11,0), knee +26. Ground is y=+60.
- **Angles:** degrees. **R joints are mirrored** (renderer negates), so +value always means outward/up. A part's local (0,0) is its pivot, and R parts reuse the L file with `scale(-1,1)`.
- **Draw order** is given in `rig.json`. Z-rule: if `uarmR > 120`, the back arm draws over the head.
- **Variants:** hands `open|fist|point|flick` (pose keys `gripL/gripR`) and faces `smile|grin|closed|wink`.
- **Render path:** each part is rasterized once to an `ImageBitmap` at DPR-capped scale. Each frame runs `ctx.setTransform` along the chain plus `drawImage`. There is no DOM SVG per frame, and ~17 drawImage per dancer.
- **Reference math:** `tools/build_dancers.py` `compose()` and `sample()` show exactly how the previews were made.

### Pose JSON (`moves/<id>.json`)
```json
{"id":"tl_mass_stomp","name":"Mass stomp","style":"tollywood","beats":2,"loop":true,"oneShot":false,
 "keys":[{"t":0,"ease":"inOut","rootX":0,"rootY":6,"rootRot":0,"torso":0,"head":0,
          "uarmL":30,"larmL":40,"uarmR":30,"larmR":40,"thighL":28,"shinL":-20,"thighR":10,"shinR":-2,
          "gripL":"fist","gripR":"fist","face":"grin"}, ...]}
```
- `t` is the phase within the move (0..1 over `beats` beats). It is driven by `beatPhase` and the beat counter, never by wall-clock while conf ≥ 0.3.
- `ease`: `inOut` (smoothstep) or `snap` (cubic-out, used for hits that should land on the beat).
- Omitted joints use the neutral pose. Strings switch at u=0.5.
- When moves change, blend 1 beat between them.
- Secondary motion: the hair/ponytail/towel spring lag is a cheap 1-DOF spring on the head angle. This is optional.

### Move sets (bands → `characters/<id>/moveset.json`)
**Band selection:**
| band | condition |
|---|---|
| idle | conf < 0.3 |
| calm | energy < 0.3 or mood ∈ {sad, devotional} |
| low | < 0.5 |
| mid | < 0.75 |
| high | ≥ 0.75 |

`accent` is a one-shot on `drop` or an onset strength > 0.9 (max once per 8 beats). Within a band, rotate moves every 8 bars. If the track style ≠ the home style, 50% of picks are borrowed from that style's list (`borrowWhenStyleDiffers`). For example, Rivo does kuthu steps on a Tamil track.

| Character | calm | low | mid | high | accent | tap | special |
|---|---|---|---|---|---|---|---|
| Tara | calm_breathe, hw_body_roll | tl_shoulder_shake, hw_bounce_step | tl_hook_loop, tl_slide_point, tl_collar_flick | tl_mass_stomp, tl_fast_footwork | tl_victory_v | tara_tap_cheer | tara_special |
| Kavi | calm_breathe, kl_folk_hip_sway | kl_heel_clap, kl_mass_entry | kl_drum_mime, kl_folk_hip_sway, kl_scarf_twirl | kl_kuthu_step, kl_wrist_flick | tl_victory_v | kavi_tap_cheer | kavi_special |
| Rivo | calm_breathe, hw_body_roll | hw_shoulder_bop, hw_bounce_step | hw_step_clap, hw_arm_wave, hw_body_roll | hw_fist_pump, hw_shuffle_kick | hw_drop_point | rivo_tap_cheer | rivo_special |
All three have `idle_sway` for idle.

**Move library** (30 files; keyframe poses described):
- **Hollywood:**
  - `hw_bounce_step`: side-to-side two-step with knee dips on the "and"
  - `hw_body_roll`: torso wave with a counter head tilt
  - `hw_arm_wave`: arms out with alternating elbow ripple
  - `hw_fist_pump`: fist up, snap down with a dip, 1 beat
  - `hw_shuffle_kick`: alternating knee kicks, snap
  - `hw_step_clap`: step with a clap on the 2 and 4
  - `hw_shoulder_bop`: alternating shoulder lift with a head nod
  - `hw_drop_point`: crouch → spring up pointing high, one-shot
- **Tollywood:**
  - `tl_mass_stomp`: wide alternating stomps, fists low, heavy root drop
  - `tl_hook_loop`: one hand loops over the head with a flicked wrist, the other on the hip, hip bounce on the off-beat (generic hook-step shape)
  - `tl_fast_footwork`: double-time heel-toe alternation
  - `tl_shoulder_shake`: quarter-beat shoulder alternation
  - `tl_collar_flick`: flick at the collar → snap point out
  - `tl_slide_point`: lateral slide with alternating points
  - `tl_victory_v`: crouch → V arms, wide stance, one-shot
- **Kollywood:**
  - `kl_kuthu_step`: alternating high knee-lift + stomp, bent swinging arms (percussive kuthu-style footwork)
  - `kl_drum_mime`: alternating down-hits as if playing a frame drum
  - `kl_folk_hip_sway`: hip sway with open-hand wrist flourishes, eyes closed
  - `kl_wrist_flick`: overhead wrist flicks on the off-beats
  - `kl_mass_entry`: half-time swagger stride with arms swung open (intro and first 8 bars)
  - `kl_heel_clap`: heel bounce clap
  - `kl_scarf_twirl`: overhead circle (Kavi's towel follows via spring)
- **Shared:** `idle_sway`, `calm_breathe` (palms together, breathing)
- **Interaction:**
  - `*_tap_cheer`: 1 beat, one per character
  - `*_special`: 4 beats, one per character
    - Tara: spin-out to point pose
    - Kavi: towel swing to knee-drop stomp
    - Rivo: freeze-hit robot sequence

## 4. UI: switcher, toggle, intensity, reduced motion, mobile layout
- **Entry:**
  - Now-playing stage gets a **Visuals** button (new sprite `i-viz`; packs that lack it fall back to the default sprite; the existing 16 + i-brand ids are unchanged).
  - **Desktop:** the button opens a popover. **Mobile:** it opens a section in the existing **More** sheet.
- **Controls** (all ≥ 44×44 px, chips with min-width 64):
  - **Visuals on/off** switch (default ON in audio mode, OFF in video mode)
  - **Scene:** `Auto` + 6 cards. Each is a static thumbnail drawn from the palette; reuse the skin-card pattern from the picker.
  - **Dancers:** `None / Tara / Kavi / Rivo / Crew (all 3)`
  - **Intensity:** segmented `Low · Med · High` (scales particle count, motion amplitude, bloom)
  - **Style lock:** `Auto · Hollywood · Tollywood · Kollywood`
- **Skins:** chips/cards inherit the skin tokens (`--r-pill --card --line --font-disp`). Classic Deck draws the cards as beveled tiles. Glass Stage uses frosted cards, which become solid under `html.solid`.
- **Mobile layout (390 px):**
  - The viz canvas replaces the art area inside the video-first stage. Its box is `min(100vw, 56svh)` square or 4:5 when lyrics are collapsed.
  - Dancers occupy the bottom 38% of the canvas with a 12 px safe inset.
  - **The transport row, seek bar, and title are outside the canvas.** The canvas never overlaps them, and they keep their own touch handling.
  - Respect `env(safe-area-inset-*)`.
- **Reduced motion** (`prefers-reduced-motion` or the in-app toggle):
  - A static scene "poster" frame renders once per track/palette change.
  - Dancers hold a pose with a gentle 0.98↔1.0 scale pulse at most once per second.
  - No particles, no camera moves, no flashes.
- **Photosensitivity (always on):** no full-frame luminance change > 20% more than 3×/s, and bloom flashes are capped at 1 per beat with ≤ 150 ms rise.
- **Persist:** `localStorage['ms.viz'] = {on, scene:'auto', dancers:['tara'], intensity:'med', style:'auto', dancerPos:{tara:[x,y]}, toys:{…}}`

## 5. Interaction (mobile touch first)
**Input model:** use Pointer Events only (`pointerdown/move/up/cancel`) on the viz canvas.
- `touch-action: none` goes **on the canvas only**. Page scroll, seek, transport, lyrics, and More-sheet gestures live outside the canvas and are never captured.
- Use `setPointerCapture` only after a drag threshold of 8 px, so a tap stays a tap.
- **Edge guard:** ignore pointerdown within 16 px of the canvas bottom edge (protects the seek bar zone) and of the screen edges (OS back-swipe).
- **Multi-touch cap:** 2 active pointers for gestures, and at most 5 queued tap effects per second.
- **Gesture table:**
| Gesture | Result |
|---|---|
| Tap empty stage | burst (scene-specific: petal pop / neon ring / ink drop / kite flutter / lamp sparkle / bokeh pop) at the touch point. **Quantize** (setting, default on when conf ≥ 0.5): the burst is scheduled for the next 1/8-beat. Otherwise it is immediate. |
| Tap a dancer | that dancer plays `*_tap_cheer` (1 beat, starting on the next beat) + a small sparkle. Max 1 per beat per dancer. |
| Double-tap or long-press (500 ms) a dancer | `*_special` (4 beats). Cooldown 4 bars. Long-press shows a radial "hold" ring. |
| Double-tap empty stage | reset the camera/bend to default (spring 400 ms) |
| Drag empty stage (1 finger) | bend/rotate scene: yaw ±25°, pitch ±12° (parallax layers / 3D camera in S2). Inertia: velocity decays at a damping of 4/s. Springs back to neutral after 3 s idle. |
| Pinch (2 fingers) | zoom 0.9–1.3×, clamped. Two-finger twist rotates S5 ring speed ±50%. |
| Drag a dancer | reposition along the stage floor band (x 10–90%, y clamped to floor band 62–92%). Snap to 3 lanes when Crew. Saved to `dancerPos`. |
| Horizontal swipe on a dancer (> 60 px, < 300 ms) | swap to the next character in that slot |
| Pointer hover/move (desktop) / touch-hold position | shapes visuals: S1 wind direction, S2 light-source/vanishing point, S3 flow-field attractor, S4 kite pull, S5 orbit center offset (±10%), S6 focus point. Hue shift ±15° by x-position (contrast guard re-run). |
- **Picker sheet:** a dancer slot's "⋯" chip (44 px) opens a bottom sheet with character cards, the same list as §4.
- **Haptics (optional, guarded):** `if ('vibrate' in navigator && settings.haptics && !reducedMotion) navigator.vibrate(12)` on tap-cheer and special only. iOS has no support, which is expected.
- **Keyboard / a11y:**
  - The canvas has `tabindex=0`, `role="application"`, and `aria-label="Visualizer stage"`, with a visible focus ring.
  - Keys: `Space` is **not** captured (it stays play/pause). `B` = burst at center. `1/2/3` = select dancer slot. `C` = cheer. `S` = special. Arrows = move the selected dancer / bend when none is selected. `0` = reset view. `V` = cycle scene. `Esc` = deselect.
  - An `aria-live="polite"` region announces "Tara: special move" (throttled 1 per 2 s).
  - All gesture results also have buttons in the Visuals panel, so nothing is gesture-only.
- **Reduced motion:**
  - Taps make one soft static glow (no particles).
  - Cheer/special become a single pose change held for 1 beat.
  - Bend and drag inertia are disabled (direct, no spring).
  - Haptics stay on only if the user explicitly enables them.
- **Perf budget for interaction:**
  - ≤ 1.5 ms/frame added on phone.
  - Tap bursts use a shared particle pool (counts toward caps in §6).
  - Pointermove is coalesced to 1 sample per frame (`getCoalescedEvents` not needed). No layout reads in handlers.

## 6. Performance budget (gates, measured)
| | Desktop | Phone |
|---|---|---|
| target | 60 fps, p95 frame ≤ 16.7 ms | 30 fps (rAF throttled to every other frame), p95 ≤ 33 ms |
| viz budget/frame | ≤ 6 ms | ≤ 10 ms |
| DPR cap | 2.0 | 1.25 (WebGL scenes render at 0.6× then upscale) |
| particles (incl. taps, toys) | 600 | 180 |
| dancers | 3 | 3 (Crew drops to 2 on tier-low) |
| analyser read | every frame | every 2nd frame |
- **Renderer:** Canvas2D for S1, S4, S5, S6 (sprites, prebaked gradients, no shadowBlur on phone). WebGL1/2 for S2, S3 (single fullscreen fragment pass + one 0.5× feedback FBO for S3). Without WebGL → the S2 2D line fallback and S3 → S6.
- **Adaptive tiers:** keep an EMA of frame time. If it stays over budget for 2 s, drop a tier: Glass glow off → particles ×0.5 → DPR −0.25 → Crew→2. If it stays under 60% of budget for 10 s, climb back one tier.
- **Pause** when any of these hold: `document.hidden`, the canvas is off-screen (IntersectionObserver), Visuals is off, or audio is paused > 2 s. For a paused audio, draw a calm frame every 500 ms. Release WebGL context on toggle-off.
- **Harness (builder must run, Design will review):**
  - Add `?vizbench=1`. It logs `viz.stats()` every 5 s: `{fps, p50ms, p95ms, tier, particles, bpm, conf}`.
  - Run a 60 s per-scene capture with Playwright on the box at 1280×800 and 390×844 (DPR 3 emulation + 4× CPU throttle).
  - **PASS** = the p95 gates above for every scene with Crew + Med intensity. Report real numbers, not claims.

## 7. Interactive Toys (beyond dancers)
All sounds are **synthesized in Web Audio** (oscillators + noise + envelopes) or own/CC0 samples, never third-party samples.
- Toy audio goes to a separate `toyGain` → destination. It is **never** connected into the analyser path, so it doesn't feed back into beat detection.
- Toy master volume defaults to −12 dB relative to the music.

Ranked by wow vs build cost:
| Rank | Toy | Wow | Cost | Touch | Audio hooks | Perf | A11y / reduced motion |
|---|---|---|---|---|---|---|---|
| 1 | **Confetti & Fireworks Cannons** | ★★★★★ | S | tap = 1 cannon at point; drag = aim arc; long-press = big finale (cooldown 8 bars) | auto-fire on `drop`; launch quantized to beat; colours from palette | pooled particles within caps; no physics beyond gravity/drag | key `F`; RM → single static starburst glyph fade |
| 2 | **Concert Stage + Crowd w/ Aimable Lights** | ★★★★★ | M | drag a spotlight head to aim (2 lights, 1 per finger); tap crowd = wave ripple | crowd bob = beatPhase; lights strobe-free sweep on bars; crowd "jump" on drop | crowd is 1 prebaked silhouette strip, sine-offset per column (no per-person sprites); lights = 2 additive gradients | arrows aim selected light; RM → lights static, crowd still |
| 3 | **Tap-along Pads (drums + "tabla-ish" + key-snapped keys)** | ★★★★☆ | M | 2×4 pad grid sheet over lower stage (each ≥ 64 px), toggles Drum / Hand-drum / Keys | Keys snap to estimated key (chroma, §1) if keyConf ≥ 0.5, else C major pentatonic; optional quantize to 1/16 | pure synth voices, max 8 voices, voice stealing; < 0.5 ms main-thread | keys `A S D F G H J K`; visible labels; RM no change (no motion) |
| 4 | **Beat-Pulse Paint** | ★★★★☆ | S | finger draws ribbon strokes; stroke width/brightness pulses with bass; 2-finger tap = clear | hue drifts with centroid; strokes "breathe" on beats; fade-out over 8 bars | strokes stored as ≤ 2000 points, re-drawn on 1 offscreen layer | keyboard draws a Lissajous auto-stroke; RM → no pulse, static strokes |
| 5 | **Audio Pet ("Bloop")** — original round creature | ★★★★☆ | S | tap = boop (squash + giggle chirp); drag = carry; leave alone = it naps in silence | squash/stretch with bass; ears flick on onsets; sleeps when paused; dances `idle_sway`-like bob | one SVG → 3 bitmaps (body/ears/eyes) | key `P` = boop; RM → blink only |
| 6 | **Lyric Bubbles** (synced lyrics only) | ★★★☆☆ | S | current line's words float as bubbles; tap = pop (sparkle + tick sound); popping never seeks | spawn on `lyricLine`; size by word length; hidden entirely when lyrics are unsynced | ≤ 12 bubbles; text drawn once per bubble to cached bitmap | bubbles are decorative (`aria-hidden`); lyrics panel stays the accessible text; RM → no float |
| 7 | **DJ Filter Pad** (+ "wobble") | ★★★☆☆ | M | XY pad in a sheet: x = low-pass/high-pass sweep (Biquad on output, cutoff 200 Hz–20 kHz), y = resonance Q 0.7–8; release = spring back to bypass in 300 ms | Filter inserted **after** the analyser tap so detection stays clean. **Scratch is NOT real scratching:** only a `playbackRate` wobble 0.92–1.08 for ≤ 400 ms on a gesture, then restore 1.0. It is disabled during seek/buffering and for live/stream sources; never touches `currentTime`. | negligible | keys `[` `]` sweep, `\` bypass; RM n/a (no motion); bypass always visible |
| 8 | **Mood Weather & Scenery** | ★★★☆☆ | S–M | swipe up/down on sky = cycle weather (sun, monsoon, fog, stars); tap sky = lightning (soft, capped) | auto weather from mood (sad→rain, devotional→dawn haze, energetic→clear + glitter, romantic→dusk); rain density ∝ high | overlay layer reused across S1/S4/S6 | key `W`; RM → static weather tint, no lightning |
**Recommended build order (MVP first):**
1. **MVP:** signal layer + S1 Marigold Burst + S4 Paper Kite Sky + Tara/Kavi/Rivo dancers (band moves) + Visuals panel + reduced motion + perf harness
2. Interaction core: tap bursts, dancer tap-cheer/special, drag dancers, camera bend/reset, keyboard map
3. Toy #1 Cannons + #5 Bloop + #4 Paint (all S)
4. S5 Lamp Orbit, S6 Night Tape, #8 Weather
5. WebGL S2 Neon Ghat, S3 Ink Monsoon, #2 Concert Stage
6. #3 Pads (key snapping), #7 DJ Filter, #6 Lyric Bubbles

Toys are mutually exclusive in the lower stage band (one "toy slot"), and cannons/weather/pet can layer on any scene.

## 8. Builder integration contract
Module: `/viz/viz.js`, an ES module with no dependencies. The path is a suggestion and the builder owns it.
```js
const viz = MSViz.init(canvas, analyser, {
  audioEl: AUD, audioCtx: AC, skin: document.documentElement.dataset.skin,
  reducedMotion: matchMedia('(prefers-reduced-motion: reduce)').matches,
  assetsBase: '/assets/dancers/', dprCap: isPhone ? 1.25 : 2, tier: 'auto'
});
viz.setScene('auto'|'marigold'|'neonghat'|'ink'|'kites'|'lamps'|'tape');
viz.setDancers(['tara','kavi','rivo']);         // [] = none; setDancer(id) alias for single
viz.selectDancer(slotIdx|null);                   // keyboard/a11y + highlight ring
viz.triggerMove(slotIdx, moveId|'tap'|'special', {quantize:true}); // returns Promise resolving when move ends
viz.setIntensity('low'|'med'|'high');  viz.setStyle('auto'|'hollywood'|'tollywood'|'kollywood');
viz.setTrack({title, channel, lang, artUrl});     // triggers palette + style/mood reset
viz.onLyric(lineIdx, text);                       // from existing synced-lyrics code
viz.onTransport('play'|'pause'|'seek'|'ended');
viz.onBeat(cb)      // cb({bpm, conf, phase, bar, strength}) → returns unsubscribe
viz.onPointer(cb)   // cb({type:'tap'|'drag'|'pinch'|'dancer-tap'|'dancer-special'|'dancer-move', x, y, slot}) (x,y 0..1)
viz.setToy(null|'cannons'|'stage'|'pads'|'paint'|'pet'|'bubbles'|'djfilter'|'weather', opts);
viz.setSkin(id); viz.setReducedMotion(bool); viz.setVisible(bool);
viz.stats() → {fps, p50ms, p95ms, tier, particles, bpm, conf, mood, style, key, keyConf};
viz.destroy();
```
**Data formats:**
- `rig.json`: joints, pivots, draw order, z-rules, part viewBoxes, palette slots
- `moves/*.json`: pose keys (§3)
- `characters/<id>/character.json`: palette, recolor rules, parts
- `characters/<id>/moveset.json`: bands + borrow lists + tap/special
**Server note:** `music_server.py` currently serves `/skins/`, `/viz-demo`, and `/vendor/`, but **not `/assets/`**. The builder must add a static route (and the rate-limit exempt prefix) or copy the assets under an existing served path. Design changed nothing on the server, and :8120 was not touched.

## 9. Asset inventory (`assets/dancers/`)
```
rig.json
characters/{tara,kavi,rivo}/{character.json, moveset.json, preview.svg}
parts/{tara,kavi,rivo}/ torso head hair_back hair_front uarm larm thigh shin acc_front
                        face_{smile,grin,closed,wink} hand_{open,fist,point,flick}  (.svg)
moves/ 30 pose files (hw_*, tl_*, kl_*, *_tap_cheer, *_special, idle_sway, calm_breathe)
preview.png              contact sheet: 5 poses × 3 characters (rendered from the SVG parts)
tools/build_dancers.py   generator + reference compose()/sample() math; tools/contact.html
```
All of it is generated by `tools/build_dancers.py` (original work, CC0-1.0). Validated: 54 SVGs (51 parts + 3 previews) parse (python xml), and all JSON parses.

## 10. References (inspiration / credit only; no code or presets copied)
- Butterchurn (MIT, WebGL MilkDrop port; already vendored in `/vendor/butterchurn`): https://github.com/jberg/butterchurn. It can optionally be offered as a "Classic Trip" extra scene using its own MIT license. **Don't** ship MilkDrop presets unless each preset's license is verified.
- Shadertoy audio-texture conventions (512×2 FFT/wave texture), useful for the S2/S3 uniform layout: https://gist.github.com/soulthreads/2efe50da4be1fb5f7ab60ff14ca434b8. iq's "Input – Sound" shader is **CC BY-NC-SA** (https://www.shadertoy.com/view/Xds3Rr), so it's reference only and must not be reused.
- Realtime BPM concepts (low-pass ~200 Hz peak-interval; ~10 s to stable; half/double errors): https://www.realtime-bpm-analyzer.com/guide/realtime-bpm-detection. The library is **Apache-2.0**, so it can't be pasted as MIT. Implement our own or vendor it with its license file.
- web-audio-beat-detector (MIT, offline AudioBuffer tempo; useful for downloaded/offline tracks): https://github.com/chrisguttandin/web-audio-beat-detector
- Code-first SVG character rig ideas: Kugutu https://github.com/neka-nat/kugutu, Rigby2D https://rigby2d.com/, Pose Animator (Apache-2.0) https://github.com/yemount/pose-animator. These are concepts only, and no code was used.

## 11. Known limitations / open issues
1. Beat sync is approximate. Half/double tempo is common on Indian film percussion, and the dancers fold to 70–140 BPM.
2. Video mode likely has no analyser signal unless the video audio is routed through `AC`, so the viz defaults OFF there.
3. Mood/style come from heuristics plus keywords, so they will be wrong sometimes. The manual Scene and Style locks are the escape hatch.
4. Key snapping for pads is approximate, with a pentatonic fallback.
5. "Scratch" is only a playbackRate wobble, not real scratching.
6. Front-view FK legs can foot-slide slightly. Optional 2-bone IK on feet is a later polish item.
7. `/assets/` is not yet served (see §8).
8. Perf figures are targets until the §6 harness is run.
9. Dancer art is v1 vector chibi. Further polish passes (more expressions, a back view for spins) are possible.
