#!/bin/sh
# Music Stream failover-20261111 - runs on the MAIN server only.
# It is the forced command of each backup server's ssh key (see authorized_keys "ms-standby"),
# so a backup can only ask for the things below. Read-only: it never changes anything here.
#   version  -> one line per bundle "name hash" + "app <sw cache version>"
#   status   -> "server ok|down" and "tunnel ready|running|stopped"
#   core|vendor|skins|vizdemo|assets -> tar.gz of that part of the code (no backups, caches or secrets)
#   data     -> tar.gz of users.json sessions.json user_data/ lcache/plays/plays.json
#   creds    -> tar.gz of the tunnel config + tunnel credentials (NOT cert.pem)
set -u
D="${MS_ROOT:-$HOME/music-stream}"
PORT="${MS_PORT:-8121}"
cd "$D" 2>/dev/null || { echo "no $D" >&2; exit 2; }
set -- ${SSH_ORIGINAL_COMMAND:-${1:-version}}
mode="${1:-version}"
CORE_FILES="music_server.py ms_users.py ms_cluster.py ms_standby.py famlang.py famkey.js famlang.js game.js player.html sw.js icon.svg icon-192.png icon-512.png favicon.ico THEMES.md THIRD_PARTY_NOTICES.md README.md install.sh install.ps1 start.sh start.bat"
CORE_DIRS="scripts docs licenses deploy"
core_paths() { for f in $CORE_FILES $CORE_DIRS; do [ -e "$f" ] && printf '%s\n' "$f"; done; }
paths_of() { case "$1" in
  core) core_paths;; vendor) echo vendor;; skins) echo skins;; vizdemo) echo viz-demo;; assets) echo assets;; *) return 1;; esac; }
lst() { # stable listing: path size mtime (no content read; cheap even for 200 MB of assets)
  find $(paths_of "$1") -type f ! -name '*.bak*' ! -name '*.pre*' ! -name '*.broken*' ! -name '*.tmp*' ! -name '*.log' ! -path '*/__pycache__/*' ! -path 'assets/viz/update/*' -printf '%p %s %T@\n' 2>/dev/null | LC_ALL=C sort; }
ver() { if [ "$1" = core ]; then core_paths | xargs -I{} find {} -type f ! -name '*.bak*' ! -name '*.pre*' ! -name '*.broken*' ! -name '*.tmp*' ! -path '*/__pycache__/*' 2>/dev/null | LC_ALL=C sort | xargs md5sum 2>/dev/null | md5sum | cut -c1-12
  else lst "$1" | md5sum | cut -c1-12; fi; }
tarb() { tar czf - --exclude='*.bak*' --exclude='*.pre*' --exclude='*.broken*' --exclude='*.tmp*' --exclude='*.log' --exclude='__pycache__' --exclude='assets/viz/update' $(paths_of "$1"); }
tunnel_state() {
  if ! pgrep -f 'cloudflared.*tunnel.*run' >/dev/null 2>&1; then echo stopped; return; fi
  for p in 20241 20242 20243 20244 20245; do
    c=$(curl -s -o /dev/null -m 2 -w '%{http_code}' "http://127.0.0.1:$p/ready" 2>/dev/null) || c=000
    case "$c" in 200) echo ready; return;; 503) echo down; return;; esac
  done
  echo running; }
case "$mode" in
  version) for b in core vendor skins vizdemo assets; do echo "$b $(ver $b)"; done
           echo "app $(sed -n "s/^const V='\([^']*\)'.*/\1/p" sw.js 2>/dev/null | head -1)";;
  status)  h=$(curl -s -m 4 "http://127.0.0.1:$PORT/health" 2>/dev/null); [ "$h" = ok ] && echo "server ok" || echo "server down"
           echo "tunnel $(tunnel_state)";;
  core|vendor|skins|vizdemo|assets) tarb "$mode";;
  data)    f=""; for x in users.json sessions.json user_data lcache/plays/plays.json; do [ -e "$x" ] && f="$f $x"; done
           tar czf - --exclude='*.tmp*' $f;;
  creds)   C="$HOME/.cloudflared"; T=$(sed -n 's/^tunnel:[[:space:]]*//p' "$C/config.yml" | head -1 | tr -d '"'"'"' \r')
           [ -n "$T" ] && [ -f "$C/$T.json" ] || { echo "no tunnel credentials" >&2; exit 3; }
           tar czf - -C "$C" config.yml "$T.json";;
  *) echo "unknown request" >&2; exit 2;;
esac
