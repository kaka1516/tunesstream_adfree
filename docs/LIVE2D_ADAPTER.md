# Live2D characters (msgame-4.1): one shared adapter, 4 models

Characters: **Hiyori, Haru, Mao, Rice** (official Live2D Cubism sample models). Mark, Wanko, Ren, Natori are
deliberately **not** shipped or registered. Everything is served from music-stream under `/assets/chars/` (200 on :8130).

## Files
| Path | What |
|---|---|
| `assets/chars/live2d.js` | **Shared runtime** (v2). One file drives all 4 models. Lazy: nothing heavy loads until a Live2D character is chosen. |
| `assets/chars/live2d-hiyori.js` | Symlink → `live2d.js` (back-compat for the v1 avatar bridge URL). |
| `assets/chars/lib/` | `pixi.min.js` (PixiJS 6.5.2, MIT), `cubism4.min.js` (pixi-live2d-display 0.4.0, MIT), `live2dcubismcore.min.js` (Live2D Cubism Core, Live2D Proprietary Software Licence — "Redistributable Code"), licence files. |
| `assets/chars/{Hiyori,Haru,Mao,Rice}/` | Unmodified model art (moc3/textures/physics/motions/expressions/pose3) + `LIVE2D_LICENSE.md`. Only `model3.json` was edited: Haru's 4 `Sound` refs removed (sound files not shipped), `Pose` refs restored for Haru and Mao (their `pose3.json` exists; the copies had lost the ref → the 4-hands bug). |
| `vendor/ms/avatar-live2d.js` | Stage bridge: registers all 4 with `MSViz.registerAvatar`. **Also copied over `vendor/ms/avatar-hiyori.js`** (the URL player.html already loads), original kept as `avatar-hiyori.v1.js.orig`. |
| `game.js` | `L2D_IDS` stubs registered with `MSGame.registerCharacter` (`kind:'live2d', lazy:true`); swapped for real adapters when the runtime loads. |

## Load path
1. `MSGame.useCharacter('haru')` (or the picker's **Character** chip → sheet, or `C` key). Choice persisted in `localStorage.msGameChar`.
2. game.js injects `/assets/chars/live2d.js?v=4` once → it injects the 3 libs in order → `window.MSGameLive2D = {v:2, models, adapters, adapter, preload, mount, emotes, poses, base}` and calls `MSGame.registerCharacter` for each of the 4.
3. `Live2DModel.from('/assets/chars/<Model>/<model>.model3.json', {autoInteract:false, autoUpdate:false})`; sounds muted.
4. While loading (or on any error) the game draws the canvas **silhouette**; an adapter that throws falls back permanently to silhouette (`state().character.error`).

## Rendering
One shared off-screen `PIXI.Renderer`; each figure renders into its own 2D cache canvas which is `drawImage`d into the
game canvas (so the game keeps one 2D context). Render size = on-screen size × q (q 1 / .8 / .6 by frame time, 1.5 s
hysteresis), frame-skip 2–3 under load. Foe tint is applied once per render (`source-atop`), never with `ctx.filter`.
Measured: desk 50–58 fps, phone 54–60 fps with a Live2D fighter.

## Pose map (game pose → normalised params, per model aliased to its own param ids)
| Pose | Head / body | Arms | Notes |
|---|---|---|---|
| idle | sassy hip-sway, 2 beats/sway, amplitude ∝ energy | groove pattern L-R-both-down (4-count) | nod on beat, shoulder pop on off-beat |
| run | lean fwd, bob | swing | Character Runner |
| left / right / up / down | head + body turn, sprite rot ±, squash for down | arm up on that side / both for up | Dance Battle |
| jump / slide | sprite dy / squash sy | arms up / down | Runner |
| punch (low/high) | lunge, rot | arm forward | Rhythm Fight / Groove Brawl |
| hit / miss | recoil, pout | arms down | |

Abstract slots → real ids (subset): Hiyori `ParamArmLA/RA, ParamMouthForm, ParamMouthOpenY, ParamCheek`; Haru same + `ParamTere` cheek;
Mao `ParamArmLA01/RA01, ParamMouthUp, ParamA, ParamU (kiss), ParamAllRotate (sway)`; Rice `ParamArmL01/R01, ParamAllZ (sway)`.
Missing params are skipped silently, so a pose degrades instead of breaking.

## Emotes & interaction (only each model's own params, expressions and motions)
| Emote | Trigger | How |
|---|---|---|
| wink (420 ms) | tap head, random idle | EyeLOpen → 0 + smile |
| smile / happy | perfect / good hits, tap head | mouth form + cheek; expression Haru F01/F05, Mao exp_02/exp_04 |
| kiss (1.3 s) | combo milestones | mouth pucker (Mao `ParamU`), head tilt + 3 canvas hearts |
| pout (1 s) | miss | mouth form −, brows; Haru F07, Mao exp_06 |
| tease / flip | random idle every 5–9 s | head tilt + hair flick (physics) |
| spin (720 ms) | tap body | horizontal flip (scaleX cos) + model's own `TapBody` motion |
| drop (1.2 s) | music drop (energy > .55 and > 1.7× running mean, 6 s cooldown), K.O. | surprise expression + `TapBody` |
| sway | drag | spring-back body/angle offset |
| look-follow | pointer / touch anywhere | AngleX/Y, EyeBallX/Y, BodyAngleX |
Energy (band levels) scales sway/nod amplitude, so quiet passages are gentle and choruses bounce.

## Arms ("4 hands") guard
Each model draws two arm variants (A/B) and expects `pose3.json` to keep exactly one visible. Fixes:
Pose refs restored (Haru, Mao); plus `armGuard()` forces exactly one part per arm group to opacity 1 (others 0) after
every update; `armCheck()` returns the count of visible parts per group — exposed as `state().character.arms` and
`MSGame.charPreview().arms` and asserted `== 1` per group in the UAT. Rice has no A/B parts (blends via `ParamArmChange`).

## Stage avatar slot (MSViz) — no player.html change needed
player.html already does `loadScript('/vendor/ms/avatar-hiyori.js')`. That file is now the generic bridge and registers
**hiyori, haru, mao, rice** (`MSViz.avatars()` lists all 4). Canonical source is `vendor/ms/avatar-live2d.js`; if the
player owner prefers the canonical name, it is a one-line change in player.html:
`loadScript('/vendor/ms/avatar-live2d.js')` (guarded by `window.__msAvatarLive2D`, so loading both is harmless).

## Swapping / adding a model
Copy the model folder to `assets/chars/<Name>/` (with its licence), make sure `model3.json` has its `Pose` ref and no
dangling `Sound` refs, then add an entry to `MODELS` in `live2d.js`: `{dir, file, alias:{…param ids…}, expr:{smile,happy,pout,surprise}, arms:[[partA,partB],…], frame:{cx,top,bot}}`
and the id to `L2D_IDS` in game.js (+ the bridge list in avatar-live2d.js).

## Licence notes / known limits
- Models: Live2D **Free Material License** + per-model Sample Model Terms; Cubism Core: Live2D Proprietary Software Licence (redistributable).
  Free for individuals / small businesses (annual revenue < ¥10M); a larger business needs a Cubism SDK Release License. Art is not modified or redesigned.
- Dance moves are authored procedurally from each model's own parameters (no third-party motion files).
- First load ≈ 1.5–3 MB per model (cached afterwards); Live2D is WebGL — if WebGL is unavailable it falls back to the silhouette.
