"""A2A server adapter for Mario (Agent 2).

Exposes Mario's opencode agent via the Agent2Agent (A2A) protocol:
- GET /.well-known/agent.json -> Agent Card (capability discovery)
- POST /                      -> Task submission (JSON-RPC)

Always runs as an HTTP server on port 8000.
"""

from __future__ import annotations

import json
import os
import sys

import httpx
import uvicorn
from a2a.server.agent_execution import AgentExecutor, RequestContext
from a2a.server.apps import A2AStarletteApplication
from a2a.server.events import EventQueue
from a2a.server.request_handlers import DefaultRequestHandler
from a2a.server.tasks import InMemoryTaskStore
from a2a.types import AgentCapabilities, AgentCard, AgentSkill
from a2a.utils import new_agent_text_message

# ---------------------------------------------------------------------------
# Module-level configuration
# ---------------------------------------------------------------------------

OPENCODE_BASE: str = os.getenv("OPENCODE_BASE_URL", "http://localhost:4096")
_HTTP_TIMEOUT: float = 120.0


# ---------------------------------------------------------------------------
# opencode REST API helper
# ---------------------------------------------------------------------------


async def _run_opencode_prompt(prompt: str) -> str:
    """Create a session and run a prompt synchronously via opencode REST API.

    Args:
        prompt: Natural-language instruction for the opencode agent.

    Returns:
        The agent's text response, or a raw JSON dump if no text parts found.
    """
    async with httpx.AsyncClient(timeout=_HTTP_TIMEOUT) as client:
        resp = await client.post(f"{OPENCODE_BASE}/session")
        resp.raise_for_status()
        session_id = resp.json()["id"]

        payload = {"parts": [{"type": "text", "text": prompt}]}
        resp = await client.post(
            f"{OPENCODE_BASE}/session/{session_id}/message", json=payload
        )
        resp.raise_for_status()
        data = resp.json()

    texts = [p["text"] for p in data.get("parts", []) if p.get("type") == "text"]
    return "\n".join(texts) if texts else json.dumps(data)


# ---------------------------------------------------------------------------
# A2A AgentExecutor implementation
# ---------------------------------------------------------------------------


class OpenCodeAgentExecutor(AgentExecutor):
    """Executes A2A tasks by delegating to Mario's local opencode instance."""

    async def execute(self, context: RequestContext, event_queue: EventQueue) -> None:
        """Run the incoming prompt via opencode and enqueue the result."""
        prompt = context.get_user_input()
        try:
            result = await _run_opencode_prompt(prompt)
        except Exception as exc:
            result = f"Error running task: {exc}"

        await event_queue.enqueue_event(
            new_agent_text_message(
                result,
                context_id=context.context_id,
                task_id=context.task_id,
            )
        )

    async def cancel(self, context: RequestContext, event_queue: EventQueue) -> None:
        """Cancellation is not supported."""


# ---------------------------------------------------------------------------
# Agent Card
# ---------------------------------------------------------------------------


def _build_agent_card() -> AgentCard:
    agent_url = os.getenv("A2A_SERVER_URL", "http://agent2:8000/")
    return AgentCard(
        name="Mario",
        description="Worker agent. Executes tasks delegated by Luigi.",
        version="1.0.0",
        url=agent_url,
        capabilities=AgentCapabilities(streaming=False),
        skills=[
            AgentSkill(
                id="execute_task",
                name="Execute Task",
                description=(
                    "Runs a prompt via the local opencode instance"
                    " and returns the result."
                ),
            )
        ],
    )


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def main() -> None:
    """Start the A2A server as an HTTP sidecar on port 8000."""
    card = _build_agent_card()
    executor = OpenCodeAgentExecutor()
    store = InMemoryTaskStore()
    handler = DefaultRequestHandler(agent_executor=executor, task_store=store)
    app = A2AStarletteApplication(agent_card=card, http_handler=handler)

    try:
        uvicorn.run(app.build(), host="0.0.0.0", port=8000, log_level="info")
    except Exception as exc:
        sys.stderr.write(f"Fatal error: {exc}\n")
        raise SystemExit(1) from exc


if __name__ == "__main__":
    main()
