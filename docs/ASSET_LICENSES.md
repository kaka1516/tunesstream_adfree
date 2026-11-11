# Asset licences: what is FOSS and what is not (ms-v77)

The **code** (server, player, games, visuals, VRM dancer) is original Music Stream code; its licence is **not yet chosen by the owner
(unspecified)**, so do not describe the package as open source yet. Third-party runtimes keep their own licences (MIT, ISC, BSD-3-Clause,
and the Live2D Open Software / Proprietary licences for Cubism parts): see `/THIRD_PARTY_NOTICES.md`.
The **characters are optional assets**, and most are *not* FOSS. Details and links are in `docs/GAME_CREDITS.md`.

## Selectable characters (19)
| Group | Characters | Runtime | Licence class |
|---|---|---|---|
| VRM, CC0 | Darkness Shibu, Vivi, Sendagaya Shibu, Victoria Rubin, Vita, Sendagaya Shino, HairSample F (7) | three.js + three-vrm (MIT) | **Open (CC0)**. Fully FOSS path. |
| VRM, VRoid sample terms | AvatarSample A, AvatarSample B (2) | same | Free to use, alter and redistribute; may not be sold or relicensed as CC0. **Not FOSS.** |
| Live2D, open art | Arch-chan (CC0), Cyannyan (CC BY-SA 4.0, attribution + share-alike) (2) | Live2D Cubism Core | Art is open, but the runtime is proprietary (below). |
| Live2D, custom licence | Amahane Hikari (1) | Cubism 5 Core | Model Attribution + No-AI License 1.0: credit required, no AI/ML training. **Not OSI-open.** |
| Live2D samples | Hiyori, Haru, Mao, Rice, Mao Pro, Shizuku, Koharu (7) | Cubism Core | Live2D Free Material License. Redistributable with conditions; businesses with revenue ≥ ¥10M need a Live2D licence. **Not FOSS.** |

Haru's 27 motion aliases are the same Haru model and are not counted as characters.

**Proprietary runtime:** `assets/chars/lib/live2dcubismcore*.min.js` is Live2D Proprietary Software (Redistributable Code).
Every Live2D character, including CC0 Arch-chan, needs it.

**A strictly FOSS build has only the 7 CC0 VRM characters.** Everything else is an optional asset that is redistributable under
its own terms.

## Withdrawn (kept private, never served or packaged)
| Asset | Why | Where now |
|---|---|---|
| pixiv VRoid VRMA motion pack (7 files) | Terms forbid extractable redistribution and religious/political use | `<private-folder-outside-the-repo>/vrma/` |
| Runa Inoue VRM | Embedded meta `OnlyAuthor` vs MIT GitHub release; author forbids impersonation | `<private-folder-outside-the-repo>/vrm/` |

Packaging guards: `.dockerignore`, `.gitignore`, and `scripts/check-restricted-assets.sh` (also run in the Dockerfile).
