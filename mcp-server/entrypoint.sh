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

# If MCP_PORT is set, start the custom MCP bridge as an HTTP sidecar.
# This makes all opencode tools available over SSE (Server-Sent Events).
if [ -n "$MCP_PORT" ]; then
    echo "[$AGENT_NAME] Starting custom MCP HTTP stream server on port $MCP_PORT..."
    
    # Default OPENCODE_BASE_URL to the local instance if not already set.
    export OPENCODE_BASE_URL="${OPENCODE_BASE_URL:-http://localhost:4096}"
    
    # Run the Python MCP server using the root-level virtual environment.
    /.venv/bin/python3 /mcp-server/main.py &
    MCP_PID=$!
fi

# Ensure child processes are terminated gracefully when the script exits.
trap "echo '[$AGENT_NAME] Shutting down...'; kill $OPENCODE_PID $MCP_PID 2>/dev/null" EXIT TERM INT

# Wait for the background processes to finish (blocking the container).
if [ -n "$MCP_PID" ]; then
    wait $OPENCODE_PID $MCP_PID
else
    wait $OPENCODE_PID
fi
