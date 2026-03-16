# opencode-dual-agents

A multi-agent system prototype using `opencode-ai` where two containerized agents communicate over a Docker bridge network via the [Agent2Agent (A2A) protocol](https://github.com/google-a2a/a2a-python). Agent 1 (Luigi) acts as an orchestrator, delegating tasks to Agent 2 (Mario) through a thin MCP bridge that internally uses A2A.

## Architecture

The system consists of two Docker services:

- **Agent 1 (Luigi)**: Orchestrator agent.
  - Port: `4097` (host) -> `4096` (container).
  - Port (MCP): `4100` (host) -> `8000` (container) - MCP SSE sidecar (`bridge.py`).
  - Config: `agent1-config/`.
- **Agent 2 (Mario)**: Worker agent.
  - Port: `4098` (host) -> `4096` (container).
  - Port (A2A): `4099` (host) -> `8000` (container) - A2A HTTP sidecar (`a2a_server.py`).
  - Config: `agent2-config/`.

### Inter-agent Communication

```
Luigi LLM → MCP tool call → bridge.py (SSE/:8000) → A2A → a2a_server.py (:8000) → Mario's opencode REST API (:4096)
```

Agent 1's MCP sidecar (`bridge.py`) exposes 5 tools backed by the A2A protocol:
- `opencode_health`: Check Agent 2 health via its A2A Agent Card.
- `opencode_ask`: One-shot prompt delegated to Agent 2 via A2A.
- `opencode_run`: Task delegated to Agent 2 via A2A (returns full response).
- `opencode_run_final`: Task delegated to Agent 2 via A2A (returns final message only).
- `opencode_status`: Snapshot of Agent 2's status from its A2A Agent Card.

Agent 2's A2A sidecar (`a2a_server.py`) exposes:
- `GET /.well-known/agent.json`: Agent Card for capability discovery.
- `POST /`: Task submission (JSON-RPC, A2A protocol).

## Key Files

| Path | Purpose |
|---|---|
| `Dockerfile` | Shared image: node:20-slim + opencode-ai + built custom MCP/A2A server. |
| `docker-compose.yml` | Service definitions and bridge network (`agents`). |
| `agent1-config/` | Agent 1 configuration and identity (Luigi). |
| `agent2-config/` | Agent 2 configuration, identity (Mario), and `agent-card.json`. |
| `mcp-server/bridge.py` | MCP SSE sidecar for Luigi — delegates to Mario via A2A client. |
| `mcp-server/a2a_server.py` | A2A HTTP sidecar for Mario — wraps Mario's opencode REST API. |
| `mcp-server/entrypoint.sh` | Container entrypoint: runs opencode + the appropriate sidecar. |
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

### Adding New MCP Tools
- Modify `mcp-server/bridge.py` to add new `@mcp.tool()` definitions.
- Each tool should use `_call_mario()` or the A2A client to delegate work to Agent 2.
- If the tool requires new dependencies, update `mcp-server/requirements.txt`.
