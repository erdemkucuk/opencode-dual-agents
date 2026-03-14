#!/usr/bin/env bash
set -e

echo "[agent2] Starting opencode serve on port 4096..."
opencode serve --hostname 0.0.0.0 --port 4096 &
OPENCODE_PID=$!

echo "[agent2] Waiting for opencode to become healthy (max 20s)..."
WAIT=0
until curl -sf http://localhost:4096/global/health > /dev/null 2>&1; do
  sleep 1
  WAIT=$((WAIT+1))
  if [ $WAIT -ge 20 ]; then echo "[agent2] opencode did not start in 20s, aborting."; exit 1; fi
done
echo "[agent2] opencode is healthy."

echo "[agent2] Starting custom MCP HTTP stream server on port 4095..."
MCP_PORT=4095 node /mcp-server/dist/index.js &
MCP_PID=$!

trap "echo '[agent2] Shutting down...'; kill $OPENCODE_PID $MCP_PID 2>/dev/null" EXIT TERM INT

wait $OPENCODE_PID $MCP_PID
