#!/bin/sh
# Music Stream - make your install reachable from the internet (Linux / Raspberry Pi / Android Termux).
#   ms-public                 menu (A = instant temporary link, B = permanent own address)
#   ms-public quick [--autostart] [--no-open]     A: instant link, no account (changes when restarted)
#   ms-public permanent [--hostname music.example.com] [--tunnel-name music-stream] [--dry-run] [--yes]
#   ms-public status | off
# Private files: <app>/.public/ and ~/.cloudflared/ (never committed; see .gitignore).
set -u
APP="$(cd "$(dirname "$0")/.." && pwd)"; PUB="$APP/.public"; LINK="$APP/PUBLIC_LINK.txt"; CFG="$PUB/config.yml"; MODE="$PUB/mode"
CF="$PUB/cloudflared"; HOSTNAME_ARG=""; TNAME="music-stream"; AUTO=0; NOOPEN=0; DRY=0; YES=0
CMD="${1:-menu}"; [ $# -gt 0 ] && shift
while [ $# -gt 0 ]; do case "$1" in
  --autostart) AUTO=1;; --no-open) NOOPEN=1;; --dry-run) DRY=1;; --yes|-y) YES=1;;
  --hostname) HOSTNAME_ARG="$2"; shift;; --tunnel-name) TNAME="$2"; shift;; *) echo "unknown option $1"; exit 2;; esac; shift; done
say(){ printf '%s\n' "$*"; }
fail(){ printf '\n%s\n' "$*" >&2; exit 1; }
envval(){ sed -n "s/^[[:space:]]*$1[[:space:]]*=[[:space:]]*//p" "$APP/music.env" 2>/dev/null | tail -1 | tr -d '\r'; }
PORT="$(envval MUSIC_PORT)"; PORT="${PORT:-8125}"
PY="$(envval YTDLP_PY)"; [ -x "${PY:-/nonexistent}" ] || PY="$(command -v python3 || command -v python || echo python3)"
IS_TERMUX=0; [ -n "${PREFIX:-}" ] && echo "$PREFIX" | grep -q com.termux && IS_TERMUX=1
get(){ # get URL -> prints "code"
  if command -v curl >/dev/null 2>&1; then curl -s -o /dev/null -w '%{http_code}' --max-time 8 "$1"
  else "$PY" -c "import urllib.request,sys
try: print(urllib.request.urlopen(sys.argv[1],timeout=8).status)
except Exception as e: print(getattr(e,'code',0))" "$1"; fi; }
openurl(){ [ "$NOOPEN" = 1 ] && return 0; if [ "$IS_TERMUX" = 1 ] && command -v termux-open-url >/dev/null 2>&1; then termux-open-url "$1"
  elif command -v xdg-open >/dev/null 2>&1 && [ -n "${DISPLAY:-}${WAYLAND_DISPLAY:-}" ]; then xdg-open "$1" >/dev/null 2>&1 & fi; return 0; }
mine(){ # pids of cloudflared started by this script (command line mentions $PUB)
  for d in /proc/[0-9]*; do c="$(tr '\0' ' ' < "$d/cmdline" 2>/dev/null)" || continue
    case "$c" in *cloudflared*"$PUB/"*) echo "${d#/proc/}";; esac; done; }
stop_mine(){ for p in $(mine); do kill "$p" 2>/dev/null; done; rm -f "$PUB/cloudflared.pid"; }
assert_safe(){
  [ -f "$APP/music_server.py" ] || fail "Music Stream is not installed here ($APP). Run install.sh first."
  grep -q '"role"[[:space:]]*:[[:space:]]*"admin"' "$APP/users.json" 2>/dev/null || \
    fail "Not safe yet: there is no admin account.
Open http://127.0.0.1:$PORT/setup in a browser ON THIS DEVICE, create the admin, then run this again."
  case "$(envval MUSIC_OPEN | tr 'A-Z' 'a-z')" in 1|true|yes|on) fail "Not safe: MUSIC_OPEN is on in $APP/music.env (anyone could use it without logging in).
Change it to MUSIC_OPEN=0, then run this again.";; esac
  if [ "$(get "http://127.0.0.1:$PORT/health")" != 200 ]; then
    say "Starting Music Stream first..."; sh "$APP/start.sh" >/dev/null 2>&1; i=0
    while [ $i -lt 30 ] && [ "$(get "http://127.0.0.1:$PORT/health")" != 200 ]; do sleep 1; i=$((i+1)); done
    [ "$(get "http://127.0.0.1:$PORT/health")" = 200 ] || fail "Music Stream did not start. Run ./start.sh and check server.log."
  fi; }
get_cloudflared(){
  mkdir -p "$PUB"; chmod 700 "$PUB" 2>/dev/null
  [ -x "$CF" ] && return 0
  if command -v cloudflared >/dev/null 2>&1; then ln -sf "$(command -v cloudflared)" "$CF"; return 0; fi
  if [ "$IS_TERMUX" = 1 ]; then say "Installing cloudflared..."; [ "$DRY" = 1 ] && { say "[dry-run] pkg install -y cloudflared"; return 0; }
    pkg install -y cloudflared >/dev/null 2>&1 && ln -sf "$(command -v cloudflared)" "$CF" && return 0; fi
  case "$(uname -m)" in x86_64|amd64) A=amd64;; aarch64|arm64) A=arm64;; armv7*|armv6*|arm) A=arm;; i?86) A=386;; *) fail "No cloudflared download for $(uname -m).";; esac
  U="https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-$A"
  say "Downloading cloudflared (Cloudflare's free tunnel program)..."
  [ "$DRY" = 1 ] && { say "[dry-run] download $U -> $CF"; return 0; }
  if command -v curl >/dev/null 2>&1; then curl -fsSL --retry 3 -o "$CF" "$U"; else wget -qO "$CF" "$U"; fi || fail "Could not download cloudflared. Check the internet connection."
  chmod +x "$CF"; }
autostart_on(){ # $1 = command line to run at boot
  if [ "$IS_TERMUX" = 1 ]; then mkdir -p "$HOME/.termux/boot"; printf '#!/data/data/com.termux/files/usr/bin/sh\ntermux-wake-lock 2>/dev/null\nsleep 20\n%s\n' "$1" > "$HOME/.termux/boot/music-stream-public.sh"
    chmod +x "$HOME/.termux/boot/music-stream-public.sh"; say "Starts by itself after a reboot (needs the Termux:Boot app, opened once)."
  elif command -v systemctl >/dev/null 2>&1 && systemctl --user show-environment >/dev/null 2>&1; then mkdir -p "$HOME/.config/systemd/user"
    printf '[Unit]\nDescription=Music Stream public link\nAfter=network-online.target\n[Service]\nType=oneshot\nRemainAfterExit=yes\nExecStartPre=/bin/sleep 15\nExecStart=/bin/sh -c "%s"\n[Install]\nWantedBy=default.target\n' "$1" > "$HOME/.config/systemd/user/music-stream-public.service"
    systemctl --user daemon-reload && systemctl --user enable music-stream-public.service >/dev/null 2>&1; say "Starts by itself at login/boot (systemd user service; for boot without login: loginctl enable-linger)."
  elif command -v crontab >/dev/null 2>&1; then (crontab -l 2>/dev/null | grep -v 'ms-public.sh'; echo "@reboot sleep 30; $1") | crontab -; say "Starts by itself after a reboot (crontab)."
  else say "Could not set up auto-start on this system; run ms-public again after a reboot."; fi; }
autostart_off(){ rm -f "$HOME/.termux/boot/music-stream-public.sh"
  if [ -f "$HOME/.config/systemd/user/music-stream-public.service" ]; then systemctl --user disable music-stream-public.service >/dev/null 2>&1; rm -f "$HOME/.config/systemd/user/music-stream-public.service"; systemctl --user daemon-reload 2>/dev/null; fi
  if command -v crontab >/dev/null 2>&1 && crontab -l 2>/dev/null | grep -q 'ms-public.sh'; then crontab -l 2>/dev/null | grep -v 'ms-public.sh' | crontab -; fi; return 0; }
SELF="sh '$APP/scripts/ms-public.sh'"
quick(){
  assert_safe; get_cloudflared; [ "$DRY" = 1 ] && { say "[dry-run] would run: $CF tunnel --no-autoupdate --protocol http2 --url http://127.0.0.1:$PORT"; return 0; }
  stop_mine; LOG="$PUB/quick.log"; rm -f "$LOG"
  say "Opening an instant public link (takes about 10-30 seconds)..."
  nohup "$CF" tunnel --no-autoupdate --protocol http2 --logfile "$LOG" --url "http://127.0.0.1:$PORT" >/dev/null 2>&1 &
  echo $! > "$PUB/cloudflared.pid"; URL=""; i=0
  while [ $i -lt 60 ] && [ -z "$URL" ]; do sleep 1; i=$((i+1)); URL="$(grep -o 'https://[a-z0-9-]*\.trycloudflare\.com' "$LOG" 2>/dev/null | head -1)"; done
  [ -n "$URL" ] || { stop_mine; fail "Could not open a link. Your network may block Cloudflare (outbound port 7844). Details: $LOG"; }
  OK=0; i=0; while [ $i -lt 30 ] && [ $OK = 0 ]; do sleep 2; i=$((i+1)); [ "$(get "$URL/health")" = 200 ] && OK=1; done
  if [ $OK = 0 ] && ! grep -q 'Registered tunnel connection' "$LOG" 2>/dev/null; then stop_mine
    fail "Cloudflare gave a link but this device could not connect to it. Your network probably blocks Cloudflare tunnels
(outbound port 7844). Try another network (for example phone data), or see docs/MAKE_PUBLIC.md. Details: $LOG"; fi
  echo quick > "$MODE"
  printf 'Your Music Stream public link (temporary):\n%s\n\nIt changes every time the device or the link restarts.\nStatus: ms-public status    Turn off: ms-public off\n' "$URL" > "$LINK"
  [ "$AUTO" = 1 ] && autostart_on "$SELF quick --no-open"
  say ""; say "PUBLIC LINK: $URL"; [ $OK = 1 ] || say "(Cloudflare is still warming up; if the page does not load, wait a minute and refresh.)"
  say "Saved in: $LINK"; say "Sign in with your Music Stream account. Share the link only with people you trust."; openurl "$URL"; }
run_cf(){ say "> cloudflared $*"; [ "$DRY" = 1 ] && return 0; "$CF" "$@"; }
permanent(){
  assert_safe; get_cloudflared
  say ""; say "Permanent address - you need (both free/cheap):"
  say "  1. A free Cloudflare account (https://dash.cloudflare.com/sign-up)"
  say "  2. A domain name added to that account (for example music.yourname.com)"
  H="$HOSTNAME_ARG"; if [ -z "$H" ]; then printf 'Type the address you want (for example music.yourname.com): '; read -r H </dev/tty || H=""; fi
  H="$(printf '%s' "$H" | tr 'A-Z' 'a-z' | tr -d ' ')"
  printf '%s' "$H" | grep -Eq '^[a-z0-9]([a-z0-9-]*[a-z0-9])?(\.[a-z0-9]([a-z0-9-]*[a-z0-9])?)+$' || fail "That doesn't look like a web address: '$H'"
  printf '%s' "$TNAME" | grep -Eq '^[A-Za-z0-9_-]{1,60}$' || fail "Tunnel name may only use letters, numbers, - and _."
  CFH="$HOME/.cloudflared"
  if [ ! -f "$CFH/cert.pem" ]; then say "Step 1: open the link that appears, log in to Cloudflare, click your domain, then 'Authorize'."; run_cf tunnel login || fail "Cloudflare login did not finish."
  else say "Step 1: already logged in to Cloudflare ($CFH/cert.pem)."; fi
  say "Step 2: creating (or re-using) the tunnel '$TNAME'..."; ID=""
  [ "$DRY" = 1 ] || ID="$("$CF" tunnel list --output json 2>/dev/null | "$PY" -c "import json,sys
try: print(next((t['id'] for t in json.load(sys.stdin) if t.get('name')==sys.argv[1]),''))
except Exception: print('')" "$TNAME")"
  if [ -n "$ID" ] && [ ! -f "$CFH/$ID.json" ]; then
    say "The tunnel '$TNAME' exists but its key file is not on this device (for example after a wipe)."
    a=y; [ "$YES" = 1 ] || { printf 'Delete it and create it again? Your address stays the same. [Y/n] '; read -r a </dev/tty || a=y; }
    case "$a" in n|N) fail "Stopped. Copy $ID.json from your backup into $CFH, or use --tunnel-name with a new name.";; esac
    run_cf tunnel cleanup "$TNAME"; run_cf tunnel delete -f "$TNAME" || fail "Could not delete the old tunnel."; ID=""; fi
  if [ -z "$ID" ]; then OUT="$(run_cf tunnel create "$TNAME" 2>&1)" || fail "Could not create the tunnel: $OUT"; say "$OUT"
    ID="$(printf '%s' "$OUT" | grep -oE '[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}' | head -1)"; [ "$DRY" = 1 ] && ID="${ID:-<tunnel-id>}"
    [ -n "$ID" ] || fail "Could not read the new tunnel id."; fi
  say "Step 3: pointing $H at this device..."; run_cf tunnel route dns --overwrite-dns "$TNAME" "$H" || fail "Could not set the address. Is $H's domain in your Cloudflare account?"
  Y="tunnel: $ID
credentials-file: $CFH/$ID.json
protocol: http2
ingress:
  - hostname: $H
    service: http://127.0.0.1:$PORT
  - service: http_status:404"
  if [ "$DRY" = 1 ]; then say "[dry-run] would write $CFG:"; printf '%s\n' "$Y" | sed 's/^/    /'; say "[dry-run] would start: $CF tunnel --no-autoupdate --config $CFG run (and auto-start at boot)"; return 0; fi
  mkdir -p "$PUB"; printf '%s\n' "$Y" > "$CFG"; chmod 600 "$CFG"
  say "Step 4: starting it now and after every reboot..."; startpermanent; autostart_on "$SELF startpermanent"; echo permanent > "$MODE"
  printf 'Your Music Stream permanent address:\nhttps://%s\n\nIt keeps working after restarts. Turn off: ms-public off\n' "$H" > "$LINK"
  say ""; say "PERMANENT ADDRESS: https://$H (can take 1-2 minutes to start working)"; openurl "https://$H"; }
startpermanent(){ [ -f "$CFG" ] || fail "No permanent address set up yet (run: ms-public permanent)."; [ -x "$CF" ] || get_cloudflared
  stop_mine; nohup "$CF" tunnel --no-autoupdate --logfile "$PUB/permanent.log" --config "$CFG" run >/dev/null 2>&1 & echo $! > "$PUB/cloudflared.pid"; }
status(){ M="$(cat "$MODE" 2>/dev/null || echo none)"
  if [ -n "$(mine)" ]; then say "Public link is ON ($M)."; [ -f "$LINK" ] && say "Address: $(sed -n 2p "$LINK")"; else say "Public link is OFF. Music Stream is only on this device/network."; fi
  if [ -f "$HOME/.termux/boot/music-stream-public.sh" ] || [ -f "$HOME/.config/systemd/user/music-stream-public.service" ] || crontab -l 2>/dev/null | grep -q ms-public.sh; then say "Starts by itself after reboot: yes"; else say "Starts by itself after reboot: no"; fi; }
off(){ stop_mine; autostart_off; rm -f "$LINK" "$MODE"; say "Public link is OFF. Music Stream still works on this device (http://127.0.0.1:$PORT)."
  [ -f "$CFG" ] && say "Your permanent address settings are kept; run 'ms-public permanent' to turn it back on."; return 0; }
case "$CMD" in
  quick|a|A) quick;; permanent|b|B) permanent;; startpermanent) startpermanent;; status|s|S) status;; off|o|O) off;;
  menu) say "Make Music Stream public"; say ""
    say "  A  Instant link right now - no account needed. The link changes when the device restarts."
    say "  B  Permanent address of your own (needs a free Cloudflare account and a domain name)."
    say "  S  Show status"; say "  O  Turn the public link off"; say "  Q  Quit"
    printf 'Choose A, B, S, O or Q: '; read -r c </dev/tty || c=q
    case "$c" in a|A) printf 'Start the instant link by itself after every reboot? [y/N] '; read -r r </dev/tty || r=n; case "$r" in y|Y) AUTO=1;; esac; quick;;
      b|B) permanent;; s|S) status;; o|O) off;; *) say "Nothing changed.";; esac;;
  -h|--help|help) sed -n '2,7p' "$0";;
  *) say "usage: ms-public [quick|permanent|status|off]"; exit 2;; esac
