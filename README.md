# opencode-dual-agents

A demo of two containerized [opencode](https://opencode.ai) agents communicating over a Docker bridge network. Agent 1 (Luigi) orchestrates tasks by delegating to Agent 2 (Mario) via HTTP.

## Architecture

```
Host
 └─ docker compose
     ├─ agent1 (Luigi)  :4097 ──── custom MCP server (stdio) ──► agent2:4096
     └─ agent2 (Mario)  :4098
                        :4099 ──── custom MCP server (SSE, sidecar)
```

Both agents run `opencode serve` inside Docker and use the free `opencode/minimax-m2.5-free` model for testing.

- **Agent 1 / Luigi** — orchestrator. Exposes port 4097 on the host. Spawns the custom MCP server as a local stdio process to delegate tasks to Agent 2.
- **Agent 2 / Mario** — worker. Exposes port 4098 on the host. Also runs the MCP server as an HTTP sidecar on port 4095 (host: 4099).

### Inter-agent communication

Agent 1's opencode spawns the Python MCP server as a child process (stdio MCP transport). On startup, this server:

1. Fetches `GET http://agent2:4096/doc` — opencode's live OpenAPI spec.
2. Auto-generates **~104 tools**, one per API endpoint (sessions, messages, files, providers, config, etc.).
3. Adds **5 workflow composites**: `opencode_ask`, `opencode_run`, `opencode_status`, `opencode_health`, `opencode_context`.
4. Serves all 109 tools to Agent 1 over stdio MCP.

Agent 2 runs the same binary with `MCP_PORT=4095`, exposing the same tools over SSE transport at `:4099/sse` on the host.

### About the custom MCP server

`mcp-server/` is a Python server built on `mcp` (FastMCP). It replaces the community `opencode-mcp` package with a self-contained implementation that:

- Derives its tool list **dynamically** from the live opencode OpenAPI spec — no hardcoded routes.
- Runs in **dual mode**: stdio (for agent1's local MCP command) or SSE (for the agent2 sidecar), controlled by the `MCP_PORT` environment variable.
- Uses `httpx` to communicate with the opencode API.

## Prerequisites

- Docker + Docker Compose

## Setup

1. Build and start both agents:

   ```bash
   docker compose up --build
   ```

## Usage

Send a prompt to Agent 1 using the helper script:

```bash
bash scripts/curl-test.sh
# or with a custom prompt:
bash scripts/curl-test.sh "Ask Agent 2 to summarise the Fibonacci sequence in 2 sentences."
```

You can also hit the API directly:

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
│   ├── opencode.json                   # Model config + agent2 MCP (type: local, python command)
│   └── AGENTS.md                       # Persona: Luigi
├── agent2-config/
│   ├── opencode.json                   # Model config
│   └── AGENTS.md                       # Persona: Mario
├── mcp-server/
│   ├── main.py                         # Custom Python MCP server (dual stdio/SSE mode)
│   ├── requirements.txt                # Python deps
│   └── entrypoint.sh                   # Generic entrypoint (opencode + optional MCP sidecar)
└── scripts/
    └── curl-test.sh                    # Test helper
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

Or use the helper script: `bash scripts/curl-test.sh`

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
