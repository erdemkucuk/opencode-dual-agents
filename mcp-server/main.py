"""MCP server bridge exposing an opencode REST API via high-level workflow tools.

This server provides five hand-written composite workflow tools for common
operations, acting as a simplified interface for inter-agent delegation.

Transport mode is controlled by the ``MCP_PORT`` environment variable:

- Unset → stdio mode; the orchestrator agent spawns this as a local child process.
- Set    → SSE/HTTP mode on that port; used as a network sidecar.
"""

from __future__ import annotations

import asyncio
import json
import os
from typing import Any

import httpx
from dotenv import load_dotenv
from mcp.server.fastmcp import FastMCP

# Load .env so OPENCODE_BASE_URL and MCP_PORT can be set without shell exports.
load_dotenv()

# ---------------------------------------------------------------------------
# Module-level configuration
# ---------------------------------------------------------------------------

OPENCODE_BASE: str = os.getenv("OPENCODE_BASE_URL", "http://localhost:4096")
"""REST API base URL for the opencode instance.

Defaults to ``http://localhost:4096``.
"""

_raw_port: str | None = os.getenv("MCP_PORT")
MCP_PORT: int | None = int(_raw_port) if _raw_port else None
"""HTTP port for SSE transport; ``None`` selects stdio mode."""

_HTTP_TIMEOUT: float = 30.0

mcp: FastMCP = FastMCP("opencode-bridge")


# ---------------------------------------------------------------------------
# Utility functions
# ---------------------------------------------------------------------------


async def call_opencode(
    method: str,
    path: str,
    path_params: dict[str, Any] | None = None,
    query_params: dict[str, Any] | None = None,
    body: Any = None,
) -> Any:
    """Make an HTTP request to the opencode REST API.

    Substitutes ``{key}`` placeholders in *path* with values from
    *path_params*, then issues the request with optional query parameters
    and a JSON body.

    Args:
        method: HTTP verb (case-insensitive), e.g. ``"get"`` or ``"POST"``.
        path: URL path template, e.g. ``"/session/{sessionId}/message"``.
        path_params: Path-template variable substitutions.
        query_params: Query-string parameter key/value pairs.
        body: JSON-serialisable request body; ignored for GET/DELETE.

    Returns:
        Parsed JSON (``dict`` or ``list``) when the response contains valid
        JSON; otherwise the raw response text as a ``str``. Returns a
        descriptive error string if the request itself raises an exception.
    """
    resolved_path = path
    if path_params:
        for key, value in path_params.items():
            resolved_path = resolved_path.replace(f"{{{key}}}", str(value))

    url = f"{OPENCODE_BASE}{resolved_path}"

    async with httpx.AsyncClient(timeout=_HTTP_TIMEOUT) as client:
        try:
            response = await client.request(
                method=method.upper(),
                url=url,
                params=query_params,
                json=body,
            )
            try:
                return response.json()
            except Exception:  # noqa: BLE001 — JSON decode errors vary by version
                return response.text
        except Exception as exc:  # noqa: BLE001 — surface transport errors as strings
            return f"Error calling opencode: {exc}"


# ---------------------------------------------------------------------------
# Hand-written high-level workflow tools
# ---------------------------------------------------------------------------


@mcp.tool()
async def opencode_health() -> str:
    """Check whether the opencode server is healthy.

    Returns:
        JSON-formatted health status from ``GET /global/health``.
    """
    result = await call_opencode("get", "/global/health")
    return json.dumps(result, indent=2)


@mcp.tool()
async def opencode_ask(prompt: str, directory: str | None = None) -> str:
    """Send a one-shot prompt to opencode and return the response.

    Creates a new session, sends *prompt* synchronously via the session
    message endpoint, and returns the raw response.

    Args:
        prompt: Natural-language instruction for the opencode agent.
        directory: Optional working directory path for the session.

    Returns:
        JSON-formatted response from the session message endpoint, or an
        error string if session creation fails.
    """
    query: dict[str, str] = {}
    if directory:
        query["directory"] = directory

    session = await call_opencode("post", "/session", query_params=query)
    if isinstance(session, str) or "id" not in session:
        return f"Failed to create session: {session}"

    session_id: str = session["id"]
    response = await call_opencode(
        "post",
        f"/session/{session_id}/message",
        query_params=query,
        body={"parts": [{"type": "text", "text": prompt}]},
    )
    return json.dumps(response, indent=2)


@mcp.tool()
async def opencode_run(
    prompt: str,
    directory: str | None = None,
    timeout_ms: int = 20_000,
) -> str:
    """Run a task asynchronously and poll for completion.

    Fires *prompt* via the async endpoint, then polls ``GET /session/status``
    every two seconds until the session finishes or *timeout_ms* elapses.

    Args:
        prompt: Natural-language task for the opencode agent.
        directory: Optional working directory path for the session.
        timeout_ms: Maximum time to wait for completion, in milliseconds.

    Returns:
        JSON-formatted list of all messages produced during the session, or
        an error string if session creation fails.
    """
    query: dict[str, str] = {}
    if directory:
        query["directory"] = directory

    session = await call_opencode("post", "/session", query_params=query)
    if isinstance(session, str) or "id" not in session:
        return f"Failed to create session: {session}"

    session_id: str = session["id"]
    await call_opencode(
        "post",
        f"/session/{session_id}/prompt_async",
        query_params=query,
        body={"parts": [{"type": "text", "text": prompt}]},
    )

    loop = asyncio.get_running_loop()
    deadline = loop.time() + (timeout_ms / 1000.0)
    while loop.time() < deadline:
        await asyncio.sleep(2)
        status = await call_opencode("get", "/session/status")
        if isinstance(status, dict) and session_id in status:
            if status[session_id].get("running") is not True:
                break
        else:
            break

    messages = await call_opencode(
        "get", f"/session/{session_id}/message", query_params=query
    )
    return json.dumps(messages, indent=2)


@mcp.tool()
async def opencode_status() -> str:
    """Get a combined snapshot of server health, session count, and providers.

    Bundles three API calls into one convenient response.

    Returns:
        JSON object with keys ``health``, ``session_count``, and
        ``providers``.
    """
    health = await call_opencode("get", "/global/health")
    sessions = await call_opencode("get", "/session")
    providers = await call_opencode("get", "/provider")
    session_count = len(sessions) if isinstance(sessions, list) else 0
    return json.dumps(
        {"health": health, "session_count": session_count, "providers": providers},
        indent=2,
    )


@mcp.tool()
async def opencode_context(directory: str | None = None) -> str:
    """Get current project context: resolved path, VCS info, and config.

    Args:
        directory: Optional path to query context for a specific directory.

    Returns:
        JSON object with keys ``path``, ``vcs``, and ``config``.
    """
    query: dict[str, str] = {}
    if directory:
        query["directory"] = directory

    path = await call_opencode("get", "/path", query_params=query)
    vcs = await call_opencode("get", "/vcs", query_params=query)
    config = await call_opencode("get", "/config", query_params=query)
    return json.dumps({"path": path, "vcs": vcs, "config": config}, indent=2)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def main() -> None:
    """Start the MCP server with the five workflow tools.

    Transport mode depends on ``MCP_PORT``:

    - Set  → SSE/HTTP server on that port (network-accessible sidecar).
    - Unset → stdio subprocess (parent process communicates via stdin/stdout).
    """
    try:
        if MCP_PORT:
            mcp.run(transport="sse", port=MCP_PORT, host="0.0.0.0")
        else:
            mcp.run(transport="stdio")
    except Exception as exc:  # noqa: BLE001 — fatal startup errors
        print(f"Fatal error: {exc}")
        raise SystemExit(1) from exc


if __name__ == "__main__":
    main()
