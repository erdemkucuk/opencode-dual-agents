#!/usr/bin/env bash
set -e

AGENT_NAME="${AGENT_NAME:-agent}"

echo "[$AGENT_NAME] Starting opencode serve on port 4096..."
opencode serve --hostname 0.0.0.0 --port 4096 &
OPENCODE_PID=$!

echo "[$AGENT_NAME] Waiting for opencode to become healthy (max 20s)..."
WAIT=0
until curl -sf http://localhost:4096/global/health > /dev/null 2>&1; do
  sleep 1
  WAIT=$((WAIT+1))
  if [ $WAIT -ge 20 ]; then echo "[$AGENT_NAME] opencode did not start in 20s, aborting."; exit 1; fi
done
echo "[$AGENT_NAME] opencode is healthy."

if [ -n "$MCP_PORT" ]; then
    echo "[$AGENT_NAME] Starting custom MCP HTTP stream server on port $MCP_PORT..."
    # Ensure OPENCODE_BASE_URL is set to local for the sidecar if not provided
    export OPENCODE_BASE_URL="${OPENCODE_BASE_URL:-http://localhost:4096}"
    /mcp-server/.venv/bin/python3 /mcp-server/main.py &
    MCP_PID=$!
fi

trap "echo '[$AGENT_NAME] Shutting down...'; kill $OPENCODE_PID $MCP_PID 2>/dev/null" EXIT TERM INT

if [ -n "$MCP_PID" ]; then
    wait $OPENCODE_PID $MCP_PID
else
    wait $OPENCODE_PID
fi
