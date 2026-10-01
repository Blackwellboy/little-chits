#!/bin/sh
# Two GPUs, two minds: check both model servers, then start the game with the 5090 on World A and the 3090 on
# World B. If a card is down its world runs on instinct until it comes back (add it again in ⚙ Brains).
# Ports come from configs/dual-gpu.json (18090 and 18080 by default); override with A_URL / B_URL.
A_URL="${A_URL:-http://127.0.0.1:18090/v1}"
B_URL="${B_URL:-http://127.0.0.1:18080/v1}"
cd "$(dirname "$0")/.." || exit 1
up=0
for pair in "A $A_URL" "B $B_URL"; do
  set -- $pair
  if curl -fs "$2/models" >/dev/null 2>&1; then
    echo "World $1: model server is up at $2"
    up=$((up + 1))
  else
    echo "WARNING: World $1: nothing answering at $2 — that world will run on instinct."
  fi
done
[ "$up" -eq 0 ] && echo "WARNING: no model servers are up. Start them first (docs/GPU_SETUP.md)."
exec make dual
