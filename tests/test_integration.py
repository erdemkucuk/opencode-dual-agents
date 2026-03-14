"""
Integration smoke tests for the dual-agent opencode setup.

Replicates what scripts/curl-test.sh does, but as assertable pytest tests.
"""

import httpx
import pytest

AGENT1_BASE = "http://localhost:4097"
AGENT2_BASE = "http://localhost:4098"
DEFAULT_QUESTION = "Ask Agent 2 what its name is, then tell me the answer."


def _send_message(question: str = DEFAULT_QUESTION) -> str:
    """Create a session on Agent 1 and send a message. Returns the text response."""
    with httpx.Client(timeout=15) as client:
        session_id = client.post(f"{AGENT1_BASE}/session").raise_for_status().json()["id"]
        payload = {"parts": [{"type": "text", "text": question}]}
        data = client.post(
            f"{AGENT1_BASE}/session/{session_id}/message", json=payload
        ).raise_for_status().json()

    texts = [p["text"] for p in data.get("parts", []) if p.get("type") == "text"]
    return "\n".join(texts)


class TestHealth:
    def test_agent1_openapi_doc(self, agents):
        r = httpx.get(f"{AGENT1_BASE}/doc", timeout=10)
        assert r.status_code == 200, f"Agent 1 /doc returned {r.status_code}"

    def test_agent2_openapi_doc(self, agents):
        r = httpx.get(f"{AGENT2_BASE}/doc", timeout=10)
        assert r.status_code == 200, f"Agent 2 /doc returned {r.status_code}"


class TestAgentCommunication:
    def test_agent1_creates_session(self, agents):
        r = httpx.post(f"{AGENT1_BASE}/session", timeout=10)
        assert r.status_code == 200
        assert "id" in r.json(), "Session response missing 'id'"

    def test_agent1_responds_to_message(self, agents):
        """Agent 1 should return a non-empty text response."""
        response = _send_message("Say hello.")
        assert response.strip(), "Agent 1 returned an empty response"

    def test_agent1_delegates_to_agent2(self, agents):
        """
        Ask Agent 1 (Luigi) to query Agent 2 (Mario) for its name.
        The response should mention Mario.
        """
        response = _send_message(DEFAULT_QUESTION)
        assert "Mario" in response, (
            f"Expected 'Mario' in response (Agent 2's name), got:\n{response}"
        )
