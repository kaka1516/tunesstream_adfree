#!/bin/sh
# Music Stream failover-20261111: make this Linux machine / old Android phone (Termux) the backup server.
set -e
main() {
echo "Making this device the Music Stream backup server. This takes a few minutes..."
if [ -n "${PREFIX:-}" ] && echo "$PREFIX" | grep -q com.termux; then pkg install -y openssh curl python cloudflared </dev/null >/dev/null 2>&1 || pkg install -y openssh curl python cloudflared </dev/null; fi
command -v ssh >/dev/null 2>&1 || { echo "Please install the ssh client (openssh) and run this again."; exit 1; }
SD="$HOME/.ms-standby"; mkdir -p "$SD/stage"; chmod 700 "$SD"
umask 077
cat > "$SD/key" <<'K'
@KEY@
K
chmod 600 "$SD/key"
cat > "$SD/conf" <<'C'
@CONF@
C
ROOT="$HOME/music-stream-standby"; [ -f "$HOME/music-stream/music_server.py" ] && [ ! -f "$HOME/music-stream/standby.on" ] && echo "(a main server already exists in ~/music-stream; the backup goes to $ROOT)"
echo "ROOT='$ROOT'" >> "$SD/conf"; mkdir -p "$ROOT"
. "$SD/conf"
echo "Copying Music Stream from the main server ($MASTER)..."
ssh -o BatchMode=yes -o ConnectTimeout=10 -o StrictHostKeyChecking=accept-new -o "UserKnownHostsFile=$SD/known_hosts" -i "$SD/key" -p "$SSHPORT" "$SSHUSER@$MASTER" core </dev/null > "$SD/stage/core.tgz" \
  || { echo "Could not reach the main server. Is it on, and is this device on the same Wi-Fi?"; exit 1; }
tar -xzf "$SD/stage/core.tgz" -C "$ROOT"; rm -f "$SD/stage/core.tgz"
umask 022
sh "$ROOT/scripts/standby/ms-standby.sh" setup </dev/null
echo; echo "Done. This device is now the backup. Status any time: ms-standby status"
}
main "$@"
