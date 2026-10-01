#!/usr/bin/env bash
# Start a llama.cpp model server on one GPU with settings that suit Little Chits.
#
#   scripts/gpu-server.sh --gpu 0 --port 18191 --model ~/gguf/Qwen3-14B-Q4_K_M.gguf
#
# Options:
#   --gpu N         which GPU (0, 1, ... as listed by `nvidia-smi -L`)
#   --port P        port to serve on (the game finds 18000-19999 automatically)
#   --model FILE    the .gguf file
#   --slots N       how many chits can think at once (default 8)
#   --ctx N         context per slot (default 4096; total = slots x ctx)
#   --foreground    stay attached (default: run in the background, log to data/gpu-<port>.log)
set -euo pipefail
cd "$(dirname "$0")/.."
GPU=0; PORT=18191; MODEL=""; SLOTS=8; CTX=4096; FG=0
while [ $# -gt 0 ]; do
  case "$1" in
    --gpu) GPU="$2"; shift 2 ;;
    --port) PORT="$2"; shift 2 ;;
    --model) MODEL="$2"; shift 2 ;;
    --slots) SLOTS="$2"; shift 2 ;;
    --ctx) CTX="$2"; shift 2 ;;
    --foreground) FG=1; shift ;;
    *) echo "unknown option $1 (see the top of this file)"; exit 1 ;;
  esac
done
[ -n "$MODEL" ] && [ -f "$MODEL" ] || { echo "Give a .gguf file with --model (found: '${MODEL}')"; exit 1; }

BIN="${LLAMA_SERVER:-}"
for c in "$BIN" "$(command -v llama-server 2>/dev/null || true)" ~/llama.cpp/build/bin/llama-server \
         ~/projects/llama.cpp/build/bin/llama-server /usr/local/bin/llama-server; do
  if [ -n "$c" ] && [ -x "$c" ]; then BIN="$c"; break; fi
done
[ -x "$BIN" ] || { echo "Couldn't find llama-server. Set LLAMA_SERVER=/path/to/llama-server and try again."; exit 1; }

if curl -fs "http://127.0.0.1:$PORT/v1/models" >/dev/null 2>&1; then
  echo "Something is already serving on port $PORT. Stop it first (see docs/GPU_SETUP.md, step 2)."; exit 1
fi

TOTAL=$((SLOTS * CTX))
ARGS=(-m "$MODEL" --host 127.0.0.1 --port "$PORT" -ngl 99 -np "$SLOTS" -c "$TOTAL" --jinja -fa on)
echo "GPU $GPU · port $PORT · $SLOTS slots x $CTX context · $(basename "$MODEL")"
mkdir -p data
if [ "$FG" = 1 ]; then
  CUDA_VISIBLE_DEVICES="$GPU" exec "$BIN" "${ARGS[@]}"
fi
CUDA_VISIBLE_DEVICES="$GPU" setsid nohup "$BIN" "${ARGS[@]}" >"data/gpu-$PORT.log" 2>&1 < /dev/null &
for _ in $(seq 1 180); do
  curl -fs "http://127.0.0.1:$PORT/v1/models" >/dev/null 2>&1 && break
  sleep 1
done
if curl -fs "http://127.0.0.1:$PORT/v1/models" >/dev/null 2>&1; then
  echo "Ready: http://127.0.0.1:$PORT/v1   (log: data/gpu-$PORT.log, stop: fuser -k $PORT/tcp)"
else
  echo "It didn't come up. Last lines of data/gpu-$PORT.log:"; tail -20 "data/gpu-$PORT.log"; exit 1
fi
