# Rainmeter-inspired ideas (credit-only)
Research: 8 November 2026 (IST). Companion to [VISUAL_DIRECTION.md](VISUAL_DIRECTION.md). Proposals only: not built or performance-tested.

## Evidence and originality
No skin packages, art, code, icons, fonts or images downloaded or copied. Public descriptions inform abstract ideas only: create independent geometry, layouts and movement, never trace screenshots or reproduce distinctive artwork. Credits are not product branding. Any later reuse needs separate file-level MIT/CC0 verification, including dependencies and bundled art.

The VSThemes category https://vsthemes.org/en/skins/rainmeter/ returned HTTP 500 again. Individual VSThemes references below were researched through indexed descriptions, not installer inspection. DeviantArt, VisualSkins, Reddit and official documentation supplied other evidence. These are established examples, not a current popularity ranking: indexed DeviantArt pages report about 2.2M views for Monstercat and 3M for Fountain of Colors; community recommendations corroborate VisBubble and Cleartext. Historical views do not establish current active use.

Cost: S ≈ 0.5–1 builder day; M ≈ 2–4; L ≈ 5–8, excluding integration/QA. Wow ranks are subjective visual-interaction impact, 1 highest. Unless stated otherwise: Canvas2D geometry, DOM text/controls, no framework or Rainmeter runtime.

## Fourteen reinterpretations (wow-ranked)

### 1. Petal Halo — M
Reference: configurable radial audio rays in [VisBubble, VisualSkins](https://visualskins.com/skin/visbubble-round-visualizer).
Original: interrupted asymmetric petal wreath around an empty dancer stage, not a copied cover/ray composition. Bass opens petals, highs flutter tips; onsets launch travelling seeds. Finger attracts the closest segment, drag bends the wreath, tap plants a temporary blossom. 48 segments desktop / 24 phone. Fits S1 Marigold Burst and S5 Lamp Orbit. Side Cut: folded paper; Classic Deck: segmented dial; Glass Stage: luminous beads, no phone blur.

### 2. Pluckable Monsoon Ribbon — M
Reference: smooth music-driven string/wave in [VibratingString by SnGmng, indexed VSThemes description](https://vsthemes.org/en/skins/rainmeter/12732-vibratingstring-visualizer.html).
Original: three crossing ink rivers using decimated time-domain samples. Drag displaces a ribbon, release creates a damped visual ripple without changing sound. Bass widens the river; onsets release droplets. S3 Ink Monsoon, calm/sad. Paper ink contours / deck stepped traces / glass translucent ribbons. 64 points per ribbon desktop, 32 phone; no feedback simulation required.

### 3. Orbit Sleeve — M
Reference: circular album art/progress and hover controls in [360 Music by Redsaph](https://www.deviantart.com/redsaph/art/360-Music-for-Rainmeter-%5Bv6.0-%7C-25-Oct-2017%5D-614432622).
Original: square art in an offset sleeve, incomplete exterior orbit and paper comet. Comet position follows actual playback progress; energy changes only the tail. Keep the accessible straight seek slider: no mandatory circular precision gesture. Tap sleeve opens labelled actions, never hover-only. S6 Night Tape Bokeh / S4 Paper Kite Sky. Paper sleeve / deck cartridge / frosted sleeve. Art and text stay DOM; orbit is Canvas.

### 4. Chromatic Terrace — M
Reference: scalable FFT geometry, colour and fading peaks in [Fountain of Colors by alatsombath](https://www.deviantart.com/alatsombath/art/Fountain-of-Colors-desktop-music-visualizer-518894563).
Original: twelve terraces over receding water, not equalizer bars. Log-band energy bends terraces, peaks leave 250 ms reflections. Drag shifts vanishing point ±15 degrees; tap releases a light boat. S2 Neon Ghat Steps, EDM. Paper stairs / deck wireframe / glass emissive edges. Eight terraces and one reflection layer on phones. Canvas perspective first; WebGL only if measured useful.

### 5. Frostline Canopy — M
Reference: adjustable radiant spectrum in [Frost by alatsombath, indexed VSThemes description](https://vsthemes.org/en/skins/rainmeter/8535-frost-visualizer.html).
Original: independently generated branching canopy, eight bands controlling branch tips; transient light travels along branches rather than resizing bars. Pointer pulls canopy gently; tap grows an ephemeral leaf. S4 Paper Kite Sky, romantic/pop. Paper foliage / pixel branches / glass filaments. Cache branches, cap moving tips at 64 desktop / 32 phone. No source branch outlines or textures reused.

### 6. Lyric Lanterns — M
Reference: a dedicated lyric widget in [Simple Lyrics Display by apu889, VisualSkins](https://visualskins.com/skin/simple-lyrics-display).
Original: existing readable current line remains fixed; optional duplicate fragments float as lanterns at scene edges. Tap converts a lantern to a bloom, never removes the readable line or unexpectedly seeks. S5 Lamp Orbit / S3 Ink Monsoon. Use existing authorised lyrics/timestamps only; no invented sync. DOM handles Telugu/Tamil shaping; decorative duplicates are aria-hidden. Four lanterns desktop / two phone. Paper lanterns / deck caption tiles / glass capsules.

### 7. Bass Bloom Core — S
Reference: album-centred radial spectrum in [Bass Beat 2 by azizstark, indexed VSThemes description](https://vsthemes.org/en/skins/rainmeter/14597-bass-beat-2-music-visualizer.html).
Original: six-faceted seed pod beside—not around—the art. Bass expands facets, mids twist the seed, onsets release pollen. Tap blooms it. S1 energetic Telugu/Tamil film tracks or S2 Western EDM. Paper rosette / deck hex core / glass jewel. Six facets and twelve particles on phone. No fixed purple palette or copied composition.

### 8. Triad Creature Stage — L
Reference: central speaker-like form with two small reactive companions in [Sapphire, indexed VSThemes description](https://vsthemes.org/en/skins/rainmeter/35918-sapphire.html).
Original: three new pebble creatures respond separately to bass, mids and highs, not speaker meshes. Tap selects leader; bounded drag arranges them; beat triggers hops. Reuse existing pet/dancer animation infrastructure. S1/S4, energetic styles. Paper cutouts / pixel mascots / translucent pebbles. One full leader and two tiny companions on phone, shared atlas. Art, rigging and touch QA drive the larger cost.

### 9. Prism Scene Dock — M
Reference: modular translucent widgets in [Glass Shards, attributed to 99villages.com by VisualSkins](https://visualskins.com/skin/glass-shards).
Original: three rounded asymmetrical panes labelled Scene, Cast, Toys—not broken-glass silhouettes. Tap opens a labelled picker; stage drag changes only perspective. All scenes. Paper tabs / deck faceplates / tinted prisms. Phone has one Visuals button and a bottom sheet, not floating desktop windows. No animated backdrop blur; Solid panels remains available.

### 10. Half-Moon Horizon — S
Reference: adjustable radius/start/total angle in [r/Rainmeter semicircle discussion](https://www.reddit.com/r/Rainmeter/comments/g47k62/semi_circle_music_visualiser/) recommending VisBubble.
Original: horizon arch behind the S4 sun or S5 lamp floor, with independent kite knots rather than cropped spectrum bars. Drag tilts ±12 degrees, tap sends a spark. Bass lifts the arch; highs flutter knots. Paper bunting / deck arch / glass constellation. Sixteen knots desktop / eight phone. Compact alternative to #1, not another simultaneous halo.

### 11. Twin Needle Postcard — S
Reference: analog/digital VU meters and cover colours in [Desktop VU-Meter 4, indexed VSThemes description](https://vsthemes.org/en/skins/rainmeter/35602-desktop-vu-meter-4.html).
Original: two independently drawn needles labelled Body and Air, showing bass/high-band energy—not invented stereo or calibrated dB. Tap switches energy/progress postcard views. S6 Night Tape Bokeh. Pencil arcs / Classic Deck faceplate (best fit) / glass fine needles. Cache dial, animate only needles; explain these are visual indicators, not mastering tools.

### 12. Quiet Session Card — S
Reference: minimal adaptive now-playing information board in [Cleartext by Redsaph, project overview](https://github.com/redsaph/cleartext).
Original: large title, artist and a tiny mood glyph on Music Stream's existing grid. Tap expands metadata; explicit More replaces hover discovery. Pause dims decoration, never hides transport/current track. S3/S6 or no-motion view. Editorial paper card / deck LCD strip / opaque-backed glass caption. DOM text; no continuous marquee by default. Tap expands long titles. Low spectacle, high usability.

### 13. Rounded Pulse Trail — S
Reference: rounded bars and cover-derived colours in [Lano Visualizer by MarcoPixel, project overview](https://github.com/marcopixel/Lano-Visualizer).
Original: disconnected stitches flowing along a kite string or terrace edge, not straight bars. Energy thickens stitches; onset sends a highlight forward. Pointer bends the path; tap adds a knot. S4/S2. Paper stitches / deck LED dashes / glass droplets. Thirty-two marks desktop / sixteen phone. Cache path, share album palette, avoid per-frame allocation.

### 14. Living Track Label — S
Reference: track information/progress plus art-derived palette in [Monstercat Visualizer by MarcoPixel](https://www.deviantart.com/marcopixel/art/monstercat-visualizer-for-rainmeter-486330771).
Original: small playing label on the existing skin grid with an original three-dot breathing motif. Explicit tap control cycles restrained/balanced/vivid intensity; never skips tracks. All scenes. Paper stamp / deck status LEDs / glass contrast-backed badge. RMS drives pulse, existing palette drives colour. No Monstercat branding, fonts, imagery or bar arrangement. Useful when hero visuals are hidden.

## Shared build contract
- Reuse VISUAL_DIRECTION §1 signals and §2 album-palette rules. One analysis pass shared across scene/toys. No microphone, system-audio capture, credentials or desktop plugins. When analysis is unavailable, show a truthful quiet fallback, not fake beat sync.
- Target 60 fps desktop / 30 fps phone, not an achieved claim. One delta-time rAF loop; phone updates by elapsed time (~33 ms), not every other frame (wrong on 90/120 Hz screens). Start DPR caps at 1.5 desktop / 1 phone. Profile total visual work p95 ≤8 ms desktop / ≤16 ms phone; reduce particles, geometry then render scale if over budget. Measure sustained playback, seeking, track changes, low-power mode and touch latency.
- Only one hero concept plus one quiet HUD simultaneously. Reuse scene geometry and particle pools. Crossfades must not double the phone particle cap. Pause settles to static; hidden document suspends rendering. WebGL context loss falls back to Canvas/static art.
- Touch targets ≥44 px. Pointer capture only on visual playfield, handle pointercancel, use 8 px drag threshold. Do not steal page scrolling or pinch zoom. Cap displacement at 10% stage width and rotation ±15 degrees. Explicit Reset button; no long-press-only or hover-only essential action. Visual interaction does not alter playback unless a labelled transport control is used.
- Labelled keyboard buttons, Enter/Space bursts and focus-scoped arrow adjustments; no global arrow interception. DOM text contrast ≥4.5:1, non-text controls ≥3:1. Decorative canvas aria-hidden; concise accessible scene status. Reduced motion removes pulses/parallax/travelling particles and supplies a static composition. No repetitive full-screen flashes.
- Phone stage stays above transport and safe-area inset; lyrics/visuals are separate tabs. Never push play/seek offscreen or capture gestures over video by default. Manual scene pinning always available. Culture/mood classification remains approximate; do not equate language with mood.
- No new scratch DSP or key-snapping instrument in this addendum: separately gated toys remain in the main spec. No fake precision in tempo/key estimates.

## Best delivery order (value versus effort)
1. Bass Bloom Core (#7, S): quickest striking interactive non-bar effect.
2. Petal Halo (#1, M): signature visual, all skins.
3. Pluckable Monsoon Ribbon (#2, M): distinctive touch-first calm/sad alternative.
4. Orbit Sleeve (#3, M): real progress + stronger now-playing identity.
5. Quiet Session Card (#12, S): long-title/accessibility win before more effects.
6. Chromatic Terrace (#4, M): expand the existing EDM scene after profiling.
Defer Triad Creature Stage until existing dancer/pet rigs and mobile budgets are validated.

## Cross-checks and technical evidence
[Community recommendations](https://www.reddit.com/r/Rainmeter/comments/4lvkus/good_audio_visualizers/) name Monstercat, VisBubble, Fountain of Colors and Cleartext, with a caution about integrated visualizer CPU usage. Anecdotes, not benchmarks.

[Official Rainmeter AudioLevel documentation](https://docs.rainmeter.net/manual/plugins/audiolevel/) distinguishes RMS/peak from FFT bands, attack/decay smoothing, shared-parent analysis and high-update CPU costs. Adopt general engineering principles, not plugin code. Its Windows endpoint loopback is NOT a browser capability; Music Stream analyses only its permitted media graph.

Research also exposed conflicting licence signals for Cleartext-with-Album-Art (repository metadata CC0 versus README attribution/noncommercial text). It is not used. No licence inference is needed for these credit-only independent proposals.
