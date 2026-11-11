# Skin packs

Each pack: `skins/<id>/`

| File | Required | Notes |
|------|----------|--------|
| `skin.json` | yes | id, name, preview, npLayout, art, themeColor, sideLabel, fonts |
| `skin.css` | yes | Scoped under `html[data-skin=<id>]`. Sets color/type/shape/chrome/density tokens. |
| `icons.svg` | yes | Symbols: `i-heart i-play i-pause i-next i-prev i-shuf i-rep i-rep1 i-down i-dl i-q i-radio i-imp i-vol i-fs i-more` + `i-brand`. Prefer `currentColor`; pack may set `--icon-stroke`. |
| `preview.svg` (or `.png`) | yes | ~160×100 static mock for future picker. |
| `fonts/*.woff2` | optional | Prefer bundled FOSS (OFL). |
| `textures/*` | optional | Light patterns; avoid mandatory heavy blur (Android). |

## Tokens packs must set
Colors: `--ink --ink2 --paper --tom --mus --cob --acc --txt --sub --card --bg` (+ Side Cut extras like `--line-chip --muted-num`…).
Shape: `--r-btn --r-card --r-art --r-pill --r-sheet` (alias `--r` → `--r-card`).
Chrome: `--card2 --line --line2 --muted-bg --track --border-w --border-style --shadow-panel --shadow-press --backdrop --icon-stroke`.
Type: `--font-body --font-disp --font-mono --font-num` (aliases `--disp` / `--mono`).
Density: `--row-h --art-sz`. Motion: `--ease` (honor `prefers-reduced-motion`).
Art shape: `html[data-art=square|round|vinyl]` (not token-only).
NP layout: `html[data-np-layout=art-hero|split|compact-deck]` + `--side-label`.

## How to switch (step 3 — skin-card picker)
**UI:** Header `#skstrip` shows preview cards (Side Cut / Classic Deck / Glass Stage). Tap a card to switch in-place.
Also: **Skin** button `#skb` (header), `#skbnp` (Now Playing), `#skpill` (extras) → opens dialog `#skd` with descriptions + **Solid panels** toggle.
Escape / backdrop click closes `#skd`. Selected card gets `.on` / `aria-checked`.

**Legacy colors (Theme):** Color palettes (Side B / Synth / Sakura / Paper / Nord) nest under skins — **Legacy colors** in `#skd` footer calls `openTheme()` → `#thd` (close skd then open thd). Optional `#thpill` inside `#xtra` details is also labeled Legacy colors. Header/NP Theme chrome (`#thb` / `#thbnp`) is not injected (CSS-hidden/removed if stale). `setTheme` / `#thd` still work. Old `#thstrip` hue pills stay removed/hidden.

```js
setSkin('side-cut')           // default | classic-deck | glass-stage; loads /skins/<id>/skin.css + icons.svg
openSkin()                    // open #skd picker dialog
setSkinSolid(true|false)      // html.solid; persists localStorage.skinSolid ('1'/'0')
setNpLayout('art-hero')       // art-hero | split | compact-deck — survives skin switches once set
setArtShape('vinyl')          // square | round | vinyl (also toggles body.vinyl) — survives skin switches once set
setTheme('nord')              // color-only: sideb | synth | sakura | paper | nord
```

Default on load: `data-skin=side-cut`, `data-theme=sideb` (palette fallback), `data-np-layout=art-hero`, `data-art=square`.
`html.solid` applies when `localStorage.skinSolid==='1'` **or** `prefers-reduced-transparency: reduce` (OS reduce forces solid and disables the toggle).

## Registry
No manifest — **folder convention**: `setSkin('<id>')` fetches `/skins/<id>/skin.json` and swaps `/skins/<id>/skin.css` + `icons.svg`.
To add a pack: create the folder, then add its critical files to the precache list in `sw.js` and bump `V`.
**User layout wins:** `skin.json` `npLayout` / `art` apply **only if** `localStorage.npLayout` / `localStorage.art` are unset. After the user calls `setNpLayout` / `setArtShape`, those values survive subsequent `setSkin()` calls. Pack defaults apply again only after clearing those keys.
`i-brand` must contain classed `<g class="disc">`, `<g class="arm">`, `<g class="eq">` (DOM-cloned for CSS animation).
Sprites must be well-formed XML (quoted attrs, no `--` inside comments). Stroke widths are baked per pack in `icons.svg`
(icons render via `<use>`, so `--icon-stroke` documents the pack's value but cannot override path attributes).

## Shipped
| id | name | npLayout | art | side label | display/num font |
|----|------|----------|-----|------------|------------------|
| `side-cut` | Side Cut (default) | art-hero | square | SIDE CUT — NOW SPINNING | Archivo Black |
| `classic-deck` | Classic Deck | compact-deck | square | CLASSIC DECK — ON AIR | VT323 (disp + LCD digits) |
| `glass-stage` | Glass Stage | split | round | GLASS STAGE — LIVE | Outfit (disp only) |

Display faces are chrome-only (brand, labels, digits); track titles/body stay on `--font-body` (system) for Indic.

Glass Stage blur: base surfaces use solid `--backdrop`; blur only inside `@supports(backdrop-filter)`, smaller on ≤600px,
and disabled under `prefers-reduced-transparency`, `prefers-reduced-motion`, or `html.solid` (manual fallback class).


## Extra recolor packs (original CSS)
neon-arcade, paper-fold, frost-panel, ember-glow, mint-wave, ink-kanagawa — Music Stream original. Color inspiration from public theme palettes (Dracula/Nord/Kanagawa/Rosé Pine — MIT); no upstream CSS copied.

See /THEMES.md for full palette credits.
