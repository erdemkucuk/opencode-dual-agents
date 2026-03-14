---
name: delegate-to-agent2
description: Delegate tasks to Agent 2 for specialized processing or data retrieval. Use when the task requires Agent 2's specific capabilities.
allowed-tools:
  - bash
---

# Delegate to Agent 2

Send a task to Agent 2 using these curl commands. Replace `<prompt>` with the actual task text.

```bash
AGENT2_URL="${AGENT2_URL:-http://agent2:4096}"

# Step 1: Create a session
SESSION_ID=$(curl -s -X POST "$AGENT2_URL/session" | jq -r '.id')

# Step 2: Send the prompt and capture the reply
RESPONSE=$(curl -s -X POST "$AGENT2_URL/session/$SESSION_ID/message" \
  -H "Content-Type: application/json" \
  -d "$(jq -n --arg text "<prompt>" '{"parts":[{"type":"text","text":$text}]}')")

# Step 3: Print the reply
echo "$RESPONSE" | jq -r '.parts[] | select(.type=="text") | .text'
```

Print the output as your response.
