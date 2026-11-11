#!/bin/sh
# Music Stream failover-20261111: BACKUP (standby) server for Linux / Raspberry Pi / old Android phone (Termux).
#   ms-standby setup     first-time setup (done for you by the pairing command)
#   ms-standby status    "Main server: OK / Backup: ready"
#   ms-standby off | on  switch failover off / on
#   ms-standby sync      copy code + data from the main server now
#   ms-standby tick      cron, every minute: 3 checks 20 s apart (takes over the link only when the main is down)
#   ms-standby takeover | release   (testing) start / stop the backup link by hand
# Settings: ~/.ms-standby/conf (written by the pairing command). Never prints secrets.
set -u
SD="$HOME/.ms-standby"; [ -f "$SD/conf" ] || { echo "Backup server is not set up here (no $SD/conf). Run the pairing command first."; exit 1; }
. "$SD/conf"   # MASTER SSHPORT SSHUSER MPORT PUBLIC ROOT PORT
PUBLIC="${PUBLIC%/}"
KEY="$SD/key"; KH="$SD/known_hosts"; ST="$SD/state"; STATUS="$SD/status.json"; EVL="$SD/events.log"
CFY="$SD/cf/standby.yml"; CFPID="$SD/cf.pid"; CFLOG="$SD/cf.log"; OFF="$SD/off"; MARK="$ROOT/standby.on"
mkdir -p "$SD/stage"; chmod 700 "$SD"
now(){ date +%s; }
ev(){ l="$(date '+%Y-%m-%d %H:%M:%S') $*"; echo "$l" >> "$EVL"; }
get(){ curl -fsS -m "${2:-6}" -H 'Cache-Control: no-cache' "$1" 2>/dev/null; }
sshm(){ ssh -o BatchMode=yes -o ConnectTimeout=8 -o ServerAliveInterval=10 -o StrictHostKeyChecking=accept-new -o "UserKnownHostsFile=$KH" -i "$KEY" -p "$SSHPORT" "$SSHUSER@$MASTER" "$1"; }
# state: fails okSince lastSync lastCode masterVer myVer
fails=0; okSince=0; lastSync=0; lastCode=0; masterVer=""; myVer=""
[ -f "$ST" ] && . "$ST"
save(){ cat > "$ST.tmp" <<E
fails=$fails
okSince=$okSince
lastSync=$lastSync
lastCode=$lastCode
masterVer='$masterVer'
myVer='$myVer'
E
mv -f "$ST.tmp" "$ST"; }
cf_alive(){ [ -f "$CFPID" ] && p=$(cat "$CFPID") && [ -n "$p" ] && kill -0 "$p" 2>/dev/null && grep -q standby.yml "/proc/$p/cmdline" 2>/dev/null; }
cf_start(){ cf_alive && return 0; [ -f "$CFY" ] || { ev "cannot take over: tunnel settings missing (run sync)"; return 1; }
  nohup cloudflared tunnel --no-autoupdate --metrics 127.0.0.1:20249 --config "$CFY" --logfile "$CFLOG" run >/dev/null 2>&1 &
  echo $! > "$CFPID"; ev "BACKUP TAKING OVER the public link (cloudflared pid $!)"; }
cf_stop(){ if cf_alive; then kill "$(cat "$CFPID")" 2>/dev/null; ev "backup link stopped: $1"; fi; rm -f "$CFPID"; }
srv_up(){ [ "$(get "http://127.0.0.1:$PORT/health" 4)" = ok ]; }
srv_pid(){ pgrep -f "python[0-9.]* .*ms_standby.py" 2>/dev/null | head -1; }
srv_ensure(){ pgrep -f "$SD/run-standby.sh" >/dev/null 2>&1 && return 0
  cat > "$SD/run-standby.sh" <<E
#!/bin/sh
cd "$ROOT"
PY=python3; [ -x "$ROOT/.venv/bin/python" ] && PY="$ROOT/.venv/bin/python"; command -v \$PY >/dev/null 2>&1 || PY=python
while [ -f "$MARK" ]; do echo "\$(date) start standby" >> run.log; \$PY ms_standby.py >> server.log 2>&1; echo "\$(date) exit \$?" >> run.log; sleep 5; done
E
  [ -f "$MARK" ] || return 0
  nohup sh "$SD/run-standby.sh" >/dev/null 2>&1 & ev "backup server started"; }
srv_restart(){ p=$(srv_pid); [ -n "$p" ] && kill "$p" 2>/dev/null && ev "backup server restarted: $1"; }
mstatus(){ sshm status 2>/dev/null; }
sync_data(){ t="$SD/stage/data"; rm -rf "$t"; mkdir -p "$t"
  sshm data > "$SD/stage/data.tgz" 2>/dev/null && [ -s "$SD/stage/data.tgz" ] && tar -xzf "$SD/stage/data.tgz" -C "$t" 2>/dev/null || return 1
  python3 -c "import json,sys;json.load(open(sys.argv[1]))" "$t/users.json" 2>/dev/null || { ev "data copy skipped: users.json did not parse"; return 1; }
  mkdir -p "$ROOT/user_data" "$ROOT/lcache/plays"
  for x in users.json sessions.json; do [ -f "$t/$x" ] && cp "$t/$x" "$ROOT/$x.sbtmp" && chmod 600 "$ROOT/$x.sbtmp" && mv -f "$ROOT/$x.sbtmp" "$ROOT/$x"; done
  for f in "$t"/user_data/*; do [ -f "$f" ] || continue; n=$(basename "$f"); cp "$f" "$ROOT/user_data/$n.sbtmp" && mv -f "$ROOT/user_data/$n.sbtmp" "$ROOT/user_data/$n"; done
  for f in "$ROOT"/user_data/*.json; do [ -f "$f" ] || continue; [ -f "$t/user_data/$(basename "$f")" ] || rm -f "$f"; done
  [ -f "$t/lcache/plays/plays.json" ] && cp "$t/lcache/plays/plays.json" "$ROOT/lcache/plays/plays.json.sbtmp" && mv -f "$ROOT/lcache/plays/plays.json.sbtmp" "$ROOT/lcache/plays/plays.json"
  rm -rf "$t" "$SD/stage/data.tgz"; return 0; }
sync_creds(){ d="$SD/cf"; mkdir -p "$d"; chmod 700 "$d"
  sshm creds > "$SD/stage/creds.tgz" 2>/dev/null && [ -s "$SD/stage/creds.tgz" ] && tar -xzf "$SD/stage/creds.tgz" -C "$d" 2>/dev/null || return 1
  rm -f "$SD/stage/creds.tgz"
  tid=$(sed -n 's/^tunnel:[[:space:]]*"\{0,1\}\([0-9a-f-]*\).*/\1/p' "$d/config.yml" | head -1); hn=$(sed -n 's/.*hostname:[[:space:]]*"\{0,1\}\([^" ]*\).*/\1/p' "$d/config.yml" | head -1)
  rm -f "$d/config.yml"; [ -n "$tid" ] && [ -f "$d/$tid.json" ] || return 1; chmod 600 "$d/$tid.json"
  printf 'tunnel: %s\ncredentials-file: %s\nprotocol: http2\ningress:\n  - hostname: %s\n    service: http://127.0.0.1:%s\n  - service: http_status:404\n' "$tid" "$d/$tid.json" "$hn" "$PORT" > "$CFY"; chmod 600 "$CFY"; }
sync_code(){ force="${1:-}"; v=$(sshm version 2>/dev/null) || return 1; [ -n "$v" ] || return 1
  touch "$SD/ver.txt"; restart=0
  printf '%s\n' "$v" > "$SD/ver.new"
  while read -r b h; do [ -n "$b" ] || continue
    if [ "$b" = app ]; then masterVer="$h"; continue; fi
    [ -z "$force" ] && grep -qx "$b $h" "$SD/ver.txt" && continue
    t="$SD/stage/$b"; rm -rf "$t"; mkdir -p "$t"
    sshm "$b" < /dev/null > "$SD/stage/$b.tgz" 2>/dev/null && tar -xzf "$SD/stage/$b.tgz" -C "$t" 2>/dev/null || { ev "code copy failed: $b"; return 1; }
    [ "$b" = core ] && [ ! -f "$t/music_server.py" ] && { ev "code copy incomplete"; return 1; }
    before=$(cat "$ROOT"/*.py 2>/dev/null | md5sum)
    (cd "$t" && tar cf - .) | (cd "$ROOT" && tar xf -); rm -rf "$t" "$SD/stage/$b.tgz"
    [ "$b" = core ] && [ "$(cat "$ROOT"/*.py 2>/dev/null | md5sum)" != "$before" ] && restart=1; ev "code updated from main: $b"
  done < "$SD/ver.new"
  mv -f "$SD/ver.new" "$SD/ver.txt"; myVer="$masterVer"
  [ "$restart" = 1 ] && ! cf_alive && srv_restart "new code from main"; return 0; }
wstatus(){ act=false; cf_alive && act=true; off=false; [ -f "$OFF" ] && off=true
  python3 - "$STATUS" "$EVL" <<E 2>/dev/null
import json,sys,os,time
ev=[]
try: ev=open(sys.argv[2],encoding='utf-8').read().splitlines()[-20:]
except Exception: pass
o={"ts":int(time.time()),"master":"$MASTER","master_ok":${1:-None},"active":$( $act && echo True || echo False ),"off":$( $off && echo True || echo False ),
   "public":"$PUBLIC","public_ok":${2:-None},"last_sync":$lastSync,"master_ver":"$masterVer","my_ver":"$myVer","events":ev}
t=sys.argv[1]+".tmp"; json.dump(o,open(t,"w")); os.replace(t,sys.argv[1])
E
}
check(){
  if [ -f "$OFF" ]; then cf_alive && cf_stop "switched off"; wstatus; return; fi
  srv_ensure
  lan=False; [ "$(get "http://$MASTER:$MPORT/health" 4)" = ok ] && lan=True
  pub=None
  if ! cf_alive; then
    if [ "$(get "$PUBLIC/health" 8)" = ok ]; then pub=True; fails=0; else pub=False; fails=$((fails+1))
      if [ "$fails" -ge 3 ]; then ms=""; [ "$lan" = True ] && ms=$(mstatus)
        if echo "$ms" | grep -q 'server ok' && echo "$ms" | grep -q 'tunnel ready'; then [ "$fails" = 3 ] && ev "public link failing but the main tunnel is up: not taking over"
        else cf_start; okSince=0; fi; fi; fi
  else
    ms=""; [ "$lan" = True ] && ms=$(mstatus)
    if [ "$lan" = True ] && echo "$ms" | grep -q 'server ok' && echo "$ms" | grep -Eq 'tunnel (ready|running)'; then
      if [ "$okSince" = 0 ]; then okSince=$(now); ev "main server is back; handing over in 60 s"
      elif [ $(( $(now) - okSince )) -ge 60 ]; then cf_stop "main server healthy for 60 s"; fails=0; okSince=0; fi
    else okSince=0; fi
  fi
  if ! cf_alive && [ "$lan" = True ]; then
    { [ $(( $(now) - lastCode )) -ge 1800 ] || [ -z "$myVer" ]; } && sync_code && lastCode=$(now)
    [ $(( $(now) - lastSync )) -ge 290 ] && { if sync_data; then lastSync=$(now); else ev "data copy from main failed"; fi; }
    [ -f "$CFY" ] || { sync_creds && ev "tunnel settings copied"; }
  fi
  wstatus "$lan" "$pub"; save; }
cron_on(){ command -v crontab >/dev/null 2>&1 || { echo "!! crontab missing: install cron (Termux: pkg install cronie termux-services)"; return 1; }; (crontab -l 2>/dev/null | grep -v 'ms-standby.sh tick'; echo "* * * * * sh $ROOT/scripts/standby/ms-standby.sh tick >/dev/null 2>&1") | crontab -; }
cron_off(){ command -v crontab >/dev/null 2>&1 || return 0; crontab -l 2>/dev/null | grep -v 'ms-standby.sh tick' | crontab -; }
case "${1:-status}" in
  tick) mkdir "$SD/lock" 2>/dev/null || { [ $(( $(now) - $(stat -c %Y "$SD/lock" 2>/dev/null || echo 0) )) -gt 300 ] && rm -rf "$SD/lock"; exit 0; }
        trap 'rmdir "$SD/lock" 2>/dev/null' EXIT; check; sleep 20; check; sleep 20; check;;
  sync) a=FAILED; b=FAILED; c=FAILED; sync_code "${2:-}" && { a=OK; lastCode=$(now); }; sync_data && { b=OK; lastSync=$(now); }; sync_creds && c=OK; save; wstatus
        echo "code: $a  data: $b  tunnel settings: $c";;
  off)  touch "$OFF"; cf_stop "switched off by you"; cron_off; rm -f "$MARK"; p=$(srv_pid); [ -n "$p" ] && kill "$p"; wstatus
        echo "Failover is OFF. This device will not take over the link. (Turn on again: ms-standby on)";;
  on)   rm -f "$OFF"; touch "$MARK"; cron_on; srv_ensure; echo "Failover is ON.";;
  takeover) cf_start; wstatus;;
  release)  cf_stop "released by hand"; wstatus;;
  setup)
    echo "== 1/5 Programs"; if [ -n "${PREFIX:-}" ] && echo "$PREFIX" | grep -q com.termux; then pkg install -y cloudflared openssh curl python >/dev/null 2>&1 || pkg install -y cloudflared openssh curl python; fi
    command -v cloudflared >/dev/null 2>&1 || echo "!! cloudflared is missing: install it (https://pkg.cloudflare.com or github releases) and run: ms-standby setup"
    { [ -f "$ROOT/music.env" ] && python3 -c "import yt_dlp" 2>/dev/null; } || sh "$ROOT/install.sh" --yes --port "$PORT"
    echo "== 2/5 Copy code, accounts, likes, playlists and link settings"; touch "$MARK"; rm -f "$OFF"; sync_code force; sync_data && lastSync=$(now); sync_creds; save
    echo "== 3/5 Every-minute check (cron)"; command -v crontab >/dev/null 2>&1 || { [ -n "${PREFIX:-}" ] && pkg install -y cronie termux-services >/dev/null 2>&1; }; cron_on
    if [ -n "${PREFIX:-}" ]; then mkdir -p "$HOME/.termux/boot"; printf '#!/data/data/com.termux/files/usr/bin/sh\ntermux-wake-lock\ncrond 2>/dev/null\nsh %s tick >/dev/null 2>&1 &\n' "$ROOT/scripts/standby/ms-standby.sh" > "$HOME/.termux/boot/ms-standby"; chmod +x "$HOME/.termux/boot/ms-standby"; pgrep crond >/dev/null || crond; fi
    mkdir -p "$HOME/bin"; ln -sf "$ROOT/scripts/standby/ms-standby.sh" "$HOME/bin/ms-standby"; chmod +x "$ROOT/scripts/standby/ms-standby.sh"
    echo "== 4/5 Start the backup server"; srv_ensure; i=0; while [ $i -lt 40 ] && ! get "http://127.0.0.1:$PORT/api/server-role" 4 | grep -q standby; do sleep 3; i=$((i+1)); done
    echo "== 5/5 Status"; exec sh "$0" status;;
  *) lan=no; [ "$(get "http://$MASTER:$MPORT/health" 4)" = ok ] && lan=yes; ms=""; [ $lan = yes ] && ms=$(mstatus)
     who=$(get "$PUBLIC/api/server-role" 8); code=$?
     echo
     if [ $lan = yes ] && echo "$ms" | grep -Eq 'tunnel (ready|running)'; then echo "Main server : OK"; elif [ $lan = yes ]; then echo "Main server : UP, but its link is $(echo "$ms" | sed -n 's/tunnel //p')"; else echo "Main server : DOWN (not answering on home Wi-Fi)"; fi
     if [ -f "$OFF" ]; then echo "Backup      : OFF (switched off)"; elif cf_alive; then echo "Backup      : SERVING the link now"; elif srv_up; then echo "Backup      : ready"; else echo "Backup      : NOT ready (backup server not running)"; fi
     if echo "$who" | grep -q standby; then echo "Link now on : BACKUP"; elif [ "$(get "$PUBLIC/health" 8)" = ok ]; then echo "Link now on : main server"; else echo "Link now on : nobody (link down)"; fi
     [ "$lastSync" -gt 0 ] 2>/dev/null && echo "Last copy   : $(( ($(now) - lastSync) / 60 )) min ago" || echo "Last copy   : never"
     echo "Versions    : main $masterVer / backup $myVer"; echo "Details     : http://127.0.0.1:$PORT/standby";;
esac
