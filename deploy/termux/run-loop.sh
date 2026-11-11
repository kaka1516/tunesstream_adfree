#!/data/data/com.termux/files/usr/bin/sh
# restart loop for Music Stream server (speed-20261110: yt-dlp auto-update runs in the background, never blocks a start,
# and is rolled back automatically if the new version fails a smoke test - see ytdlp_update.sh)
cd "$HOME/music-stream"
while true; do
  nohup sh "$HOME/music-stream/ytdlp_update.sh" >> ms-update.log 2>&1 &
  echo "$(date) start" >> run.log
  python music_server.py >> server.log 2>&1
  echo "$(date) exit $?" >> run.log
  sleep 5
done
