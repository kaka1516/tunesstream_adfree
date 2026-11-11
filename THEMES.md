# Music Stream — themes & skins attribution

## Full skins (pack mechanism)
Skins live under `skins/<id>/` (`skin.json`, `skin.css` scoped as `html[data-skin=<id>]`, `icons.svg`, optional fonts/textures, `preview.svg`).
Default skin: **Side Cut** (`side-cut`) — record-shop risograph / offset, paper texture, editorial list numbers, vinyl art option. Successor to the former inlined “Side B” identity chrome.

See `skins/README.md` for pack layout and how to switch.

### Side Cut fonts
- **Archivo Black** — Omnibus-Type / The Archivo Black Project Authors, SIL Open Font License 1.1.
  Bundled: `skins/side-cut/fonts/ArchivoBlack-Regular.woff2` + `OFL.txt`.
  Upstream: https://github.com/Omnibus-Type/ArchivoBlack

### Classic Deck fonts
- **VT323** — Peter Hull / The VT323 Project Authors, SIL OFL 1.1. Bundled: `skins/classic-deck/fonts/VT323-Regular.woff2` + `OFL.txt`. Upstream: https://github.com/phoikoi/VT323

### Glass Stage fonts
- **Outfit** (variable) — The Outfit Project Authors, SIL OFL 1.1. Bundled: `skins/glass-stage/fonts/Outfit-Variable.woff2` + `OFL.txt`. Upstream: https://github.com/Outfitio/Outfit-Fonts

## Color-only themes (temporary fallback)
Palette hex values only (via `html[data-theme=…]`); no code copied. Kept until further skin packs land.
- Side B (`sideb`) — original palette (same tokens as Side Cut defaults).
- Synthwave — SynthWave '84 by Robb Owen, MIT: https://github.com/robb0wen/synthwave-vscode
- Sakura — Catppuccin Mocha, MIT: https://github.com/catppuccin/catppuccin
- Paper — Rosé Pine Dawn, MIT: https://github.com/rose-pine/rose-pine-theme
- Nord — Nord by Arctic Ice Studio, MIT: https://github.com/nordtheme/nord

App icon / splash remain global (not per-skin).


## Expanded color themes (hex palettes only; no upstream code)
Credits (MIT/Apache/public color refs): Dracula, Gruvbox, Solarized, Tokyo Night, Everforest, Monokai, Atom One Dark, Ayu, Kanagawa, plus original Ocean/Ember/Mint/Violet/Slate/Flamingo packs for Music Stream.

## Skins
side-cut, classic-deck, glass-stage (original), plus neon-arcade, paper-fold, frost-panel, ember-glow, mint-wave, ink-kanagawa (recolor packs).
