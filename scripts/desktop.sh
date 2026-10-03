#!/usr/bin/env bash
# What the Windows "Little Chits" and "Stop Little Chits" desktop shortcuts run inside WSL.
#
#   scripts/desktop.sh start [PORT]            start the model servers (if needed), then the game
#   scripts/desktop.sh stop [PORT] [--models]  stop the game (and the model servers too with --models)
#   scripts/desktop.sh status [PORT]           what's running
#   scripts/desktop.sh keepalive [PORT]        stays alive while the game runs, so WSL doesn't shut it down
#
# Progress goes to stdout as plain-English lines the shortcut's window shows:
#   @step KEY text · @ok KEY text · @warn KEY text · @fail KEY text · @open URL · @done
# Lines that share a KEY replace each other. Anything else is detail for the log.
#
# The model servers come from ~/start-gpus.sh (or $LC_GPU_SCRIPT). Its "# model PORT NAME LOGFILE" lines say
# which ports to wait for; see docs/GPU_SETUP.md, "Desktop shortcut".
set -uo pipefail
cd "$(dirname "$0")/.." || exit 1
ROOT="$(pwd)"
CMD="${1:-status}"; shift || true
PORT=8010; WITH_MODELS=0
for a in "$@"; do
  case "$a" in
    --models) WITH_MODELS=1 ;;
    *[0-9]*) PORT="$a" ;;
  esac
done
URL="http://localhost:$PORT"
GPU_SCRIPT="${LC_GPU_SCRIPT:-$HOME/start-gpus.sh}"
MODEL_WAIT="${LC_MODEL_WAIT:-900}"   # seconds to wait for a model server to load
GAME_WAIT="${LC_GAME_WAIT:-180}"
mkdir -p data

say() { printf '@%s %s %s\n' "$1" "$2" "$3"; }
game_up() { curl -fs -m 3 "$URL/api/health" >/dev/null 2>&1; }
model_up() { curl -fs -m 5 "http://127.0.0.1:$1/v1/models" >/dev/null 2>&1; }
mins() { local s=$1; [ "$s" -lt 60 ] && echo "${s}s" || echo "$((s / 60)) min"; }

# "PORT NAME LOG" for every "# model" line in the GPU script
models() {
  [ -f "$GPU_SCRIPT" ] || return 0
  sed -n 's/^#[[:space:]]*model[[:space:]]\+\([0-9]\+\)[[:space:]]\+\([^[:space:]]\+\)[[:space:]]*\(.*\)$/\1 \2 \3/p' "$GPU_SCRIPT"
}

start_models() {
  if [ ! -f "$GPU_SCRIPT" ]; then
    say warn models "No $GPU_SCRIPT yet, so the models can't be started for you (see docs/GPU_SETUP.md)."
    return 0
  fi
  local list; list="$(models)"
  if [ -z "$list" ]; then
    say warn models "$GPU_SCRIPT has no '# model PORT NAME LOG' lines, so there's nothing to wait for."
    return 0
  fi
  local missing=() port name log
  while read -r port name log; do
    if model_up "$port"; then say ok "m$port" "The $name model is ready."
    else missing+=("$port"); say step "m$port" "Starting the $name model…"; fi
  done <<<"$list"
  [ ${#missing[@]} -eq 0 ] && return 0

  echo "running $GPU_SCRIPT start"
  bash "$GPU_SCRIPT" start >>data/start-gpus.log 2>&1 || echo "$GPU_SCRIPT exited with $? (see data/start-gpus.log)"
  local t0=$SECONDS pending=("${missing[@]}") next shown=0
  while [ ${#pending[@]} -gt 0 ] && [ $((SECONDS - t0)) -lt "$MODEL_WAIT" ]; do
    next=()
    for port in "${pending[@]}"; do
      name="$(awk -v p="$port" '$1 == p {print $2}' <<<"$list")"
      if model_up "$port"; then say ok "m$port" "The $name model is ready (took $(mins $((SECONDS - t0))))."
      else next+=("$port"); fi
    done
    pending=("${next[@]+"${next[@]}"}")
    [ ${#pending[@]} -eq 0 ] && break
    if [ $((SECONDS - t0)) -ge $((shown + 30)) ]; then
      shown=$((SECONDS - t0))
      for port in "${pending[@]}"; do
        name="$(awk -v p="$port" '$1 == p {print $2}' <<<"$list")"
        say step "m$port" "Starting the $name model… $(mins "$shown") so far (big models take a few minutes)"
      done
    fi
    sleep 3
  done
  for port in "${pending[@]+"${pending[@]}"}"; do
    read -r _ name log <<<"$(awk -v p="$port" '$1 == p' <<<"$list")"
    say warn "m$port" "The $name model didn't start. See ${log:-data/start-gpus.log}. Its world will think on instinct until it's up."
  done
}

# A real capability check: one decision through the doctor, before the game relies on the model.
check_models() {
  local port name log out
  while read -r port name log; do
    [ -n "$port" ] && model_up "$port" || continue
    say step "d$port" "Checking the $name model can drive chits…"
    out="$(cd server && timeout 150 ../.venv/bin/python -m chits.tools.doctor --url "http://127.0.0.1:$port/v1" --samples 1 2>&1)"
    echo "$out"
    if grep -q " OK " <<<"$out"; then
      say ok "d$port" "The $name model gives good answers ($(grep -o '[0-9]* ms' <<<"$out" | head -1) per decision)."
    else
      say warn "d$port" "The $name model answered, but not in a way chits can use: $(tail -1 <<<"$out" | cut -c1-160)"
    fi
  done <<<"$(models)"
}

install_if_needed() {
  if [ ! -x .venv/bin/python ] || [ ! -d web/node_modules ]; then
    say step install "First run: installing Little Chits (a few minutes)…"
    make install >>data/launcher.log 2>&1 || { say fail install "Installing failed. See data/launcher.log in $ROOT"; return 1; }
    say ok install "Installed."
  fi
  if [ ! -f web/dist/index.html ]; then
    say step build "Building the game's screen…"
    make web >>data/launcher.log 2>&1 || { say fail build "Building failed. See data/launcher.log in $ROOT"; return 1; }
    say ok build "Built."
  fi
}

start_game() {
  install_if_needed || return 1
  say step game "Starting the game…"
  echo "--- $(date '+%F %T') starting on port $PORT" >>data/launcher.log
  setsid nohup make run PORT="$PORT" >>data/launcher.log 2>&1 </dev/null &
  local t0=$SECONDS
  until game_up; do
    if [ $((SECONDS - t0)) -ge "$GAME_WAIT" ]; then
      say fail game "The game didn't start. See data/launcher.log in $ROOT"
      tail -25 data/launcher.log
      return 1
    fi
    sleep 1
  done
  say ok game "The game is running (took $(mins $((SECONDS - t0))))."
}

# Which model each world is thinking with, from the running game itself.
report_brains() {
  curl -fs -m 5 "$URL/api/brains" 2>/dev/null | MODELS="$(models)" .venv/bin/python scripts/report_brains.py || true
}

# WSL shuts itself down about a minute after the last Windows program using it exits (vmIdleTimeout), taking
# the game and the model servers with it. A hidden Windows-side "wsl.exe ... keepalive" holds it open while the
# game runs, however the game was started (the desktop shortcut starts one too; this makes sure there is one).
ensure_keepalive() {
  command -v powershell.exe >/dev/null 2>&1 || return 0
  local shim="$HOME/.local/share/little-chits/desktop.sh"
  [ -f "$shim" ] || shim="$ROOT/scripts/desktop.sh"
  local n
  n="$(powershell.exe -NoProfile -NonInteractive -Command "@(Get-CimInstance Win32_Process | Where-Object { \$_.Name -eq 'wsl.exe' -and \$_.CommandLine -match 'desktop.sh keepalive' }).Count" </dev/null 2>/dev/null | tr -d '\r')"
  [ "${n:-0}" -gt 0 ] 2>/dev/null && return 0
  powershell.exe -NoProfile -NonInteractive -Command "Start-Process -WindowStyle Hidden -FilePath wsl.exe -ArgumentList '-d ${WSL_DISTRO_NAME:-Ubuntu} -e bash $shim keepalive $PORT'" </dev/null >/dev/null 2>&1
  echo "keepalive started"
}

case "$CMD" in
  start)
    start_models   # also brings back a model server that died while the game kept running
    if game_up; then
      say ok game "Little Chits is already running."
    else
      check_models
      start_game || exit 1
      sleep 2
    fi
    ensure_keepalive
    report_brains
    say open "$URL" "$URL"
    echo "@done"
    ;;
  stop)
    if game_up; then
      say step game "Saving the world…"
      curl -fs -m 20 -X POST "$URL/api/save" >/dev/null 2>&1 || true
      say step game "Stopping the game…"
      fuser -k -TERM "$PORT/tcp" >/dev/null 2>&1 || true   # let it finish writing; fuser's default is SIGKILL
      for _ in $(seq 1 20); do game_up || break; sleep 0.5; done
      game_up && { fuser -k "$PORT/tcp" >/dev/null 2>&1 || true; sleep 1; }
      if game_up; then say fail game "The game is still running on port $PORT."; else say ok game "The game has stopped."; fi
    else
      say ok game "The game wasn't running."
    fi
    if [ "$WITH_MODELS" = 1 ]; then
      if [ -f "$GPU_SCRIPT" ]; then
        say step models "Stopping the model servers…"
        bash "$GPU_SCRIPT" stop >>data/start-gpus.log 2>&1 || true
        while read -r port name log; do
          [ -n "$port" ] || continue
          for _ in $(seq 1 30); do model_up "$port" || break; sleep 1; done
          if model_up "$port"; then say warn "m$port" "The $name model is still running."
          else say ok "m$port" "The $name model has stopped."; fi
        done <<<"$(models)"
        say ok models "Model servers done."
      else
        say warn models "No $GPU_SCRIPT, so I don't know how to stop the model servers."
      fi
    fi
    echo "@done"
    ;;
  status)
    if game_up; then say ok game "The game is running at $URL"; else say warn game "The game isn't running."; fi
    while read -r port name log; do
      [ -n "$port" ] || continue
      if model_up "$port"; then say ok "m$port" "The $name model is up on port $port."
      else say warn "m$port" "The $name model isn't answering on port $port."; fi
    done <<<"$(models)"
    game_up && report_brains
    echo "@done"
    ;;
  keepalive)
    # Held open by the Windows launcher: while this runs, WSL keeps the game alive after the window closes.
    for _ in $(seq 1 60); do game_up && break; sleep 2; done
    while game_up; do sleep 30; done
    ;;
  *)
    echo "usage: scripts/desktop.sh start|stop|status|keepalive [PORT] [--models]"; exit 2 ;;
esac
