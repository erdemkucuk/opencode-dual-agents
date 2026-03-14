#!/usr/bin/env bash
# Ask agent1 to delegate a query to agent2 via its skill.

QUESTION="${1:-Ask Agent 2 what its name is, then tell me the answer.}"

SESSION=$(curl -s -X POST http://localhost:4097/session | jq -r '.id')

echo "Session: $SESSION"
echo "Question: $QUESTION"

curl -s -X POST "http://localhost:4097/session/$SESSION/message" \
  -H "Content-Type: application/json" \
  -d "{\"parts\":[{\"type\":\"text\",\"text\":\"$QUESTION\"}]}" \
  | jq -r '.parts[] | select(.type=="text") | .text'
