#!/data/data/com.termux/files/usr/bin/bash
# Low-priority weekly visuals updater. Never restarts the music server.
set -u
MS="${MUSIC_STREAM_ROOT:-$HOME/music-stream}"
PY="${MS}/scripts/viz-update.py"
[ -f "$PY" ] || exit 0
[ -f "$MS/assets/viz/update/disabled" ] && exit 0
# nice + ionice when available; stay quiet
CMD=(python3 "$PY")
if command -v nice >/dev/null; then CMD=(nice -n 19 "${CMD[@]}"); fi
if command -v ionice >/dev/null; then CMD=(ionice -c3 "${CMD[@]}"); fi
exec "${CMD[@]}" "$@"
