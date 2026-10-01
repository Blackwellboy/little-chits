#!/usr/bin/env bash
# Drive a local coding model through the build plan, one verified task at a time.
#
#   AGENT=aider  MODEL=openai/qwen3-coder  API_BASE=http://127.0.0.1:18090/v1  scripts/agent_loop.sh
#   AGENT=opencode scripts/agent_loop.sh
#   AGENT=custom AGENT_CMD='mytool --prompt-file "$PROMPT_FILE"' scripts/agent_loop.sh
#
# For each ready task it hands the agent the spec + rules, then runs every gate
# (scripts/plan.py verify). Only a full pass ticks the task off and commits.
# A task that still fails after MAX_ATTEMPTS stops the loop and leaves a report in plan/reports/.
set -euo pipefail
cd "$(dirname "$0")/.."

AGENT="${AGENT:-aider}"
MAX_ATTEMPTS="${MAX_ATTEMPTS:-4}"
ONLY="${ONLY:-}"            # e.g. ONLY=T05 to run a single task
PY="${PY:-.venv/bin/python}"
[ -x "$PY" ] || PY=python3

run_agent() {  # $1 = task id, $2 = prompt file, $3 = attempt
  local id="$1" prompt="$2"
  case "$AGENT" in
    aider)
      # aider re-runs the test command and feeds failures back to the model until it passes
      aider --yes-always --no-auto-commits --no-show-model-warnings \
        ${MODEL:+--model "$MODEL"} ${API_BASE:+--openai-api-base "$API_BASE"} ${OPENAI_API_KEY:+--openai-api-key "$OPENAI_API_KEY"} \
        --read AGENTS.md --read "$(grep -o "plan/tasks/$id-[^\"]*" plan/tasks.json | head -1)" \
        $(for f in $("$PY" -c "import json;print(' '.join(a for t in json.load(open('plan/tasks.json'))['tasks'] if t['id']=='$id' for a in t['acceptance']))"); do echo --read "$f"; done) \
        --test-cmd "$PY scripts/plan.py verify $id" --auto-test \
        --message-file "$prompt" ;;
    opencode)
      opencode run "$(cat "$prompt")" ;;
    custom)
      PROMPT_FILE="$prompt" TASK_ID="$id" bash -c "${AGENT_CMD:?set AGENT_CMD}" ;;
    *)
      echo "unknown AGENT=$AGENT (aider|opencode|custom)"; exit 2 ;;
  esac
}

while true; do
  if [ -n "$ONLY" ]; then id="$ONLY"; else id="$("$PY" scripts/plan.py next --id || true)"; fi
  if [ -z "$id" ]; then echo "🎉 plan complete"; exit 0; fi
  echo "═══════════════ $id ═══════════════"
  prompt="$(mktemp)"
  ok=0
  for attempt in $(seq 1 "$MAX_ATTEMPTS"); do
    "$PY" scripts/plan.py prompt "$id" > "$prompt"
    if [ "$attempt" -gt 1 ] && [ -f "plan/reports/$id.txt" ]; then
      { echo; echo "Your previous attempt did not pass. Gate report:"; tail -c 6000 "plan/reports/$id.txt"; } >> "$prompt"
    fi
    echo "── attempt $attempt/$MAX_ATTEMPTS ($AGENT)"
    run_agent "$id" "$prompt" "$attempt" || true
    git checkout -- plan/acceptance plan/tasks plan/tasks.json 2>/dev/null || true  # the contract can't be edited
    if "$PY" scripts/plan.py done "$id" --commit; then ok=1; break; fi
  done
  rm -f "$prompt"
  if [ "$ok" != 1 ]; then
    echo "✋ $id still failing after $MAX_ATTEMPTS attempts — see plan/reports/$id.txt"; exit 1
  fi
  [ -n "$ONLY" ] && exit 0
done
