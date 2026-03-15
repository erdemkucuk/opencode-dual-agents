"""Pytest fixtures for integration testing the dual-agent opencode setup.

Session-scoped fixture spins up both containers once per test run,
waits for both agents to be ready, then tears everything down afterward.
"""

import subprocess
import time

import httpx
import pytest

AGENT1_BASE = "http://localhost:4097"
AGENT2_BASE = "http://localhost:4098"
AGENT1_MCP_BASE = "http://localhost:4100"
AGENT2_MCP_BASE = "http://localhost:4099"
READY_TIMEOUT = 30  # seconds to wait for opencode endpoints
MCP_READY_TIMEOUT = 10  # seconds to wait for MCP sidecar (starts after opencode)
POLL_INTERVAL = 2


def _compose(args: list[str], check: bool = True) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["docker", "compose", *args],
        check=check,
        capture_output=True,
        text=True,
    )


def _wait_for_url(url: str, name: str, timeout: int = READY_TIMEOUT) -> None:
    """Poll *url* until it responds with a non-5xx status or *timeout* expires.

    Uses streaming so SSE endpoints (which never close the body) don't block.
    """
    deadline = time.time() + timeout
    last_err = None
    while time.time() < deadline:
        try:
            with httpx.stream("GET", url, timeout=5) as r:
                if r.status_code < 500:
                    return
        except Exception as e:
            last_err = e
        time.sleep(POLL_INTERVAL)
    raise TimeoutError(f"{name} not ready after {timeout}s. Last error: {last_err}")


def _wait_for_agent(base_url: str, name: str, timeout: int = READY_TIMEOUT) -> None:
    _wait_for_url(f"{base_url}/doc", name, timeout)


@pytest.fixture(scope="session")
def agents():
    """Bring up both agent containers (with --build), yield, then tear down."""
    _compose(["down", "--remove-orphans"])
    _compose(["up", "--build", "-d"])

    try:
        # First wait for both opencode HTTP endpoints to be ready.
        _wait_for_agent(AGENT1_BASE, "Agent 1")
        _wait_for_agent(AGENT2_BASE, "Agent 2")
        # MCP sidecars start only after opencode is healthy, so a shorter
        # timeout is sufficient once the main endpoints are up.
        _wait_for_url(f"{AGENT1_MCP_BASE}/sse", "Agent 1 MCP", MCP_READY_TIMEOUT)
        _wait_for_url(f"{AGENT2_MCP_BASE}/sse", "Agent 2 MCP", MCP_READY_TIMEOUT)
        yield
    finally:
        _compose(["down", "--remove-orphans"])
