#!/usr/bin/env sh
# Explicit yt-dlp updater (ms-v75). Run it yourself when YouTube playback breaks; then restart the server.
# It never runs on its own. Uses the same Python the server uses (YTDLP_PY in music.env, else python3).
# Usage: scripts/update-ytdlp.sh [--pre]      (--pre = PyPI pre-release/nightly build)
cd "$(dirname "$0")/.."
PY="$(sed -n 's/^YTDLP_PY=//p' music.env 2>/dev/null | head -1)"; PY="${PY:-${PYTHON:-python3}}"
PRE=""; [ "$1" = "--pre" ] && PRE="--pre"
echo "yt-dlp before: $("$PY" -m yt_dlp --version 2>/dev/null || echo none)"
if [ -n "$VIRTUAL_ENV" ] || "$PY" -c 'import sys;sys.exit(0 if sys.prefix!=sys.base_prefix else 1)' 2>/dev/null; then
  "$PY" -m pip install -U $PRE "yt-dlp[default]"
else
  "$PY" -m pip install --user -U $PRE "yt-dlp[default]" || { echo "pip refused (externally managed Python?). Use the venv made by install.sh, or your OS package (e.g. 'pkg upgrade yt-dlp' / 'opkg upgrade yt-dlp')."; exit 1; }
fi
echo "yt-dlp after:  $("$PY" -m yt_dlp --version 2>/dev/null || echo none)"
echo "Restart the server so it loads the new extractor (or use the in-app yt-dlp update, which re-imports it)."
