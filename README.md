# opencode-dual-agents

A demo of two containerized [opencode](https://opencode.ai) agents communicating over a Docker bridge network. Agent 1 (Luigi) orchestrates tasks by delegating to Agent 2 (Mario) via HTTP.

## Architecture

```
Host
 └─ docker compose
     ├─ agent1 (Luigi)  :4097 ──── opencode-mcp bridge ──► agent2:4096
     └─ agent2 (Mario)  :4098
```

Both agents run `opencode serve` inside Docker and use Google Gemini (`gemini-3-flash-preview`) via a shared `GEMINI_API_KEY`.

- **Agent 1 / Luigi** — orchestrator. Exposes port 4097 on the host. Uses `opencode-mcp` to connect to Agent 2 as an MCP server.
- **Agent 2 / Mario** — worker. Exposes port 4098 on the host. Receives delegated tasks via its MCP tools exposed by the bridge.

### Inter-agent communication

Agent 1 uses the `agent2` MCP server. The `opencode-mcp` bridge handles the REST API interaction with Agent 2.

### About opencode-mcp

`opencode-mcp` is a community package released under the **MIT License** ([npm](https://www.npmjs.com/package/opencode-mcp), [source](https://github.com/AlaeddineMessadi/opencode-mcp)). It allows any Model Context Protocol (MCP) client to leverage OpenCode's autonomous capabilities.

- **How it works:** It acts as a translator between MCP JSON-RPC commands (via stdio) and the OpenCode "headless" REST API (`opencode serve`).
- **Capabilities:** It exposes approximately **79 tools** to the AI, allowing it to delegate complex, multi-step tasks (like refactoring or debugging) to a background process.
- **In this project:** Agent 1 (Luigi) uses `opencode-mcp` to treat Agent 2 (Mario) as a remote toolset, enabling seamless inter-agent delegation.

## Prerequisites

- Docker + Docker Compose
- A Google Gemini API key

## Setup

1. Copy the example env file and add your key:

   ```bash
   echo "GEMINI_API_KEY=your_key_here" > .env
   ```

2. Build and start both agents:

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
├── Dockerfile                          # Shared image (node:20-slim + opencode + curl + jq)
├── docker-compose.yml                  # Agent services and bridge network
├── .env                                # GEMINI_API_KEY (not committed)
├── agent1-config/
│   ├── opencode.json                   # Model config + agent2 MCP server
│   └── AGENTS.md                       # Persona: Luigi
├── agent2-config/
│   ├── opencode.json                   # Model config
│   └── AGENTS.md                       # Persona: Mario
└── scripts/
    └── curl-test.sh                    # Test helper
```

## Testing

### 1. Verify both agents are reachable

```bash
curl -s http://localhost:4097/session -X POST | jq .   # Agent 1
curl -s http://localhost:4098/session -X POST | jq .   # Agent 2
```

Each should return a JSON object with an `id` field.

### 2. Test Agent 1 in isolation

```bash
SESSION=$(curl -s -X POST http://localhost:4097/session | jq -r '.id')
curl -s -X POST "http://localhost:4097/session/$SESSION/message" \
  -H "Content-Type: application/json" \
  -d '{"parts":[{"type":"text","text":"What is your name?"}]}' \
  | jq -r '.parts[] | select(.type=="text") | .text'
# Expected: a reply from Luigi
```

### 3. Test Agent 2 in isolation

```bash
SESSION=$(curl -s -X POST http://localhost:4098/session | jq -r '.id')
curl -s -X POST "http://localhost:4098/session/$SESSION/message" \
  -H "Content-Type: application/json" \
  -d '{"parts":[{"type":"text","text":"What is your name?"}]}' \
  | jq -r '.parts[] | select(.type=="text") | .text'
# Expected: a reply from Mario
```

### 4. Test end-to-end delegation (Agent 1 → Agent 2)

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
| Delegation returns no text | Check `docker compose logs agent1` for `opencode-mcp` execution errors |

## Common commands

```bash
docker compose up --build       # Build and start
docker compose up               # Start without rebuilding
docker compose build agent1     # Rebuild a single agent
docker compose logs -f agent1   # Tail logs for one agent
docker compose down             # Stop everything
```
