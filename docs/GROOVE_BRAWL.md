# Groove Brawl (`GAMES.brawl`, msgame-4.2)

Original rhythm brawler built on `docs/DISCO_BRAWLER_SPEC.md`. It takes design inspiration only from the genre; see GAME_CREDITS.md.

## Controls
| Verb | Desk | Phone |
|---|---|---|
| HIT (Strike) | F / J / Space (or tap the stage) | middle pad **HIT** |
| DODGE | D / S / Shift / ← ↓ | left pad **DODGE**, or swipe left/right/down |
| PARRY (Counter) | K / E / ↑ → | right pad **PARRY**, or swipe up |
| Groove Break (Fever at 100%) | hold HIT ≥ 300 ms, or G | hold **HIT** |

## Rules
- **HIT** always animates at once. Its **impact lands on the nearest beat** (beat-impact delay), with one impact per beat.
  - Perfect (≤ ~45 ms): 1.5× damage and +8 Fever.
  - Good (≤ ~90 ms): 1× damage and +4 Fever.
  - Weak (off-beat): 0.5× damage and +1 Fever. It still connects but drops the combo.
  - Mashing faster than about half a beat always counts as Weak. Extra presses before the queued impact only add flair.
- **Cues** come from the live bar-echo chart:
  - **Red chevron** (strong downbeat) means DODGE. Not on Easy, and there are no red cues for the first 30 s.
  - **Blue diamond** means PARRY. A successful parry does 2 damage and gives +12 Fever.
  - **Projectiles** (high-band hits) fly at you. DODGE them.
  - Missing a cue costs player HP: projectile 6, red 10, blue 8. At 0 HP you get "DOWN!", the HP refills, and play continues with no soft-lock.
- **Waves:** foes join on beats, up to 2 on phone or Easy and 3 on desk.
  - **mosh** foes have 2 HP.
  - **hype** foes have 3 HP and appear after 2 K.O.s.
- **The Dropper** mini-boss has 12/16/20 HP (Easy/Normal/Hard). It arrives every 8 K.O.s and on music drops (an energy spike), and gets its own HP bar.
- **Groove Break:** 4 beat-ticks of flurry damage on every foe, then a final slam. It clears pending cues.
- The fighter is the selected `MSGame` character (Live2D or silhouette). Foes are silhouette shadow dancers.

## API
`MSGame.state().brawl` returns `{foes[{kind,hp,max,pose}], fever, youHp, kos, grooveBreak, boss, pendingImpacts, nextBeatInMs, periodMs, lastImpact{kind,pressToImpactMs,impactVsBeatMs}, downs}`.

## UAT
Run `uat/game/test_brawl.py`. It saves `brawl_results.json`, `test_brawl.log` and the `brawl-*.png` screenshots.
