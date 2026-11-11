#!/bin/bash
cd "$(dirname "$0")"; K=$(grep MUSIC_KEY music.env|cut -d= -f2); B=http://127.0.0.1:8120; ok=0; bad=0
chk(){ if eval "$2"; then echo "PASS $1"; ok=$((ok+1)); else echo "FAIL $1"; bad=$((bad+1)); fi; }
chk health '[ "$(curl -s $B/health)" = ok ]'
chk search '[ $(curl -s -m 90 "$B/api/search?q=beatles&k=$K" | python3 -c "import json,sys;print(len(json.load(sys.stdin)))") -gt 0 ]'
chk lyrics_lrclib 'curl -s -m 40 "$B/api/lyrics?k=$K&t=Yesterday&a=The%20Beatles&d=125" | grep -q synced'
chk lyrics_unknown_returns_fast '[ $(curl -s -m 40 -o /dev/null -w "%{http_code}" "$B/api/lyrics?k=$K&t=zzqx%20nonexistent%20$RANDOM&a=nobody") = 200 ]'
chk audio_range_206 '[ $(curl -s -m 90 -o /dev/null -w "%{http_code}" -H "Range: bytes=500000-600000" "$B/audio?k=$K&id=QDYfEBY9NM4") = 206 ]'
chk stream_range_206 '[ $(curl -s -m 90 -o /dev/null -w "%{http_code}" -H "Range: bytes=500000-600000" "$B/stream?k=$K&id=QDYfEBY9NM4") = 206 ]'
chk stream_norange_mp3 'curl -s --max-time 15 -o /tmp/st.mp3 "$B/stream?k=$K&id=QDYfEBY9NM4"; ffprobe -v error -show_streams /tmp/st.mp3 | grep -q codec_name=mp3'
chk video_range_206_h264 '[ $(curl -s -m 90 -o /tmp/v.mp4 -w "%{http_code}" -H "Range: bytes=0-400000" "$B/video?k=$K&id=QDYfEBY9NM4") = 206 ] && grep -aq avc1 /tmp/v.mp4'
chk page '[ $(curl -s -o /dev/null -w "%{http_code}" "$B/?k=$K") = 200 ]'
for x in /sw.js /manifest.webmanifest /icon-192.png /favicon.ico; do chk "asset$x" '[ $(curl -s -o /dev/null -w "%{http_code}" $B$x) = 200 ]'; done
echo "== $ok passed, $bad failed"
