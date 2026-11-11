# Music Stream — Groove Brawl (working title)

**Status:** design spec only · 2026-11-06 IST (Asia/Calcutta)  
**Owner:** research / design handoff for Full-Stack  
**Scope:** box only. **Do not edit `game.js` / `player.html` from this doc until the user says go.**  
**Legal:** inspired by the *mechanics* of Brain Jar’s *Dead as Disco* (Steam Early Access, May 2026). **Do not copy** that game’s name, characters (Charlie Disco, Idols), art, UI chrome, audio, logos, or “Beat Kune Do / Fever Rush” branding. Our game is an original mode inside Music Stream’s `window.MSGame` picker.

**Working title options (pick one later):** Groove Brawl · Pulse Clash · Stage Crash · Neon Mosh  
**Picker id (suggested):** `brawl`  
**Depends on:** existing beat/chart engine in `game.js`, `window.msAnalyser`, Live2D adapters (`MSGameLive2D` / `registerCharacter`) for Hiyori / Haru / Mao / Rice.

---

## 1. What *Dead as Disco* actually is (research summary)

Sources used (public pages only; trailer audio/video was not watched):

- Steam store: https://store.steampowered.com/app/3404260/Dead_as_Disco/
- Official site: https://deadasdisco.com/
- 80.lv interview on BeatWarping / BYOM: https://80.lv/articles/interview-how-dead-as-disco-synchronizes-combat-to-player-uploaded-music
- Combat guide (rhythm, counters, Fever Rush): https://www.gametruth.com/guides/dead-as-disco-beginner-combat-guide-rhythm-combos-fever-rush/
- Reviews (Kotaku, TheSixthAxis, GamesMarket writeups)

### Pitch
Neon-drenched **third-person rhythm beat ’em up**: martial arts + music-video spectacle. You play Charlie Disco, reclaiming the spotlight from villainous ex-bandmate **Idols**. Every punch, kick, dodge, and combo is meant to land *with* the song.

### Core mechanics (what players feel)
| Pillar | How it works there |
|---|---|
| **Fight to music** | Attack / dodge / takedown sync to the track. On-beat inputs deal more damage, unlock flashier finishers, fill a special meter faster. Off-beat still works — the game stays cool (not a hard fail). |
| **BeatWarping** | Animations are annotated so impact frames *stretch/shrink* to the next beat. Input starts immediately; the punch *lands* on music. Not pure “wait for the next beat window” lag. |
| **Read the cue, pick the reply** | Attack indicators: counterable vs **unblockable** (must dodge). Multi-hit strings need a reply per hit. Perfect dodge windows light up. |
| **Fever / special** | Successful on-beat actions fill a meter → hold Fever + Attack for a close-range drum-solo flurry. |
| **Free-flow crowd** | Waves of fodder + boss phases (Arkham / DMC / Hi-Fi Rush hybrid). Projectiles can interrupt combos. |
| **BYOM (“My Music”)** | Import any track; set **BPM** + **beat offset** (later: auto-calibration). Optional BPM *sections* for tempo changes. Story tracks get hand-authored markers (drumrolls, vocals) for “moveset syncs.” |
| **Modes** | Story Idol fights (interactive music videos), Infinite Disco / challenges / Free Play with enemy-wave editing, cosmetics, skill tree (“Fans” currency). |
| **Tech stack** | Unreal + FMOD + custom SongCrafter. Desktop-class 3D. |

### What the trailer is selling (from descriptions / marketing)
Playable music-video brawling: neon stages, stylish camera, choreographed KOs timed to drops, custom songs turning into fight spectacles. That spectacle is the fantasy the owner wants — **not** another falling-notes lane game.

---

## 2. What we can build in Music Stream (2D browser)

Music Stream already has the hard part of BYOM: **whatever song is playing** (YouTube / YT Music via our stream) *is* the soundtrack. Charts come from the live beat engine (`msAnalyser` + onset/BPM grid in `game.js`). Live2D characters are landing for Dance / Runner / Fight.

### Feasible fantasy (target)
A **side-view / shallow-arena 2D rhythm brawler** on the game canvas:

- Player Live2D (or silhouette fallback) on the left; 1–3 foes on the right / around.
- **Attack** on beat → damage + combo.
- **Dodge** on unblockable cues → i-frames + meter.
- **Counter** on telegraphed strikes → big score + Fever fill.
- **Fever** special that clears a wave or finishes a stunned foe on a downbeat.
- Waves scale with song energy / onset density; a “boss bar” appears on drops or every N KOs.
- Phone-first pads + desktop keys; music keeps playing (same contract as other MSGame modes).

### Explicitly out of scope (v1–v2)
| Dead as Disco feature | Why we skip / defer |
|---|---|
| Full 3D free-roam camera + music-video levels | Browser perf + art budget; Canvas2D/WebGL side stage only |
| True BeatWarping (annotated stretchable anims) | Live2D motions aren’t authored with warp sections; approximate pose snaps + impact VFX on beat instead |
| Hand-authored SongCrafter markers per track | We have live onset/BPM only; optional later: user tap-calibrate offset |
| Skill tree, story Idols, Dive Bar collectibles | Product scope; Music Stream games are score-chase modes |
| Wave editor / UGC level builder | Defer; auto waves from beat grid |
| Co-op | No |

### Relationship to existing **Rhythm Fight** (`GAMES.fight`)
Rhythm Fight is a **2-target (BODY/HEAD) approach-ring punch game** vs one Shadow. Groove Brawl **replaces or supersedes** that fantasy with:

- Crowd waves + counter/dodge verbs  
- Fever meter  
- Stronger Live2D combat poses  
- Drop-triggered boss phases  

Keep Rhythm Fight until Groove Brawl UAT passes; then demote Fight to legacy or merge.

---

## 3. Original design — Groove Brawl

### 3.1 Fantasy one-liner
You’re the opener on a neon stage. The song is the fight. Hit on the groove, slip the red cues, and dump Fever when the drop hits — with your Live2D dancer as the fighter.

### 3.2 Verbs (4 inputs max — phone must work)
| Verb | Meaning | Beat rule | Reward |
|---|---|---|---|
| **Strike** | Basic attack toward nearest foe in range | On-beat → Perfect; near-beat → Good; off → Weak (still hits) | Damage, combo, Fever fill |
| **Heavy** | Slow hit / launcher (costs 1 beat wind-up telegraph) | Must release on beat | Stun / launch; opens Counter window on foe |
| **Dodge** | Sidestep / flash-step | Required for **red unblockable**; optional otherwise | Perfect dodge → Fever + brief slow-mo flash (≤120 ms, no real pause of music) |
| **Counter** | Parry when a foe shows a **blue** wind-up | Window ±80–100 ms of predicted impact beat | Big damage, KO credit, Fever chunk |
| **Fever** (hold + Strike, or dedicated pad when full) | Special flurry | Best started on a **downbeat** or `drop` event | Clears light foes / finishes stunned; score bomb |

v1 can collapse Heavy into “hold Strike” so phone stays at **3 pads**: Strike · Dodge · Counter, with Fever as hold-Strike when meter ≥ 100%.

### 3.3 Judgement windows (reuse game.js style)
Aligned with existing Perfect / Good / Miss tiers:

| Judgement | Window vs predicted beat | Damage mult | Fever |
|---|---|---|---|
| Perfect | ≤ 45 ms | 1.5× | +8 |
| Good | ≤ 90 ms | 1.0× | +4 |
| Weak (off-beat hit still allowed) | > 90 ms but action accepted | 0.5× | +1 |
| Miss (failed counter/dodge) | wrong verb or late | 0 | player HP − |

**Important DaD lesson we keep:** never soft-lock input until the next beat. Strike always starts immediately; **impact VFX and damage apply on the nearest upcoming beat** (poor-man’s BeatWarp).

### 3.4 Beat mapping (our engine)

Reuse `game.js` chart engine:

- `E.period` / `E.phase` / `E.live` onset grid  
- Slot events: `beat`, `half`, `down`, `on`, strength `s`, band `b`  
- Features from analyser (and future viz signal layer): `bass`, `onset`, `drop`, `energy`

| Song signal | Spawns / modifies |
|---|---|
| Normal beat + onset | Light foe Strike cue (blue counterable ~40% on Normal+) |
| Strong downbeat (`down` && `on` && `s` high) | Unblockable (red) or Heavy cue |
| High band / snare-ish (`b` high) | Projectile / overhead (must Dodge) |
| `drop` or energy spike | Boss phase start or Fever auto-nudge UI |
| Low confidence / idle groove | Fewer cues, more Weak-friendly windows (Easy) |

**BPM extremes:** clamp effective combat BPM to **70–160** (fold half/double like dancers). Above 160, treat every other beat as a combat beat so phone thumbs survive.

**Calibration (v2):** optional “Tap 8 beats” offset nudge stored per `songKey()` — mirrors DaD’s offset fix without a full SongCrafter.

### 3.5 Enemies
Keep art original: silhouette / simple masked Live2D recolors / procedural “shadow dancers” — **not** Idols or Charlie.

| Role | HP | Behavior | Notes |
|---|---|---|---|
| **Mosh** (fodder) | 1–2 hits | Walk in; telegraphed Strike | Max 3 on screen (phone: 2) |
| **Hype** | 3 hits | Mix Strike + occasional red | Flanks |
| **Dropper** (mini-boss) | Bar HP | Pattern strings synced to 4–8 beat phrases | Spawns on `drop` or every 8 KOs |
| **Projectile** | n/a | Travels in 2–3 beats; Dodge | From off-stage |

Targeting: auto-lock nearest in cone; Strike always hits locked foe. No free-aim required.

### 3.6 Combos & Fever
- Combo increments on Perfect/Good Strike or successful Counter; breaks on Miss or taking a hit.
- Fever 0–100; dump for **Groove Break** (our name — not “Fever Rush”): 1.5–2.5 s flurry, damage ticks on successive beats, ends on a slam if a foe is stunned.
- Score: base hit × judgement × combo mult × Fever bonus; persist best via existing `msGame2:` localStorage keys.

### 3.7 Live2D integration
Use `MSGame.registerCharacter` / `MSGameLive2D` adapters already wired for Dance / Character Runner / Rhythm Fight.

| Pose / reaction | Trigger |
|---|---|
| idle sway | beatPhase |
| punch / kick | Strike impact beat |
| duck / flash | Dodge |
| smug / wink | Perfect Counter / KO |
| hit react | player took damage |
| celebrate | Groove Break end / wave clear |

**Limits:** Live2D sample motions often look wrong (extra limbs, T-pose blends) if we force-speed them. Prefer **short pose snaps + particle impact** over stretching long dances. Another bot owns better internet motions — this mode consumes whatever poses the character adapter exposes (`punch`, `hit`, `idle`, `ko`, …).

Player picks character in existing sheet (Hiyori / Haru / Mao / Rice). Foes use silhouette or a desaturated clone — never a second full Live2D on phone if FPS < 40.

### 3.8 Visual style (original)
Neon stage floor + album-art palette (same rules as `VISUAL_DIRECTION.md`). Side Cut / Classic Deck / Glass Stage skins tint the arena. Approach rings for cues (blue = Counter, red = Dodge, white = optional Strike target). **No** copying DaD UI glyphs, drumstick Fever iconography, or Idol silhouettes.

---

## 4. Controls

### Phone (portrait primary)
| Control | Mapping |
|---|---|
| Left pad | **Dodge** |
| Center pad | **Strike** (hold when Fever full → Groove Break) |
| Right pad | **Counter** |
| Swipe left/right on stage | Dodge (alt) |
| Tap foe | Retarget |

Pads must be ≥ 48 CSS px; labels short: `DODGE` · `HIT` · `PARRY`.

### Desktop
| Key | Action |
|---|---|
| `F` / `J` / Space | Strike |
| `D` / `Shift` / `S` | Dodge |
| `K` / `E` | Counter |
| `R` | Restart (existing) |
| `P` | Pause game (music continues) |
| Esc | Back / close |

### Accessibility
- Colorblind: shapes differ (chevron Dodge, circle Strike, diamond Counter) not only hue.
- Easy: no red cues for first 30 s; Weak hits still build Fever slowly.
- Reduce flash: skip 120 ms “slow-mo” overlay.

---

## 5. Feasibility verdict

| Layer | Verdict |
|---|---|
| BYOM soundtrack | **Already done** (playing track) |
| Beat grid → combat chart | **Buildable** on existing engine |
| Attack / dodge / counter loop | **Buildable** (2D, cue rings) |
| Crowd waves + KO scoring | **Buildable** (cap entity count) |
| Fever / Groove Break | **Buildable** |
| Live2D fighter feel | **Partial** — poses + VFX; not Unreal BeatWarp |
| Music-video 3D spectacle | **Not buildable** at DaD fidelity in this PWA |
| Hand-authored per-song sync magic | **Not in v1**; optional tap offset later |

**Bottom line:** We can ship a **satisfying original 2D rhythm brawler** that captures the *fantasy* (fight the song, counter on beat, dump specials on the drop, your track = your stage). We cannot ship a browser clone of Dead as Disco’s 3D BeatWarping spectacle.

---

## 6. Phased build (for Full-Stack; no code in this task)

### Phase 0 — Spec lock (this doc)
- [x] Research DaD mechanics  
- [x] Name options + legal fence  
- [ ] User picks working title + confirms “build on box”

### Phase 1 — Vertical slice (box `:8130`)
1. New `GAMES.brawl` stub in picker (name TBD).  
2. One foe, Strike-only with poor-man’s beat-impact delay.  
3. Perfect/Good/Weak scoring hooked to existing `addScore` / combo.  
4. UAT screenshots: phone + desktop; FPS log; **no “heard audio” claims**.

### Phase 2 — Defense verbs
1. Blue Counter + red Dodge cues from chart.  
2. Player HP; Miss feedback; Easy/Normal/Hard cue density.  
3. Mosh ×2 waves; projectile on high-band events.

### Phase 3 — Fever + Live2D
1. Fever meter + Groove Break.  
2. Wire active `MSGame` character poses; silhouette fallback.  
3. Dropper mini-boss on `drop` / KO milestones.  
4. Truncation-safe picker title (≤ phone card width).

### Phase 4 — Polish
1. Optional per-song tap offset calibration.  
2. Skin-aware arena tint; particle KO.  
3. Replace or archive Rhythm Fight if redundant.  
4. UAT Human visual pass → user “go” before any PC sync.

**Perf gates (measure, don’t claim):** phone Safari/Chromium ≥ 40 FPS with 1 Live2D + ≤2 foes; desktop ≥ 55 FPS with 1 Live2D + 3 foes. If fail, foes → silhouettes.

---

## 7. Acceptance criteria (UAT)
1. Opening the mode does not stop music.  
2. Charts change when the song / seek changes (beat engine re-lock).  
3. On-beat Strike clearly scores higher than mashing (measured by score delta in a scripted tap harness).  
4. Red cues punish standing still; Dodge clears them.  
5. Counter window is readable ≥ 400 ms before impact on Normal.  
6. Fever dump is possible within one chorus on Normal with decent timing.  
7. Live2D failure falls back to silhouette without freezing the player (known `player.html` / observer issues are owned elsewhere).  
8. No DaD names, assets, or trademarked phrases in UI strings.

---

## 8. Credits / inspiration note (for `GAME_CREDITS.md` later)
When implemented, add a row:

| Project | What we took | Code |
|---|---|---|
| Dead as Disco (Brain Jar) — public interviews / Steam description | Design ideas only: on-beat combat rewards, counter vs unblockable cues, special meter, BYOM fantasy | **None** — original `game.js` mode |

---

## 9. Open questions for the user
1. Prefer working title: **Groove Brawl** / Pulse Clash / Stage Crash / Neon Mosh?  
2. Keep Rhythm Fight beside it, or replace once Brawl ships?  
3. Phone: 3 pads (HIT / DODGE / PARRY) OK, or must include a visible FEVER button?
