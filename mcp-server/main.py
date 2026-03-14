"""MCP server bridge exposing Agent 2's opencode REST API as MCP tools.

At startup, fetches Agent 2's OpenAPI spec and auto-generates ~104 typed MCP
tools (one per endpoint). Also registers five hand-written composite workflow
tools for common operations.

Transport mode is controlled by the ``MCP_PORT`` environment variable:

- Unset → stdio mode; Agent 1 spawns this as a local child process.
- Set    → SSE/HTTP mode on that port; used as Agent 2's network sidecar.
"""

from __future__ import annotations

import asyncio
import json
import os
import re
from collections.abc import Callable, Coroutine
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
"""REST API base URL for Agent 2's opencode instance.

Overridden to ``http://agent2:4096`` inside Docker via the environment.
"""

_raw_port: str | None = os.getenv("MCP_PORT")
MCP_PORT: int | None = int(_raw_port) if _raw_port else None
"""HTTP port for SSE transport; ``None`` selects stdio mode."""

# Retry / timeout tunables for spec fetching and HTTP calls.
_SPEC_RETRIES: int = 15
_SPEC_RETRY_DELAY: float = 2.0
_SPEC_TIMEOUT: float = 5.0
_HTTP_TIMEOUT: float = 30.0
_DESCRIPTION_MAX_LEN: int = 500

mcp: FastMCP = FastMCP("agent2-opencode-bridge")


# ---------------------------------------------------------------------------
# Utility functions
# ---------------------------------------------------------------------------


def sanitize_name(raw: str) -> str:
    """Convert a camelCase/PascalCase operationId into a valid snake_case tool name.

    Args:
        raw: Raw operationId from the OpenAPI spec (e.g. ``"getSessionMessage"``).

    Returns:
        A lowercase, underscore-separated identifier containing only
        ``[a-z0-9_]`` characters (e.g. ``"get_session_message"``).
    """
    s1 = re.sub(r"(.)([A-Z][a-z]+)", r"\1_\2", raw)
    s2 = re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", s1).lower()
    return re.sub(r"[^a-z0-9_]", "_", s2).strip("_")


async def call_opencode(
    method: str,
    path: str,
    path_params: dict[str, Any] | None = None,
    query_params: dict[str, Any] | None = None,
    body: Any = None,
) -> Any:
    """Make an HTTP request to Agent 2's opencode REST API.

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


async def fetch_spec() -> dict[str, Any]:
    """Fetch Agent 2's OpenAPI spec from ``GET /doc`` with retry logic.

    Retries up to ``_SPEC_RETRIES`` times with ``_SPEC_RETRY_DELAY``-second
    pauses to tolerate the case where Agent 2's opencode server is still
    starting up.

    Returns:
        Parsed OpenAPI specification as a dictionary.

    Raises:
        RuntimeError: If the server does not respond successfully within
            the retry budget.
    """
    print(f"Connecting to opencode at {OPENCODE_BASE}...")
    for attempt in range(_SPEC_RETRIES):
        try:
            async with httpx.AsyncClient(timeout=_SPEC_TIMEOUT) as client:
                response = await client.get(f"{OPENCODE_BASE}/doc")
                if response.status_code == 200:
                    print("OpenAPI spec loaded.")
                    return response.json()
        except Exception:  # noqa: BLE001 — server may not be up yet
            pass

        await asyncio.sleep(_SPEC_RETRY_DELAY)
        if attempt % 3 == 0:
            print(f"Waiting for opencode (attempt {attempt + 1})...")

    raise RuntimeError(
        f"opencode never became healthy after {_SPEC_RETRIES * _SPEC_RETRY_DELAY:.0f} s"
    )


# ---------------------------------------------------------------------------
# Dynamic tool registration
# ---------------------------------------------------------------------------


def register_dynamic_tools(spec: dict[str, Any]) -> None:
    """Auto-generate one MCP tool per endpoint found in the OpenAPI spec.

    For each ``(path, method)`` combination that carries an ``operationId``:

    - Derives a snake_case tool name via :func:`sanitize_name`.
    - Separates path params, query params, and an optional request body.
    - Registers an async handler with FastMCP that routes ``**kwargs`` to
      :func:`call_opencode`.

    Args:
        spec: Parsed OpenAPI specification dictionary as returned by
            :func:`fetch_spec`.

    Note:
        ``make_handler`` is a closure factory used to correctly capture loop
        variables — a common Python gotcha with late-binding closures in
        ``for`` loops.
    """
    paths: dict[str, Any] = spec.get("paths", {})
    for path, methods in paths.items():
        for http_method, op in methods.items():
            operation_id: str | None = op.get("operationId")
            if not operation_id:
                continue

            tool_name = sanitize_name(operation_id)
            summary: str = (
                op.get("summary")
                or op.get("description")
                or f"{http_method.upper()} {path}"
            )
            description = summary[:_DESCRIPTION_MAX_LEN]

            params: list[dict[str, Any]] = op.get("parameters", [])
            path_params_spec = [p for p in params if p.get("in") == "path"]
            query_params_spec = [p for p in params if p.get("in") == "query"]
            # Only non-GET/DELETE endpoints with a requestBody carry a body.
            has_body = (
                http_method.lower() not in {"get", "delete"} and "requestBody" in op
            )

            def make_handler(
                m: str,
                p: str,
                pps: list[dict[str, Any]],
                qps: list[dict[str, Any]],
                hb: bool,
            ) -> Callable[..., Coroutine[Any, Any, str]]:
                async def handler(**kwargs: Any) -> str:
                    path_vals: dict[str, Any] = {}
                    query_vals: dict[str, Any] = {}
                    body_val: Any = None

                    for spec_p in pps:
                        name = spec_p["name"]
                        if name in kwargs:
                            path_vals[name] = kwargs[name]
                    for spec_p in qps:
                        name = spec_p["name"]
                        if name in kwargs:
                            query_vals[name] = kwargs[name]
                    if hb and "body" in kwargs:
                        body_val = kwargs["body"]

                    result = await call_opencode(m, p, path_vals, query_vals, body_val)
                    if isinstance(result, (dict, list)):
                        return json.dumps(result, indent=2)
                    return str(result)

                return handler

            handler = make_handler(
                http_method, path, path_params_spec, query_params_spec, has_body
            )
            mcp.tool(name=tool_name, description=description)(handler)


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
    """Fetch the OpenAPI spec, register all tools, then start the MCP server.

    Uses a dedicated event loop to synchronously await the spec before any
    async MCP machinery starts. Transport mode depends on ``MCP_PORT``:

    - Set  → SSE/HTTP server on that port (Agent 2's network-accessible
      sidecar, exposed on host port 4099).
    - Unset → stdio subprocess (Agent 1 communicates via stdin/stdout pipes).
    """
    try:
        # Fetch the spec synchronously before the MCP async runtime starts.
        loop = asyncio.new_event_loop()
        spec = loop.run_until_complete(fetch_spec())
        loop.close()

        # Dynamically register ~104 tools from the fetched spec.
        register_dynamic_tools(spec)

        if MCP_PORT:
            mcp.run(transport="sse", port=MCP_PORT, host="0.0.0.0")
        else:
            mcp.run(transport="stdio")
    except Exception as exc:  # noqa: BLE001 — fatal startup errors
        print(f"Fatal error: {exc}")
        raise SystemExit(1) from exc


if __name__ == "__main__":
    main()
