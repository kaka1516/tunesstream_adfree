#!/usr/bin/env sh
# Music Stream one-command installer (ms-v75) for Linux / Raspberry Pi / Termux (Android) / OpenWrt (musl).
#   sh install.sh [--yes] [--start] [--no-ffmpeg|--with-ffmpeg] [--no-node] [--port N] [--lan] [--autostart] [--print-autostart] [--update-ytdlp]
# One step:  sh install.sh --yes --start   (installs, writes music.env with a random key, starts on http://127.0.0.1:8125)
# What it does: installs OS packages (python3, optional ffmpeg, optional nodejs), creates ./.venv when the platform
# supports venv, installs yt-dlp (+ optional extras) into it, writes music.env (only keys that are missing), and prints how
# to start. It does NOT start the server, does NOT enable autostart unless you pass --autostart, and never prints your key.
# Run from the unpacked Music Stream folder. Re-running is safe (idempotent).
set -eu
cd "$(dirname "$0")"
YES=0; START=0; FF=1; FFW=0; NODE=1; PORT=8125; LAN=0; AUTO=0; UPD=0; PRINT=0
while [ $# -gt 0 ]; do case "$1" in
  --yes|-y) YES=1;; --start) START=1;; --no-ffmpeg) FF=0;; --with-ffmpeg) FFW=1;; --no-node) NODE=0;; --port) PORT="$2"; shift;; --lan) LAN=1;;
  --autostart) AUTO=1;; --print-autostart) PRINT=1;; --update-ytdlp) UPD=1;; -h|--help) sed -n '2,10p' "$0"; exit 0;; *) echo "unknown option $1"; exit 2;; esac; shift; done
say(){ printf '%s\n' "== $*"; }
run(){ if [ "$YES" = 1 ]; then "$@" || say "step failed: $* (continuing with what is already installed)"; return 0; fi
  printf 'Will run: %s\nProceed? [y/N] ' "$*"; a=n; read -r a </dev/tty 2>/dev/null || read -r a || a=n   # no tty / EOF = no
  case "$a" in y|Y) "$@" || say "step failed: $* (continuing)";; *) echo "skipped";; esac; return 0; }
DIR="$(pwd)"
case "$DIR" in *'"'*|*"'"*|*'$'*|*'`'*|*'\'*) echo "install path contains quote/\$/backtick/backslash characters; move it to a plain path"; exit 2;; esac
sedesc(){ printf '%s' "$1" | sed 's/[&#|]/\\&/g'; }          # escape for sed replacement (delimiter #)
render(){ # render(template, python) -> stdout ; systemd needs % doubled
  d="$(sedesc "$DIR")"; p="$(sedesc "$2")"
  case "$1" in *.service) d="$(printf '%s' "$d" | sed 's/%/%%/g')"; p="$(printf '%s' "$p" | sed 's/%/%%/g')";; esac
  sed "s#@DIR@#$d#g;s#@PY@#$p#g" "$1"; }
SUDO=""; [ "$(id -u 2>/dev/null || echo 0)" != 0 ] && command -v sudo >/dev/null 2>&1 && SUDO=sudo
# ---- platform ----
if [ -f /etc/openwrt_release ]; then OS=openwrt
elif [ -n "${PREFIX:-}" ] && echo "$PREFIX" | grep -q com.termux; then OS=termux
elif command -v apt-get >/dev/null 2>&1; then OS=debian
elif command -v apk >/dev/null 2>&1; then OS=alpine
elif command -v dnf >/dev/null 2>&1; then OS=fedora
elif command -v pacman >/dev/null 2>&1; then OS=arch
else OS=generic; fi
say "platform: $OS ($(uname -m))"
case "$OS" in openwrt) TPL=deploy/openwrt/music-stream.init;; termux) TPL=deploy/termux/music-stream-boot.sh;; *) TPL=deploy/systemd/music-stream.service;; esac
if [ "$PRINT" = 1 ]; then  # view-only: render the autostart template for this platform and stop (installs nothing)
  P0="$DIR/.venv/bin/python"; [ -x "$P0" ] || P0="$(command -v python3 || echo python3)"; render "$TPL" "$P0"; exit 0; fi
if [ "$OS" = openwrt ] && [ "$FF" = 1 ] && [ "$FFW" = 0 ]; then say "OpenWrt: ffmpeg skipped by default (large, CPU-heavy); pass --with-ffmpeg on a strong router"; FF=0; fi
PK=""; case "$OS" in
  openwrt) PK="python3 python3-pip python3-venv ca-bundle"; [ "$NODE" = 1 ] && PK="$PK node"; [ "$FF" = 1 ] && PK="$PK ffmpeg"
           run opkg update; run opkg install $PK || say "some opkg packages are not available for this target (node/ffmpeg are optional)";;
  termux)  PK="python"; [ "$NODE" = 1 ] && PK="$PK nodejs-lts"; [ "$FF" = 1 ] && PK="$PK ffmpeg"; run pkg install -y $PK;;
  debian)  PK="python3 python3-venv python3-pip ca-certificates"; [ "$NODE" = 1 ] && PK="$PK nodejs"; [ "$FF" = 1 ] && PK="$PK ffmpeg"; run $SUDO apt-get update; run $SUDO apt-get install -y $PK;;
  alpine)  PK="python3 py3-pip ca-certificates"; [ "$NODE" = 1 ] && PK="$PK nodejs"; [ "$FF" = 1 ] && PK="$PK ffmpeg"; run $SUDO apk add $PK;;
  fedora)  PK="python3 python3-pip"; [ "$NODE" = 1 ] && PK="$PK nodejs"; [ "$FF" = 1 ] && PK="$PK ffmpeg-free"; run $SUDO dnf install -y $PK;;
  arch)    PK="python python-pip"; [ "$NODE" = 1 ] && PK="$PK nodejs"; [ "$FF" = 1 ] && PK="$PK ffmpeg"; run $SUDO pacman -S --needed --noconfirm $PK;;
  *) say "unknown OS: install python3 (>=3.9), optionally ffmpeg and nodejs, yourself";; esac
PY=python3; command -v python3 >/dev/null 2>&1 || PY=python
"$PY" -c 'import sys;assert sys.version_info>=(3,9)' || { echo "need Python >= 3.9"; exit 1; }
# ---- python env (venv where possible; Termux/OpenWrt fall back to --user) ----
VPY="$PY"
if [ "$OS" != termux ] && "$PY" -m venv .venv >/dev/null 2>&1; then VPY="$(pwd)/.venv/bin/python"; say "venv: .venv"; PIPX=""
else say "venv unavailable: using pip --user"; PIPX="--user"; fi
EXTRA="unidecode syncedlyrics"; [ "$OS" = openwrt ] && EXTRA="unidecode"   # lyrics lib is optional; skipped on routers
"$VPY" -m pip install $PIPX -U pip >/dev/null 2>&1 || true
"$VPY" -m pip install $PIPX "yt-dlp[default]" $EXTRA || "$VPY" -m pip install $PIPX yt-dlp
# ---- music.env: add only missing keys; MUSIC_KEY is generated by the server on first start (never printed here) ----
touch music.env; chmod 600 music.env 2>/dev/null || true
[ -s music.env ] && [ -n "$(tail -c1 music.env)" ] && printf '\n' >> music.env   # never glue a key onto an unterminated last line
addk(){ if grep -q "^$1=" music.env; then if [ "${3:-}" = say ]; then say "keeping your existing $1 in music.env"; fi; else printf '%s=%s\n' "$1" "$2" >> music.env; fi; return 0; }
case "$PORT" in 8120|8121) echo "port $PORT is reserved for another copy; using 8125"; PORT=8125;; esac
addk MUSIC_PORT "$PORT" say; addk MUSIC_BIND "$([ "$LAN" = 1 ] && echo 0.0.0.0 || echo 127.0.0.1)" say; addk YTDLP_PY "$VPY" say; addk YTDLP_AUTO_UPDATE 0 say
if command -v ffmpeg >/dev/null 2>&1; then addk FFMPEG "$(command -v ffmpeg)"; else say "no ffmpeg: direct playback works; mp3 download (/dl) and the transcoded fallback stream are disabled"; fi
if command -v node >/dev/null 2>&1; then addk YTDLP_JS_RUNTIME node; elif command -v deno >/dev/null 2>&1; then addk YTDLP_JS_RUNTIME deno; else addk YTDLP_JS_RUNTIME none; say "no JS runtime: yt-dlp may fail on some YouTube videos; install nodejs if playback breaks"; fi
grep -q '^MUSIC_KEY=' music.env || printf 'MUSIC_KEY=%s\n' "$("$VPY" -c 'import secrets;print(secrets.token_urlsafe(24))')" >> music.env   # random, never printed
[ "$UPD" = 1 ] && sh scripts/update-ytdlp.sh || true
# ---- autostart (opt-in only) ----
if [ "$AUTO" = 1 ]; then case "$OS" in
  openwrt) render "$TPL" "$VPY" > /etc/init.d/music-stream && chmod +x /etc/init.d/music-stream && /etc/init.d/music-stream enable && say "procd service enabled (start: /etc/init.d/music-stream start)";;
  termux)  mkdir -p "$HOME/.termux/boot" && render "$TPL" "$VPY" > "$HOME/.termux/boot/music-stream.sh" && chmod +x "$HOME/.termux/boot/music-stream.sh" && say "Termux:Boot script installed (needs the Termux:Boot app, opened once)";;
  *) if command -v systemctl >/dev/null 2>&1; then mkdir -p "$HOME/.config/systemd/user" && render "$TPL" "$VPY" > "$HOME/.config/systemd/user/music-stream.service" && systemctl --user daemon-reload && systemctl --user enable music-stream && say "systemd user unit enabled (start: systemctl --user start music-stream; for boot without login: loginctl enable-linger ${USER:-$(id -un)})"; else say "no systemd: see deploy/ for templates"; fi;; esac
else say "autostart not changed (pass --autostart to install $TPL, or --print-autostart to just view it)"; fi
say "done. Start: ./start.sh   Open: http://127.0.0.1:$PORT/?k=<MUSIC_KEY from music.env, created on first start>"

# ---- ms-public command (make it reachable from the internet; see docs/MAKE_PUBLIC.md) ----
BIN="$HOME/.local/bin"; [ "$OS" = termux ] && BIN="$PREFIX/bin"
mkdir -p "$BIN" 2>/dev/null && printf '#!/bin/sh\nexec sh "%s/scripts/ms-public.sh" "$@"\n' "$DIR" > "$BIN/ms-public" && chmod +x "$BIN/ms-public" \
  && say "installed the 'ms-public' command ($BIN/ms-public)" || say "could not install ms-public into $BIN; use: sh $DIR/ms-public"
case ":$PATH:" in *":$BIN:"*) ;; *) say "note: $BIN is not on your PATH yet; until you log in again use: sh $DIR/ms-public";; esac
PORT="$(sed -n 's/^MUSIC_PORT=//p' music.env | head -1)"
if [ "$START" = 1 ]; then
  sh ./start.sh
  i=0; while [ $i -lt 30 ]; do sleep 1; i=$((i+1)); if "$VPY" -c "import urllib.request,sys;urllib.request.urlopen('http://127.0.0.1:$PORT/health',timeout=2)" 2>/dev/null; then break; fi; done
  if [ -f users.json ]; then say "running: http://127.0.0.1:$PORT/  (stop: ./stop.sh)"
  else say "running. First run: open http://127.0.0.1:$PORT/setup in a browser ON THIS DEVICE to create the admin account (stop: ./stop.sh)"
       say "headless? create it here instead: $VPY ms_users.py create-admin \"$DIR\" <name> <file-with-password>"; fi
fi
if [ -f users.json ] && grep -q '"admin"' users.json 2>/dev/null; then say "to use it from outside your home: run  ms-public"
else say "after you create the admin account, run  ms-public  to use it from outside your home (instant link or your own address)"; fi
