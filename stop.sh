#!/usr/bin/env sh
# Stop the Music Stream server started by ./start.sh (only this folder's server.pid).
# cluster-20261113: also stop worker processes listed in server.workers.
cd "$(dirname "$0")"
if [ -f server.pid ] && kill -0 "$(cat server.pid)" 2>/dev/null; then
  pid=$(cat server.pid)
  if grep -qE 'music_server|ms_standby|ms_cluster' "/proc/$pid/cmdline" 2>/dev/null; then
    if [ -f server.workers ]; then
      for w in $(cat server.workers); do
        kill "$w" 2>/dev/null || true
      done
    fi
    kill "$pid" 2>/dev/null || true
    i=0
    while [ $i -lt 10 ] && kill -0 "$pid" 2>/dev/null; do i=$((i+1)); sleep 0.2; done
    if [ -f server.workers ]; then
      for w in $(cat server.workers); do
        kill -9 "$w" 2>/dev/null || true
      done
    fi
    kill -9 "$pid" 2>/dev/null || true
    rm -f server.pid server.workers
    echo "stopped"
  else
    echo "not running"
    rm -f server.pid server.workers
  fi
else
  echo "not running"
  rm -f server.pid server.workers
fi
