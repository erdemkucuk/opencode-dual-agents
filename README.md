# opencode-dual-agents

A demo of two containerized [opencode](https://opencode.ai) agents communicating over a Docker bridge network. Agent 1 (Luigi) orchestrates tasks by delegating to Agent 2 (Mario) via HTTP.

## Architecture

```
Host
 └─ docker compose
     ├─ agent1 (Luigi)  :4097 ──── opencode serve
     │                  :4100 ──── custom MCP server (SSE, sidecar)
     └─ agent2 (Mario)  :4098 ──── opencode serve
                        :4099 ──── custom MCP server (SSE, sidecar)
```

Both agents run `opencode serve` inside Docker and use the free `opencode/minimax-m2.5-free` model for testing.

- **Agent 1 / Luigi** — orchestrator. Exposes port 4097 on the host. Runs the MCP server as an SSE sidecar on port 8000 (host: 4100) to delegate tasks to Agent 2.
- **Agent 2 / Mario** — worker. Exposes port 4098 on the host. Also runs the MCP server as an SSE sidecar on port 8000 (host: 4099).

### Inter-agent communication

Both agents run the MCP server as an SSE sidecar on port 8000 (container), exposing the same 5 tools at `:4100/sse` (agent1) and `:4099/sse` (agent2) on the host. The server exposes **5 workflow tools**:

| Tool | Description |
|---|---|
| `opencode_health` | Lightweight ping — calls `GET /global/health` and returns the raw JSON status. Use it to verify Agent 2 is reachable before delegating work. |
| `opencode_ask` | **One-shot synchronous call.** Creates a new session, posts the prompt to `POST /session/{id}/message`, and returns the full response immediately. Best for short questions where you want a direct answer without waiting for a background task. |
| `opencode_run` | **Async task with full message history.** Posts the prompt to `POST /session/{id}/prompt_async`, then polls `GET /session/status` every 2 seconds until the session finishes (or a configurable `timeout_ms` elapses). Returns the complete list of all messages produced during the session. |
| `opencode_run_final` | Same async/poll flow as `opencode_run`, but returns only the **last message** instead of the full history. Useful when you only care about the final answer and want to avoid processing intermediate tool-call messages. |
| `opencode_status` | **Diagnostic snapshot.** Bundles three API calls — `GET /global/health`, `GET /session` (count), and `GET /provider` — into a single JSON response with keys `health`, `session_count`, and `providers`. |

### About the custom MCP server

`mcp-server/` is a Python server built on `mcp` (FastMCP). It replaces the community `opencode-mcp` package with a self-contained implementation that:

- Exposes **5 hand-written workflow tools** (see table above): `opencode_ask`, `opencode_run`, `opencode_run_final`, `opencode_status`, `opencode_health`.
- Always runs in **SSE/HTTP mode** on port 8000.
- Uses `httpx` to communicate with the opencode API.

## Prerequisites

- Docker + Docker Compose

## Setup

1. Build and start both agents:

   ```bash
   docker compose up --build
   ```

## Usage

Send a prompt to Agent 1 by hitting the API directly:

```bash
SESSION=$(curl -s -X POST http://localhost:4097/session | jq -r '.id')
curl -s -X POST "http://localhost:4097/session/$SESSION/message" \
  -H "Content-Type: application/json" \
  -d '{"parts":[{"type":"text","text":"What is your name?"}]}' \
  | jq -r '.parts[] | select(.type=="text") | .text'
```

## Project structure

```
.
├── Dockerfile                          # Shared image (node:20-slim + opencode + MCP server build)
├── docker-compose.yml                  # Agent services and bridge network
├── agent1-config/
│   ├── opencode.json                   # Model config + agent2 MCP (type: remote, SSE URL)
│   └── AGENTS.md                       # Persona: Luigi
├── agent2-config/
│   ├── opencode.json                   # Model config
│   └── AGENTS.md                       # Persona: Mario
├── mcp-server/
│   ├── bridge.py                       # Custom Python MCP server (SSE/HTTP mode)
│   ├── requirements.txt                # Python deps
│   └── entrypoint.sh                   # Generic entrypoint (opencode + optional MCP sidecar)
```

## Testing

### Automated (pytest)

Integration tests in `tests/` cover health checks and end-to-end delegation. The test fixture handles the full `down → build → up → test → down` cycle automatically.

```bash
# One-time venv setup
make .venv

# Full cycle: rebuild images, bring up, run all tests, bring down
make test

# Skip rebuild (faster when only config/prompts changed)
make test-fast
```

### Manual

#### 1. Verify both agents are reachable

```bash
curl -s http://localhost:4097/session -X POST | jq .   # Agent 1
curl -s http://localhost:4098/session -X POST | jq .   # Agent 2
```

Each should return a JSON object with an `id` field.

#### 2. Test Agent 1 in isolation

```bash
SESSION=$(curl -s -X POST http://localhost:4097/session | jq -r '.id')
curl -s -X POST "http://localhost:4097/session/$SESSION/message" \
  -H "Content-Type: application/json" \
  -d '{"parts":[{"type":"text","text":"What is your name?"}]}' \
  | jq -r '.parts[] | select(.type=="text") | .text'
# Expected: a reply from Luigi
```

#### 3. Test Agent 2 in isolation

```bash
SESSION=$(curl -s -X POST http://localhost:4098/session | jq -r '.id')
curl -s -X POST "http://localhost:4098/session/$SESSION/message" \
  -H "Content-Type: application/json" \
  -d '{"parts":[{"type":"text","text":"What is your name?"}]}' \
  | jq -r '.parts[] | select(.type=="text") | .text'
# Expected: a reply from Mario
```

#### 4. Test end-to-end delegation (Agent 1 → Agent 2)

```bash
SESSION=$(curl -s -X POST http://localhost:4097/session | jq -r '.id')
curl -s -X POST "http://localhost:4097/session/$SESSION/message" \
  -H "Content-Type: application/json" \
  -d '{"parts":[{"type":"text","text":"Ask Agent 2 what its name is, then tell me the answer."}]}' \
  | jq -r '.parts[] | select(.type=="text") | .text'
# Expected: Agent 1 uses MCP tool to query Agent 2, who identifies itself as Mario
```

### Troubleshooting

| Symptom | Likely cause |
|---|---|
| `curl` hangs or returns empty | Agents not running — check `docker compose ps` |
| `null` session id | Agent started but not ready yet — wait a few seconds and retry |
| `"status": "failed"` in `/mcp` | MCP server crashed — check `docker compose logs agent1` for python errors |
| Delegation returns wrong agent name | MCP tools not connected — verify `curl http://localhost:4097/mcp` shows `"status": "connected"` |
| Agent 2 MCP HTTP sidecar not responding | Check `docker compose logs agent2` for `[mcp]` lines; verify port 4099 is mapped |

## Common commands

```bash
docker compose up --build       # Build and start
docker compose up               # Start without rebuilding
docker compose build agent1     # Rebuild a single agent
docker compose logs -f agent1   # Tail logs for one agent
docker compose down             # Stop everything
```
