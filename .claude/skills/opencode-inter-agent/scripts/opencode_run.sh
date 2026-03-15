#!/usr/bin/env bash
# Run a task on an opencode server asynchronously, poll until complete, and print all messages.
#
# Fires the prompt via the async endpoint, polls /session/status every 2 seconds
# until the session finishes or the timeout elapses, then returns all messages.
#
# Usage:
#   ./opencode_run.sh <base_url> <prompt> [directory] [timeout_ms]
#
# Example:
#   ./opencode_run.sh http://localhost:4098 "List files in /tmp"

set -euo pipefail

if [[ $# -lt 2 ]]; then
  echo "Usage: $0 <base_url> <prompt> [directory] [timeout_ms]" >&2
  exit 1
fi

BASE="${1%/}"
PROMPT="$2"
DIRECTORY="${3:-}"
TIMEOUT_MS="${4:-20000}"

PARAMS=""
[[ -n "$DIRECTORY" ]] && PARAMS="?directory=${DIRECTORY}"

SESSION_ID=$(curl -sf -X POST "${BASE}/session${PARAMS}" | jq -r '.id')
echo "Session: $SESSION_ID" >&2

curl -sf -X POST "${BASE}/session/${SESSION_ID}/prompt_async${PARAMS}" \
  -H "Content-Type: application/json" \
  --data-binary "{\"parts\":[{\"type\":\"text\",\"text\":$(jq -n --arg p "$PROMPT" '$p')}]}" \
  > /dev/null

TIMEOUT_S=$(( TIMEOUT_MS / 1000 ))
DEADLINE=$(( $(date +%s) + TIMEOUT_S ))

while true; do
  sleep 2
  STATUS=$(curl -sf "${BASE}/session/status")
  RUNNING=$(echo "$STATUS" | jq -r --arg id "$SESSION_ID" '.[$id].running // false')
  if [[ "$RUNNING" != "true" ]]; then
    break
  fi
  if (( $(date +%s) >= DEADLINE )); then
    echo "Timeout waiting for session $SESSION_ID" >&2
    break
  fi
done

curl -sf "${BASE}/session/${SESSION_ID}/message${PARAMS}" | jq .
