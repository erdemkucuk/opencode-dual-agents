# opencode-dual-agents

A demo of two containerized [opencode](https://opencode.ai) agents communicating over a Docker bridge network. Agent 1 (Luigi) orchestrates tasks by delegating to Agent 2 (Mario) via HTTP.

## Architecture

```
Host
 └─ docker compose
     ├─ agent1 (Luigi)  :4097 ──── delegate-to-agent2 skill ──► agent2:4096
     └─ agent2 (Mario)  :4098
```

Both agents run `opencode serve` inside Docker and use Google Gemini (`gemini-3-flash-preview`) via a shared `GEMINI_API_KEY`.

- **Agent 1 / Luigi** — orchestrator. Exposes port 4097 on the host. Has a `delegate-to-agent2` skill that creates a session on Agent 2 and sends it a prompt via curl + jq.
- **Agent 2 / Mario** — worker. Exposes port 4098 on the host. Receives delegated prompts and responds independently.

### Inter-agent communication

```
POST /session              → create session, returns id
POST /session/{id}/message → send prompt, returns reply parts
```

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
bash scripts/curl-test.sh "Use your delegate-to-agent2 skill to summarise the Fibonacci sequence."
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
│   ├── opencode.json                   # Model config
│   ├── AGENTS.md                       # Persona: Luigi
│   └── .agents/skills/
│       └── delegate-to-agent2/
│           └── SKILL.md               # Delegation skill
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
  -d '{"parts":[{"type":"text","text":"Use your delegate-to-agent2 skill to ask Agent 2 what its name is, then tell me the answer."}]}' \
  | jq -r '.parts[] | select(.type=="text") | .text'
# Expected: Agent 1 delegates to Agent 2, who identifies itself as Mario
```

Or use the helper script: `bash scripts/curl-test.sh`

This asks Agent 1 to use its `delegate-to-agent2` skill to query Agent 2's name. Expected output ends with Agent 2 identifying itself as Mario.

### Troubleshooting

| Symptom | Likely cause |
|---|---|
| `curl` hangs or returns empty | Agents not running — check `docker compose ps` |
| `null` session id | Agent started but not ready yet — wait a few seconds and retry |
| Delegation returns no text | Check `docker compose logs agent1` for skill execution errors |

## Common commands

```bash
docker compose up --build       # Build and start
docker compose up               # Start without rebuilding
docker compose build agent1     # Rebuild a single agent
docker compose logs -f agent1   # Tail logs for one agent
docker compose down             # Stop everything
```
