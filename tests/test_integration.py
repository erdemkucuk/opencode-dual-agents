"""
Integration smoke tests for the dual-agent opencode setup.

Replicates what scripts/curl-test.sh does, but as assertable pytest tests.
"""

import httpx
import pytest

AGENT1_BASE = "http://localhost:4097"
AGENT2_BASE = "http://localhost:4098"
DEFAULT_QUESTION = "Ask Agent 2 what its name is, then tell me the answer."


def _send_message_to(base_url: str, question: str) -> str:
    """Create a session on the given agent and send a message. Returns the text response."""
    with httpx.Client(timeout=60) as client:
        session_id = client.post(f"{base_url}/session").raise_for_status().json()["id"]
        payload = {"parts": [{"type": "text", "text": question}]}
        data = client.post(
            f"{base_url}/session/{session_id}/message", json=payload
        ).raise_for_status().json()

    texts = [p["text"] for p in data.get("parts", []) if p.get("type") == "text"]
    return "\n".join(texts)


def _send_message(question: str = DEFAULT_QUESTION) -> str:
    """Create a session on Agent 1 and send a message. Returns the text response."""
    return _send_message_to(AGENT1_BASE, question)


class TestHealth:
    """Scenario 1 (partial): verify both agents are reachable via /doc."""

    def test_agent1_openapi_doc(self, agents):
        """Confirms the opencode HTTP server on Agent 1 (port 4097) is up and serving
        its OpenAPI spec. Does not test any AI behaviour — pure infrastructure check."""
        r = httpx.get(f"{AGENT1_BASE}/doc", timeout=10)
        assert r.status_code == 200, f"Agent 1 /doc returned {r.status_code}"

    def test_agent2_openapi_doc(self, agents):
        """Same check for Agent 2 (port 4098)."""
        r = httpx.get(f"{AGENT2_BASE}/doc", timeout=10)
        assert r.status_code == 200, f"Agent 2 /doc returned {r.status_code}"


class TestSessionCreation:
    """Scenario 1: POST /session on each agent returns a JSON object with an 'id' field."""

    def test_agent1_creates_session(self, agents):
        """POSTs to /session on Agent 1 and verifies the response contains an 'id'.
        The id is required by subsequent /session/{id}/message calls."""
        r = httpx.post(f"{AGENT1_BASE}/session", timeout=10)
        assert r.status_code == 200
        assert "id" in r.json(), "Agent 1 session response missing 'id'"

    def test_agent2_creates_session(self, agents):
        """Same session-creation check directly against Agent 2 (port 4098),
        confirming its REST API is independently functional."""
        r = httpx.post(f"{AGENT2_BASE}/session", timeout=10)
        assert r.status_code == 200
        assert "id" in r.json(), "Agent 2 session response missing 'id'"


class TestAgent1Isolation:
    """Scenario 2: Agent 1 (Luigi) responds in isolation and identifies itself."""

    def test_agent1_responds_to_message(self, agents):
        """Sends a simple prompt directly to Agent 1 and checks the reply is non-empty.
        Validates the full request pipeline: session creation → message → LLM → response."""
        response = _send_message_to(AGENT1_BASE, "Say hello.")
        assert response.strip(), "Agent 1 returned an empty response"

    def test_agent1_identifies_as_luigi(self, agents):
        """Asks Agent 1 for its name and asserts 'Luigi' appears in the reply.
        Verifies that agent1-config/AGENTS.md was loaded and the persona is active."""
        response = _send_message_to(AGENT1_BASE, "What is your name?")
        assert "Luigi" in response, (
            f"Expected 'Luigi' in Agent 1 response, got:\n{response}"
        )


class TestAgent2Isolation:
    """Scenario 3: Agent 2 (Mario) responds in isolation and identifies itself."""

    def test_agent2_responds_to_message(self, agents):
        """Sends a simple prompt directly to Agent 2 (port 4098) and checks for a
        non-empty reply, bypassing Agent 1 entirely."""
        response = _send_message_to(AGENT2_BASE, "Say hello.")
        assert response.strip(), "Agent 2 returned an empty response"

    def test_agent2_identifies_as_mario(self, agents):
        """Asks Agent 2 for its name and asserts 'Mario' appears in the reply.
        Verifies that agent2-config/AGENTS.md was loaded and the persona is active."""
        response = _send_message_to(AGENT2_BASE, "What is your name?")
        assert "Mario" in response, (
            f"Expected 'Mario' in Agent 2 response, got:\n{response}"
        )


class TestEndToEndDelegation:
    """Scenario 4: Agent 1 delegates to Agent 2 via the MCP tool."""

    def test_agent1_delegates_to_agent2(self, agents):
        """Instructs Agent 1 to ask Agent 2 for its name. Asserts 'Mario' appears in
        the final reply, which requires the full delegation chain to succeed:
        Agent 1 → opencode_ask MCP tool → Agent 2 REST API → 'Mario' → Agent 1 reply."""
        response = _send_message(DEFAULT_QUESTION)
        assert "Mario" in response, (
            f"Expected 'Mario' in response (Agent 2's name), got:\n{response}"
        )
