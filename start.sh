#!/usr/bin/env sh
# Linux / Termux / OpenWrt launcher. Usage: ./start.sh [--tunnel] [--update-ytdlp]
# ms-v75: yt-dlp is only upgraded when you ask (--update-ytdlp or MS_UPDATE_YTDLP=1); launching never changes installed packages.
cd "$(dirname "$0")"
PY="$(sed -n 's/^YTDLP_PY=//p' music.env 2>/dev/null | head -1)"; PY="${PY:-${PYTHON:-python3}}"   # the venv python written by install.sh
for a in "$@"; do [ "$a" = "--update-ytdlp" ] && MS_UPDATE_YTDLP=1; done
if [ "${MS_UPDATE_YTDLP:-0}" = "1" ]; then sh scripts/update-ytdlp.sh || echo "yt-dlp update failed; starting with the installed version"; fi
"$PY" -m yt_dlp --version 2>/dev/null > ytdlp_version.txt || echo "warning: yt-dlp not importable by $PY (run ./install.sh)"
if [ -f server.pid ] && kill -0 "$(cat server.pid)" 2>/dev/null && grep -q music_server "/proc/$(cat server.pid)/cmdline" 2>/dev/null; then
  echo "already running (pid $(cat server.pid)); not starting a second copy"
else
  nohup "$PY" music_server.py >> server.log 2>&1 &
  echo $! > server.pid; echo "server pid $! (port from music.env MUSIC_PORT)"
fi
for a in "$@"; do [ "$a" = "--tunnel" ] && { nohup "$PY" scripts/music_tunnel.py > tunnel.log 2>&1 & echo "tunnel pid $! (URL -> public_url.txt)"; }; done
