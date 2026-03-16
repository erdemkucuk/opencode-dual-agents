"""MCP server bridge for Luigi (Agent 1).

Exposes tools for delegating tasks to Mario (Agent 2) via the A2A protocol.
The A2A task lifecycle replaces the hand-rolled async polling loop.

Always runs as an SSE/HTTP server on port 8000.
"""

from __future__ import annotations

import json
import os
import sys
import uuid
from typing import Any

import httpx
from a2a.client import ClientFactory
from a2a.client.client_factory import ClientConfig
from a2a.types import Message, Part, Role, TextPart
from dotenv import load_dotenv
from mcp.server.fastmcp import FastMCP

# Load .env so A2A_MARIO_URL can be set without shell exports.
load_dotenv()

# ---------------------------------------------------------------------------
# Module-level configuration
# ---------------------------------------------------------------------------

A2A_MARIO_URL: str = os.getenv("A2A_MARIO_URL", "http://agent2:8000")
_HTTP_TIMEOUT: float = 60.0

mcp: FastMCP = FastMCP(
    "opencode-bridge",
    host="0.0.0.0",
    port=8000,
)


# ---------------------------------------------------------------------------
# A2A client helper
# ---------------------------------------------------------------------------


def _new_user_message(prompt: str) -> Message:
    return Message(
        role=Role.user,
        parts=[Part(root=TextPart(text=prompt))],
        message_id=str(uuid.uuid4()),
    )


def _extract_text(event: Any) -> str:
    """Pull the text content out of a client event (Message or Task tuple)."""
    if isinstance(event, Message):
        return "\n".join(
            p.root.text for p in event.parts if hasattr(p.root, "text")
        )
    if isinstance(event, tuple):
        # (Task, UpdateEvent | None)
        task, _ = event
        if task.status and task.status.message:
            msg = task.status.message
            return "\n".join(
                p.root.text for p in msg.parts if hasattr(p.root, "text")
            )
    return ""


async def _call_mario(prompt: str) -> str:
    """Send a prompt to Mario via A2A and return the text response.

    Args:
        prompt: Natural-language instruction for Mario.

    Returns:
        The agent's text response, or an error message string.
    """
    message = _new_user_message(prompt)
    async with httpx.AsyncClient(timeout=_HTTP_TIMEOUT) as http_client:
        try:
            client = await ClientFactory.connect(
                A2A_MARIO_URL, ClientConfig(httpx_client=http_client)
            )
            async for event in client.send_message(message):
                text = _extract_text(event)
                if text:
                    return text
            return ""
        except Exception as exc:
            return f"Error calling Mario via A2A: {exc}"


# ---------------------------------------------------------------------------
# MCP tools
# ---------------------------------------------------------------------------


@mcp.tool()
async def opencode_health() -> str:
    """Check whether Mario (Agent 2) is healthy via its A2A Agent Card.

    Returns:
        JSON-formatted health status derived from the Agent Card endpoint.
    """
    async with httpx.AsyncClient(timeout=10.0) as client:
        try:
            resp = await client.get(
                f"{A2A_MARIO_URL}/.well-known/agent.json"
            )
            resp.raise_for_status()
            return json.dumps(
                {"status": "healthy", "agent": resp.json()}, indent=2
            )
        except Exception as exc:
            return json.dumps(
                {"status": "unhealthy", "error": str(exc)}, indent=2
            )


@mcp.tool()
async def opencode_ask(prompt: str) -> str:
    """Send a one-shot prompt to Mario (Agent 2) via A2A and return the response.

    Args:
        prompt: Natural-language instruction for the opencode agent.

    Returns:
        The agent's text response.
    """
    return await _call_mario(prompt)


@mcp.tool()
async def opencode_run(prompt: str, timeout_ms: int = 60_000) -> str:
    """Run a task on Mario (Agent 2) via A2A and return the response.

    The A2A protocol handles the task lifecycle natively — no custom
    polling loop is needed.

    Args:
        prompt: Natural-language task for the opencode agent.
        timeout_ms: Kept for API compatibility; A2A handles its own timeout.

    Returns:
        JSON object with the agent's response under the ``result`` key.
    """
    result = await _call_mario(prompt)
    return json.dumps({"result": result}, indent=2)


@mcp.tool()
async def opencode_run_final(prompt: str, timeout_ms: int = 60_000) -> str:
    """Run a task on Mario (Agent 2) via A2A and return the final response.

    Args:
        prompt: Natural-language task for the opencode agent.
        timeout_ms: Kept for API compatibility; A2A handles its own timeout.

    Returns:
        The final text response from the agent.
    """
    return await _call_mario(prompt)


@mcp.tool()
async def opencode_status() -> str:
    """Get a snapshot of Mario (Agent 2)'s status via its A2A Agent Card.

    Returns:
        JSON object with ``agent_card`` and ``status`` keys.
    """
    async with httpx.AsyncClient(timeout=10.0) as client:
        try:
            resp = await client.get(
                f"{A2A_MARIO_URL}/.well-known/agent.json"
            )
            resp.raise_for_status()
            return json.dumps(
                {"agent_card": resp.json(), "status": "reachable"}, indent=2
            )
        except Exception as exc:
            return json.dumps(
                {"status": "unreachable", "error": str(exc)}, indent=2
            )


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def main() -> None:
    """Start the MCP server as an SSE/HTTP sidecar on port 8000."""
    try:
        mcp.run(transport="sse")
    except Exception as exc:
        sys.stderr.write(f"Fatal error: {exc}\n")
        raise SystemExit(1) from exc


if __name__ == "__main__":
    main()
