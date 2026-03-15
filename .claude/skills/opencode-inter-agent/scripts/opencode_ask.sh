#!/usr/bin/env bash
# Send a one-shot prompt to an opencode server and print the response.
#
# Creates a new session, sends the prompt synchronously, and prints the result.
#
# Usage:
#   ./opencode_ask.sh <base_url> <prompt> [directory]
#
# Example:
#   ./opencode_ask.sh http://localhost:4098 "What is your name?"

set -euo pipefail

if [[ $# -lt 2 ]]; then
  echo "Usage: $0 <base_url> <prompt> [directory]" >&2
  exit 1
fi

BASE="${1%/}"
PROMPT="$2"
DIRECTORY="${3:-}"

PARAMS=""
[[ -n "$DIRECTORY" ]] && PARAMS="?directory=${DIRECTORY}"

SESSION_ID=$(curl -sf -X POST "${BASE}/session${PARAMS}" | jq -r '.id')
echo "Session: $SESSION_ID" >&2

curl -sf -X POST "${BASE}/session/${SESSION_ID}/message${PARAMS}" \
  -H "Content-Type: application/json" \
  --data-binary "{\"parts\":[{\"type\":\"text\",\"text\":$(jq -n --arg p "$PROMPT" '$p')}]}" \
  | jq .
