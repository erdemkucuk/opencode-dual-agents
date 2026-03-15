"""
MCP server bridge exposing an opencode REST API via high-level workflow tools.

This server provides five hand-written composite workflow tools for common
operations, acting as a simplified interface for inter-agent delegation.

Always runs as an SSE/HTTP server on port 8000.
"""

from __future__ import annotations

import asyncio
import json
import os
from typing import Any

import httpx
from dotenv import load_dotenv
from mcp.server.fastmcp import FastMCP

# Load .env so OPENCODE_BASE_URL can be set without shell exports.
load_dotenv()

# ---------------------------------------------------------------------------
# Module-level configuration
# ---------------------------------------------------------------------------

OPENCODE_BASE: str = os.getenv("OPENCODE_BASE_URL", "http://localhost:4096")
"""REST API base URL for the opencode instance.

Defaults to ``http://localhost:4096``.
"""

_HTTP_TIMEOUT: float = 60.0

mcp: FastMCP = FastMCP(
    "opencode-bridge",
    host="0.0.0.0",
    port=8000,
)


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
            except Exception:
                return response.text
        except Exception as exc:
            return f"Error calling opencode: {exc}"


async def _create_session(directory: str | None) -> tuple[str, str, dict[str, str]]:
    """Create a new opencode session.

    Args:
        directory: Optional working directory for the session.  When
            provided it is forwarded as a ``directory`` query parameter on
            every subsequent request that belongs to this session.

    Returns:
        A ``(error_string, session_id, query)`` tuple where:

        - *error_string* — non-empty human-readable message when session
          creation fails; empty string on success.
        - *session_id* — the opaque session identifier returned by the API;
          empty string on failure.
        - *query* — ready-to-use query-parameter dict (``{"directory": …}``
          when *directory* was supplied, otherwise ``{}``); pass this as
          *query_params* to every ``call_opencode`` call in the same session
          so the API routes requests to the correct working directory.
    """
    query: dict[str, str] = {"directory": directory} if directory else {}
    session = await call_opencode("post", "/session", query_params=query)
    if isinstance(session, str) or "id" not in session:
        return f"Failed to create session: {session}", "", {}
    return "", session["id"], query


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
    error, session_id, query = await _create_session(directory)
    if error:
        return error

    response = await call_opencode(
        "post",
        f"/session/{session_id}/message",
        query_params=query,
        body={"parts": [{"type": "text", "text": prompt}]},
    )
    return json.dumps(response, indent=2)


async def _run_async_session(
    prompt: str,
    directory: str | None,
    timeout_ms: int,
) -> tuple[str, list[Any] | Any]:
    """Create a session, fire an async prompt, and poll until completion.

    Returns:
        A ``(error_string, messages)`` tuple.  On failure *error_string* is
        non-empty and *messages* is ``None``; on success *error_string* is
        empty and *messages* holds the session message list.
    """
    error, session_id, query = await _create_session(directory)
    if error:
        return error, None

    prompt_result = await call_opencode(
        "post",
        f"/session/{session_id}/prompt_async",
        query_params=query,
        body={"parts": [{"type": "text", "text": prompt}]},
    )
    if isinstance(prompt_result, str) and prompt_result.startswith("Error"):
        return f"Failed to submit prompt: {prompt_result}", None

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
        "get",
        f"/session/{session_id}/message",
        query_params=query,
    )
    return "", messages


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
    error, messages = await _run_async_session(prompt, directory, timeout_ms)
    if error:
        return error
    return json.dumps(messages, indent=2)


@mcp.tool()
async def opencode_run_final(
    prompt: str,
    directory: str | None = None,
    timeout_ms: int = 20_000,
) -> str:
    """Run a task asynchronously and poll for completion, returning the last message.

    Fires *prompt* via the async endpoint, then polls ``GET /session/status``
    every two seconds until the session finishes or *timeout_ms* elapses.

    Args:
        prompt: Natural-language task for the opencode agent.
        directory: Optional working directory path for the session.
        timeout_ms: Maximum time to wait for completion, in milliseconds.

    Returns:
        JSON-formatted final message produced during the session, or
        an error string if session creation fails or no messages were returned.

    """
    error, messages = await _run_async_session(prompt, directory, timeout_ms)
    if error:
        return error
    if isinstance(messages, list) and len(messages) > 0:
        return json.dumps(messages[-1], indent=2)
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


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def main() -> None:
    """Start the MCP server as an SSE/HTTP sidecar on port 8000."""
    import sys

    try:
        mcp.run(transport="sse")
    except Exception as exc:
        sys.stderr.write(f"Fatal error: {exc}\n")
        raise SystemExit(1) from exc


if __name__ == "__main__":
    main()
