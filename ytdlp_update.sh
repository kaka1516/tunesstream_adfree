#!/data/data/com.termux/files/usr/bin/sh
# speed-20261110: safe yt-dlp auto-update (at most every 12h). Remembers the working versions of yt-dlp/urllib3/requests,
# updates with a 5-minute cap, smoke-tests a real lookup, and rolls back if the new set is broken.
cd "$HOME/music-stream" || exit 0
L="$HOME/music-stream/.ytdlp_update.lock"; S="$HOME/music-stream/.ytdlp_update.stamp"
mkdir "$L" 2>/dev/null || { [ -n "$(find "$L" -mmin +30 2>/dev/null)" ] && rm -rf "$L" && mkdir "$L"; } || exit 0
trap 'rm -rf "$L"' EXIT
[ -f "$S" ] && [ -z "$(find "$S" -mmin +720 2>/dev/null)" ] && exit 0
echo "$(date) update check"
smoke() { timeout 120 python -m yt_dlp --js-runtimes node -f "bestaudio[ext=m4a]/bestaudio" -g --no-warnings "https://www.youtube.com/watch?v=dQw4w9WgXcQ" 2>/dev/null | grep -q '^https://' \
          && timeout 60 python -c "import yt_dlp;y=yt_dlp.YoutubeDL({'quiet':True,'no_warnings':True,'extract_flat':True,'playlistend':3});e=y.extract_info('https://www.youtube.com/results?search_query=%E0%A4%A4%E0%A5%81%E0%A4%AE+hi+ho',download=False);assert e.get('entries')" >/dev/null 2>&1; }
OLD=$(python -m pip freeze 2>/dev/null | grep -iE '^(yt-dlp|urllib3|requests)==' | tr '\n' ' ')
timeout 300 python -m pip install -q -U "yt-dlp[default]" 2>&1 | tail -3
if smoke; then
  echo "$(date) ok: $(python -m yt_dlp --version)"; python -m yt_dlp --version > ytdlp_version.txt 2>/dev/null; touch "$S"
else
  echo "$(date) smoke FAILED after update; rolling back to: $OLD"
  [ -n "$OLD" ] && timeout 300 python -m pip install -q $OLD 2>&1 | tail -2
  if smoke; then echo "$(date) rollback ok"; touch "$S"; else echo "$(date) still failing after rollback (left as is)"; fi
  python -m yt_dlp --version > ytdlp_version.txt 2>/dev/null
fi
