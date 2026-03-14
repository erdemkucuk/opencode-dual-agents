# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Architecture

Two containerized `opencode serve` instances communicate over a Docker bridge network named `agents`. Both use Google Gemini via `GEMINI_API_KEY`.

- **Agent 1** (`agent1-config/`, host port 4097 → container port 4096) — orchestrator. Uses `opencode-mcp` bridge to interact with Agent 2 as an MCP server.
- **Agent 2** (`agent2-config/`, host port 4098 → container port 4096) — worker. Exposes its tools to Agent 1 via the `opencode-mcp` bridge.

Each agent's config directory is volume-mounted to `/agent` inside its container. `opencode.json` at the root of each config dir configures the provider and model. Agent identity/persona is set in `AGENTS.md` inside each config dir (read by opencode on startup).

### Inter-agent communication flow

Agent 1 → `opencode-mcp` → Agent 2's REST API:

Agent 1 uses tools provided by the `agent2` MCP server. These tools (e.g., `agent2_opencode_ask`, `agent2_opencode_run`) wrap Agent 2's session and message endpoints.

## Key files

| Path | Purpose |
|---|---|
| `Dockerfile` | Shared image: node:20-slim + opencode-ai + opencode-mcp + curl + jq |
| `docker-compose.yml` | Defines both agent services and the bridge network |
| `.env` | `GEMINI_API_KEY` — never commit, excluded by all ignore files |
| `agent1-config/opencode.json` | Agent 1 model config + `agent2` MCP server config |
| `agent2-config/opencode.json` | Agent 2 model config |
| `agent1-config/AGENTS.md` | Agent 1 persona/identity (name: Luigi) |
| `agent2-config/AGENTS.md` | Agent 2 persona/identity (name: Mario) |
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
- Model IDs use `google/` prefix (e.g. `google/gemini-3-flash-preview`).
- Skills are directories under `.agents/skills/<name>/` where the directory name matches the `name` frontmatter field exactly (lowercase, hyphens only).
- `--hostname 0.0.0.0` is required when running `opencode serve` inside Docker — the default `127.0.0.1` is not reachable from other containers.

## .env and secrets

`.env` is excluded from Git, Claude Code, Copilot, and Gemini CLI via `.gitignore`, `.claudeignore`, `.copilotignore`, and `.geminiignore` respectively.
