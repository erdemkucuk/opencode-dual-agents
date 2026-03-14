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
READY_TIMEOUT = 30  # seconds to wait for containers to be ready
POLL_INTERVAL = 2


def _compose(args: list[str], check: bool = True) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["docker", "compose", *args],
        check=check,
        capture_output=True,
        text=True,
    )


def _wait_for_agent(base_url: str, name: str, timeout: int = READY_TIMEOUT) -> None:
    deadline = time.time() + timeout
    last_err = None
    while time.time() < deadline:
        try:
            r = httpx.get(f"{base_url}/doc", timeout=5)
            if r.status_code == 200:
                return
        except Exception as e:
            last_err = e
        time.sleep(POLL_INTERVAL)
    raise TimeoutError(f"{name} not ready after {timeout}s. Last error: {last_err}")


@pytest.fixture(scope="session")
def agents(request):
    """Bring up both agent containers (with --build), yield, then tear down.
    Pass --no-rebuild to pytest via -k or use the `agents_no_rebuild` fixture
    to skip rebuilding.
    """
    rebuild = not request.config.getoption("--no-rebuild", default=False)
    up_args = ["up", "--build", "-d"] if rebuild else ["up", "-d"]

    _compose(["down", "--remove-orphans"])
    _compose(up_args)

    try:
        _wait_for_agent(AGENT1_BASE, "Agent 1")
        _wait_for_agent(AGENT2_BASE, "Agent 2")
        yield
    finally:
        _compose(["down", "--remove-orphans"])


def pytest_addoption(parser):
    parser.addoption(
        "--no-rebuild",
        action="store_true",
        default=False,
        help="Skip docker compose build (use cached images)",
    )
