#!/usr/bin/env bash
# Starts (or stops) your model servers for Little Chits. The "Little Chits" desktop shortcut runs it.
# `make shortcut` copies this to ~/start-gpus.sh if you don't have one yet. Edit that copy, not this file.
#   ~/start-gpus.sh          start the ones that aren't already running (safe to run twice)
#   ~/start-gpus.sh stop     stop them
#
# 1. Put your model files and GPU numbers in the two gpu-server.sh lines below (docs/GPU_SETUP.md, step 4).
# 2. Keep one "# model PORT NAME LOGFILE" line per server. The shortcut waits for those ports and uses the
#    NAME in its messages ("Starting the 5090 model..."):
# model 18191 5090 ~/projects/little-chits/data/gpu-18191.log
# model 18192 3090 ~/projects/little-chits/data/gpu-18192.log

LC="$(cat ~/.config/little-chits/repo 2>/dev/null || echo ~/projects/little-chits)"
up() { curl -fs -m 3 "http://127.0.0.1:$1/v1/models" >/dev/null 2>&1; }

case "${1:-start}" in
  start)
    up 18191 || "$LC/scripts/gpu-server.sh" --gpu 0 --port 18191 --model ~/gguf/YOUR-5090-MODEL.gguf &
    up 18192 || "$LC/scripts/gpu-server.sh" --gpu 1 --port 18192 --model ~/gguf/YOUR-3090-MODEL.gguf &
    wait ;;
  stop)
    fuser -k 18191/tcp 18192/tcp ;;
  *)
    echo "usage: ~/start-gpus.sh [start|stop]"; exit 2 ;;
esac
