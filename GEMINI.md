# opencode-dual-agents

A multi-agent system prototype using `opencode-ai` where two containerized agents communicate over a Docker bridge network. Agent 1 (Luigi) acts as an orchestrator, delegating tasks to Agent 2 (Mario) via a custom Python-based MCP (Model Context Protocol) server.

## Architecture

The system consists of two Docker services:

- **Agent 1 (Luigi)**: Orchestrator agent.
  - Port: `4097` (host) -> `4096` (container).
  - Port (MCP): `4100` (host) -> `8000` (container) - SSE sidecar mode.
  - Config: `agent1-config/`.
- **Agent 2 (Mario)**: Worker agent.
  - Port: `4098` (host) -> `4096` (container).
  - Port (MCP): `4099` (host) -> `8000` (container) - SSE sidecar mode.
  - Config: `agent2-config/`.

### Inter-agent Communication

Agent 1 uses 5 custom workflow tools provided by the `mcp-server`:
- `opencode_health`: Check Agent 2 health.
- `opencode_ask`: One-shot synchronous prompt.
- `opencode_run`: Async task with polling (returns full history).
- `opencode_run_final`: Async task with polling (returns last message only).
- `opencode_status`: Combined snapshot of health, sessions, and providers.

## Key Files

| Path | Purpose |
|---|---|
| `Dockerfile` | Shared image: node:20-slim + opencode-ai + built custom MCP server. |
| `docker-compose.yml` | Service definitions and bridge network (`agents`). |
| `agent1-config/` | Agent 1 configuration and identity (Luigi). |
| `agent2-config/` | Agent 2 configuration and identity (Mario). |
| `mcp-server/bridge.py` | Custom Python FastMCP server (SSE/HTTP mode on port 8000). |
| `mcp-server/entrypoint.sh` | Generic container entrypoint for opencode + optional MCP sidecar. |
| `tests/` | Pytest integration tests for end-to-end communication. |

## Building and Running

### Prerequisites
- Docker and Docker Compose.
- Python 3.12+ (for local testing/linting).

### Commands

```bash
# Build and start both agents
docker compose up --build

# Start without rebuilding
docker compose up

# Stop all services
docker compose down

# Run integration tests (rebuilds images)
make test

# Run integration tests (skips rebuild)
make test-fast

# Tail logs for a specific agent
docker compose logs -f agent1
```

## Development Conventions

### Python Environment
- Use the provided `Makefile` to manage the virtual environment: `make .venv`.
- Python code uses `ruff` for linting and formatting.

### OpenCode Configuration
- Configuration files are located in `agent1-config/` and `agent2-config/`.
- `opencode.json` defines the model and MCP tools.
- `AGENTS.md` defines the persona/identity of the agent.

### Testing Strategy
- Integration tests are located in `tests/test_integration.py`.
- Tests use `pytest` and `httpx` to verify the agents are reachable and communicating correctly.
- A session-scoped fixture handles the Docker lifecycle during testing.

### Adding New Tools
- Modify `mcp-server/bridge.py` to add new `@mcp.tool()` definitions.
- Ensure the tools are properly documented with docstrings for the LLM to understand their usage.
- If the tool requires new dependencies, update `mcp-server/requirements.txt`.
