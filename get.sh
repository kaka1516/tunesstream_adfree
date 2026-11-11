#!/bin/sh
# Music Stream one-line installer for Linux / Raspberry Pi / Android (Termux):
#   curl -fsSL https://raw.githubusercontent.com/kaka1516/tunesstream_adfree/main/get.sh | sh
# 
# Downloads the code to ~/music-stream (or $MS_DIR), installs everything and starts the server on http://127.0.0.1:8125
set -eu
REPO="${MS_REPO:-kaka1516/tunesstream_adfree}"; BRANCH="${MS_BRANCH:-main}"; DEST="${MS_DIR:-$HOME/music-stream}"
if [ -n "${PREFIX:-}" ] && echo "$PREFIX" | grep -q com.termux; then pkg install -y curl tar >/dev/null 2>&1 || true; fi
if [ -f "$DEST/music_server.py" ] && [ -d "$DEST/.git" ] && command -v git >/dev/null 2>&1; then
  echo "== updating $DEST"; git -C "$DEST" pull --ff-only
else
  echo "== downloading $REPO ($BRANCH) to $DEST"
  mkdir -p "$DEST"; tmp="${TMPDIR:-/tmp}/ms-get.$$.tgz"
  curl -fsSL "https://codeload.github.com/$REPO/tar.gz/refs/heads/$BRANCH" -o "$tmp"
  tar xzf "$tmp" -C "$DEST" --strip-components=1; rm -f "$tmp"   # your music.env and accounts are not in the archive, so they are kept
fi
exec sh "$DEST/install.sh" --yes --start
