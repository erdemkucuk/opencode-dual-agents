# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Architecture

Two containerized `opencode serve` instances communicate over a Docker bridge network named `agents`. Both use the free `opencode/minimax-m2.5-free` model for testing.

- **Agent 1** (`agent1-config/`, host port 4097 → container port 4096) — orchestrator. Spawns the custom MCP server as a local stdio child process to interact with Agent 2.
- **Agent 2** (`agent2-config/`, host port 4098 → container port 4096) — worker. Also runs the custom MCP server as an HTTP sidecar on port 4095 (host port 4099).

Each agent's config directory is volume-mounted to `/agent` inside its container. `opencode.json` at the root of each config dir configures the provider and model. Agent identity/persona is set in `AGENTS.md` inside each config dir (read by opencode on startup).

### Inter-agent communication flow

Agent 1 → custom MCP server (stdio) → Agent 2's REST API:

Agent 1 uses tools provided by the `agent2` MCP server. These tools are auto-generated at startup by fetching `GET http://agent2:4096/doc` (opencode's OpenAPI spec) and registering one tool per endpoint (~104 tools), plus 5 hand-written workflow composites (`opencode_ask`, `opencode_run`, `opencode_status`, `opencode_health`, `opencode_context`).

Agent 2 also runs the same MCP server binary in HTTP Streamable mode on port 4095, making all 109 tools available over HTTP from the host on port 4099.

## Key files

| Path | Purpose |
|---|---|
| `Dockerfile` | Shared image: node:20-slim + opencode-ai + built custom MCP server + curl + jq |
| `docker-compose.yml` | Defines both agent services and the bridge network |
| `agent1-config/opencode.json` | Agent 1 model config + `agent2` MCP server config (type: local, python command) |
| `agent2-config/opencode.json` | Agent 2 model config |
| `agent1-config/AGENTS.md` | Agent 1 persona/identity (name: Luigi) |
| `agent2-config/AGENTS.md` | Agent 2 persona/identity (name: Mario) |
| `mcp-server/main.py` | Custom Python FastMCP server: fetches opencode OpenAPI spec, registers tools, dual stdio/SSE mode |
| `mcp-server/requirements.txt` | Python MCP server deps: `mcp[cli]`, `httpx`, `python-dotenv` |
| `mcp-server/entrypoint.sh` | Generic entrypoint: runs opencode + optional MCP sidecar sidecar (if `MCP_PORT` set) |
| `scripts/curl-test.sh` | Helper script to send a test prompt to Agent 1 from the host |

## Commands

```bash
# Build and start both agents
docker compose up --build

# Start without rebuilding
docker compose up

# Rebuild a single agent
docker compose build agent1

# Tail logs for one agent
docker compose logs -f agent1

# Stop everything
docker compose down
```

## OpenCode config conventions

- Use `{env:VAR_NAME}` syntax (not `$VAR`) for environment variables inside `opencode.json`.
- Model IDs use `opencode/` prefix (e.g. `opencode/minimax-m2.5-free`).
- Skills are directories under `.agents/skills/<name>/` where the directory name matches the `name` frontmatter field exactly (lowercase, hyphens only).
- `--hostname 0.0.0.0` is required when running `opencode serve` inside Docker — the default `127.0.0.1` is not reachable from other containers.

## Secrets

`.env` is excluded from Git, Claude Code, Copilot, and Gemini CLI via `.gitignore`, `.claudeignore`, `.copilotignore`, and `.geminiignore` respectively. Use it for any API keys required by providers if switching from the free model.
