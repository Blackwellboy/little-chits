#!/usr/bin/env bash
# Start Little Chits (if it isn't already running) and open it in the browser.
# Usage: scripts/launch.sh [port] [--foreground]
#   default port 8010 (the old v0.2 service may still hold 8000)
#   --foreground keeps the server attached to this window (used by the Windows shortcut under WSL,
#   where background processes can be stopped when the window closes)
set -euo pipefail
cd "$(dirname "$0")/.."
PORT=8010
FG=0
for a in "$@"; do
  case "$a" in
    --foreground) FG=1 ;;
    *[0-9]*) PORT="$a" ;;
  esac
done
URL="http://localhost:$PORT"
LOG="data/launcher.log"
mkdir -p data
IS_WSL=0
grep -qi microsoft /proc/version 2>/dev/null && IS_WSL=1

up() { curl -fs "$URL/api/health" >/dev/null 2>&1; }
open_url() {
  if [ "$IS_WSL" = 1 ]; then
    (cmd.exe /c start "" "$URL" || explorer.exe "$URL") >/dev/null 2>&1 &
  else
    (xdg-open "$URL" || sensible-browser "$URL" || firefox "$URL") >/dev/null 2>&1 &
  fi
}

if up; then
  echo "Little Chits is already running at $URL"
  open_url
  [ "$FG" = 1 ] && { echo "(this window can be closed)"; sleep 4; }
  exit 0
fi

# first run: install everything
if [ ! -x .venv/bin/python ] || [ ! -d web/node_modules ]; then
  echo "First run: installing (a minute or two)..."
  make install
fi
[ -f web/dist/index.html ] || make web

echo "Starting Little Chits on $URL"
if [ "$FG" = 1 ]; then
  ( for _ in $(seq 1 90); do up && { open_url; break; }; sleep 1; done ) &
  echo "Leave this window open while you play. Close it (or press Ctrl+C) to stop the world."
  exec make run PORT="$PORT"
fi

setsid nohup make run PORT="$PORT" >"$LOG" 2>&1 < /dev/null &
for _ in $(seq 1 90); do
  up && break
  sleep 1
done
if up; then
  open_url
  echo "Running at $URL. Stop it with: make stop PORT=$PORT"
else
  echo "It didn't start. Last lines of $LOG:"
  tail -25 "$LOG"
  exit 1
fi
