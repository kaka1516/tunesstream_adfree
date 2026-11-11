#!/usr/bin/env sh
# Stop the Music Stream server started by ./start.sh (only this folder's server.pid).
cd "$(dirname "$0")"
if [ -f server.pid ] && kill -0 "$(cat server.pid)" 2>/dev/null && grep -q music_server "/proc/$(cat server.pid)/cmdline" 2>/dev/null; then
  kill "$(cat server.pid)" && rm -f server.pid && echo "stopped"
else echo "not running"; rm -f server.pid; fi
