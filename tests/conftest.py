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
AGENT1_MCP = "http://localhost:4100"
AGENT2_MCP = "http://localhost:4099"
READY_TIMEOUT = 30  # seconds to wait for containers to be ready
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


@pytest.fixture(scope="session")
def agents(request):
    """Bring up both agent containers, yield, then tear down."""
    _compose(["down", "--remove-orphans"])
    _compose(["up", "-d"])

    try:
        _wait_for_url(f"{AGENT1_BASE}/doc", "Agent 1 opencode")
        _wait_for_url(f"{AGENT2_BASE}/doc", "Agent 2 opencode")
        _wait_for_url(f"{AGENT1_MCP}/sse", "Agent 1 MCP")
        _wait_for_url(f"{AGENT2_MCP}/sse", "Agent 2 MCP")
        yield
    finally:
        _compose(["down", "--remove-orphans"])


def pytest_addoption(parser):
    parser.addoption(
        "--no-rebuild",
        action="store_true",
        default=False,
        help="Ignored; kept for backwards compatibility. Rebuild is handled by make.",
    )
