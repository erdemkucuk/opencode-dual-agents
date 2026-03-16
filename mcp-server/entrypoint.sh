#!/usr/bin/env bash
set -e

# Default agent name for logging
AGENT_NAME="${AGENT_NAME:-agent}"

# Start 'opencode serve' in the background. 
# It must bind to 0.0.0.0 to be accessible within the Docker network.
echo "[$AGENT_NAME] Starting opencode serve on port 4096..."
opencode serve --hostname 0.0.0.0 --port 4096 &
OPENCODE_PID=$!

# Wait for the opencode API to become responsive before continuing.
# This ensures that any dependent services (like the MCP server) can connect.
echo "[$AGENT_NAME] Waiting for opencode to become healthy (max 20s)..."
WAIT=0
until curl -sf http://localhost:4096/global/health > /dev/null 2>&1; do
  sleep 1
  WAIT=$((WAIT+1))
  if [ $WAIT -ge 20 ]; then echo "[$AGENT_NAME] opencode did not start in 20s, aborting."; exit 1; fi
done
echo "[$AGENT_NAME] opencode is healthy."

# Start the appropriate sidecar on port 8000.
# - agent1 (Luigi): MCP SSE server (bridge.py) that delegates to Mario via A2A.
# - agent2 (Mario): A2A HTTP server (a2a_server.py) that wraps the local opencode.
export OPENCODE_BASE_URL="${OPENCODE_BASE_URL:-http://localhost:4096}"
if [ "${AGENT_NAME}" = "agent2" ]; then
  echo "[$AGENT_NAME] Starting A2A server on port 8000..."
  /.venv/bin/python3 /mcp-server/a2a_server.py &
else
  echo "[$AGENT_NAME] Starting MCP SSE server on port 8000..."
  /.venv/bin/python3 /mcp-server/bridge.py &
fi
MCP_PID=$!

# Ensure child processes are terminated gracefully when the script exits.
trap "echo '[$AGENT_NAME] Shutting down...'; kill $OPENCODE_PID $MCP_PID 2>/dev/null" EXIT TERM INT

wait $OPENCODE_PID $MCP_PID
