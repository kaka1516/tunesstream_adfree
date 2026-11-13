#!/data/data/com.termux/files/usr/bin/sh
# watchdog: restart Music Stream / AdGuard / Tailscale if they die
# guard-20261113: health-check :8121, not just pgrep. Worker processes also match
# music_server.py, so a dead front was previously ignored and the public port stayed down.
health() { curl -sf -m 2 "http://127.0.0.1:$1/health" >/dev/null; }
if ! health 8121; then
  if health 8221 && [ -f "$HOME/music-stream/ms_front_only.py" ]; then
    if ! pgrep -f 'ms_front_only.py' >/dev/null; then
      nohup python -u "$HOME/music-stream/ms_front_only.py" >> "$HOME/music-stream/front-only.log" 2>&1 &
    fi
  elif ! pgrep -f 'music-stream/run.sh' >/dev/null; then
    nohup sh "$HOME/music-stream/run.sh" >/dev/null 2>&1 &
  fi
fi
pgrep -f AdGuardHome >/dev/null || (nohup "$HOME/agh/run.sh" >/dev/null 2>&1 &)
pgrep -f tailscaled >/dev/null || (nohup "$HOME/agh/ts.sh" >/dev/null 2>&1 &)
pgrep -x sshd >/dev/null || sshd
# restart named Cloudflare tunnel if it stops (does not touch Funnel)
if ! pgrep -f "/cloudflared tunnel run tunestream-phone" >/dev/null; then
  nohup "$(command -v cloudflared)" tunnel run tunestream-phone >> "$HOME/cf/tunnel.log" 2>&1 &
fi

# weekly visuals catalog update (Monday-or-any 04:00-04:09 IST), at most once per 6 days
# low priority; never restarts the music serve
VIZUP="$HOME/music-stream/scripts/viz-update.sh"
VIZDIS="$HOME/music-stream/assets/viz/update/disabled"
VIZSTAMP="$HOME/music-stream/assets/viz/update/last-cron"
if [ -f "$VIZUP" ] && [ ! -f "$VIZDIS" ]; then
  hr=$(date +%H)
  mn=$(date +%M)
  if [ "$hr" = "04" ] && [ "$mn" -lt 10 ]; then
    run=1
    if [ -f "$VIZSTAMP" ]; then
      # skip if stamp is less than 6 days old
      now=$(date +%s)
      then=$(date -r "$VIZSTAMP" +%s 2>/dev/null || echo 0)
      age=$((now-then))
      [ "$age" -lt 518400 ] && run=0
    fi
    if [ "$run" = "1" ]; then
      touch "$VIZSTAMP"
      nohup sh "$VIZUP" >/dev/null 2>&1 &
    fi
  fi
fi
