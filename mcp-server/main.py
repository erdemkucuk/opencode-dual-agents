import os
import httpx
import asyncio
import json
import re
from typing import Any, Dict, Optional
from mcp.server.fastmcp import FastMCP
from dotenv import load_dotenv

# Load environment variables from .env (e.g. OPENCODE_BASE_URL, MCP_PORT)
load_dotenv()

# Base URL for Agent 2's opencode REST API.
# In Docker, this is overridden to http://agent2:4096 via the environment.
OPENCODE_BASE = os.getenv("OPENCODE_BASE_URL", "http://localhost:4096")

# If MCP_PORT is set, the server runs as an HTTP/SSE server on that port.
# If not set, it runs as a stdio subprocess (used by Agent 1).
MCP_PORT = os.getenv("MCP_PORT")
if MCP_PORT:
    MCP_PORT = int(MCP_PORT)

# Create the FastMCP server instance — the entry point for all tool registrations.
mcp = FastMCP("agent2-opencode-bridge")


def sanitize_name(raw: str) -> str:
    """Convert a camelCase/PascalCase OpenAPI operationId into a valid snake_case tool name.

    Example: "getSessionMessage" → "get_session_message"
    Also replaces any remaining non-alphanumeric/underscore characters with '_'.
    """
    s1 = re.sub("(.)([A-Z][a-z]+)", r"\1_\2", raw)
    s2 = re.sub("([a-z0-9])([A-Z])", r"\1_\2", s1).lower()
    return re.sub(r"[^a-z0-9_]", "_", s2).strip("_")


async def call_opencode(
    method: str,
    path: str,
    path_params: Dict[str, Any] = None,
    query_params: Dict[str, Any] = None,
    body: Any = None,
) -> Any:
    """Make an HTTP request to Agent 2's opencode REST API.

    - Substitutes path template variables, e.g. /session/{sessionId} → /session/abc123
    - Sends optional query params and a JSON body.
    - Returns parsed JSON if possible, otherwise raw text.
    """
    # Replace {placeholder} segments in the path with actual values
    resolved_path = path
    if path_params:
        for key, value in path_params.items():
            resolved_path = resolved_path.replace(f"{{{key}}}", str(value))

    url = f"{OPENCODE_BASE}{resolved_path}"

    async with httpx.AsyncClient(timeout=30.0) as client:
        try:
            response = await client.request(
                method=method.upper(), url=url, params=query_params, json=body
            )
            try:
                return response.json()  # Prefer structured JSON
            except Exception:
                return response.text  # Fall back to plain text
        except Exception as e:
            return f"Error calling opencode: {str(e)}"


async def fetch_spec() -> Dict[str, Any]:
    """Fetch Agent 2's OpenAPI spec from GET /doc with retry logic.

    Retries up to 15 times with 2-second delays (up to 30s total) to handle
    the case where Agent 2's opencode server is still starting up.
    Raises an exception if the server never becomes reachable.
    """
    print(f"Connecting to opencode at {OPENCODE_BASE}...")
    for attempt in range(15):
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                response = await client.get(f"{OPENCODE_BASE}/doc")
                if response.status_code == 200:
                    print("OpenAPI spec loaded.")
                    return response.json()
        except Exception:
            pass
        await asyncio.sleep(2)
        if attempt % 3 == 0:
            print(f"Waiting for opencode (attempt {attempt + 1})...")
    raise Exception("opencode never became healthy after 30 s")


def register_dynamic_tools(spec: Dict[str, Any]):
    """Auto-generate one MCP tool per endpoint found in the OpenAPI spec.

    For each path+method combination in the spec:
    - Derives a snake_case tool name from the operationId
    - Separates path params, query params, and request body
    - Registers an async handler with FastMCP that routes kwargs to call_opencode()

    Note: make_handler() is a closure factory to correctly capture the loop
    variables (m, p, pps, qps, hb) — a common Python gotcha with closures in loops.
    """
    paths = spec.get("paths", {})
    for path, methods in paths.items():
        for http_method, op in methods.items():
            operation_id = op.get("operationId")
            if not operation_id:
                continue  # Skip endpoints with no operationId

            tool_name = sanitize_name(operation_id)
            summary = (
                op.get("summary")
                or op.get("description")
                or f"{http_method.upper()} {path}"
            )
            description = summary[:500]  # MCP tool descriptions have a length limit

            params = op.get("parameters", [])
            path_params_spec = [p for p in params if p.get("in") == "path"]
            query_params_spec = [p for p in params if p.get("in") == "query"]
            # Only non-GET/DELETE endpoints with a requestBody schema carry a body
            has_body = (
                http_method.lower() not in ["get", "delete"] and "requestBody" in op
            )

            def make_handler(m, p, pps, qps, hb):
                async def handler(**kwargs):
                    # Route each kwarg to the correct parameter slot
                    path_vals = {}
                    query_vals = {}
                    body_val = None
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
                    # Always return a string — MCP tools must return serializable text
                    if isinstance(result, (dict, list)):
                        return json.dumps(result, indent=2)
                    return str(result)

                return handler

            handler = make_handler(
                http_method, path, path_params_spec, query_params_spec, has_body
            )
            # Register the generated handler as a named MCP tool
            mcp.tool(name=tool_name, description=description)(handler)


# ──────────────────────────────────────────────────────────────
# Hand-written high-level workflow tools (5 ergonomic composites)
# These are more convenient than the raw auto-generated endpoints.
# ──────────────────────────────────────────────────────────────


@mcp.tool()
async def opencode_health() -> str:
    """Check if the opencode server is healthy."""
    result = await call_opencode("get", "/global/health")
    return json.dumps(result, indent=2)


@mcp.tool()
async def opencode_ask(prompt: str, directory: Optional[str] = None) -> str:
    """Send a one-shot prompt to opencode and return the response.

    Creates a new session, sends the prompt synchronously, and returns
    the raw response from the session message endpoint.
    """
    q = {}
    if directory:
        q["directory"] = directory
    # Create a fresh session for this prompt
    session = await call_opencode("post", "/session", query_params=q)
    if isinstance(session, str) or "id" not in session:
        return f"Failed to create session: {session}"
    session_id = session["id"]
    # Send the prompt as a text message part
    response = await call_opencode(
        "post",
        f"/session/{session_id}/message",
        query_params=q,
        body={"parts": [{"type": "text", "text": prompt}]},
    )
    return json.dumps(response, indent=2)


@mcp.tool()
async def opencode_run(
    prompt: str, directory: Optional[str] = None, timeout_ms: int = 20000
) -> str:
    """Run a task asynchronously and poll for completion.

    Fires the prompt via the async endpoint, then polls GET /session/status
    every 2 seconds until the session is no longer running or the timeout expires.
    Returns all accumulated session messages.
    """
    q = {}
    if directory:
        q["directory"] = directory
    # Create a fresh session
    session = await call_opencode("post", "/session", query_params=q)
    if isinstance(session, str) or "id" not in session:
        return f"Failed to create session: {session}"
    session_id = session["id"]
    # Fire the prompt asynchronously (non-blocking)
    await call_opencode(
        "post",
        f"/session/{session_id}/prompt_async",
        query_params=q,
        body={"parts": [{"type": "text", "text": prompt}]},
    )
    # Poll until the session finishes or the deadline is reached
    deadline = asyncio.get_event_loop().time() + (timeout_ms / 1000.0)
    while asyncio.get_event_loop().time() < deadline:
        await asyncio.sleep(2)
        status = await call_opencode("get", "/session/status")
        if isinstance(status, dict) and session_id in status:
            if status[session_id].get("running") is not True:
                break  # Task finished
        else:
            break
    # Fetch and return all messages produced during this session
    messages = await call_opencode(
        "get", f"/session/{session_id}/message", query_params=q
    )
    return json.dumps(messages, indent=2)


@mcp.tool()
async def opencode_status() -> str:
    """Get opencode server health, session count, and provider list.

    Bundles three separate API calls into one convenient snapshot.
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
async def opencode_context(directory: Optional[str] = None) -> str:
    """Get current project context: path, VCS info, and config."""
    q = {}
    if directory:
        q["directory"] = directory
    path = await call_opencode("get", "/path", query_params=q)
    vcs = await call_opencode("get", "/vcs", query_params=q)
    config = await call_opencode("get", "/config", query_params=q)
    return json.dumps({"path": path, "vcs": vcs, "config": config}, indent=2)


def main():
    """Entry point: fetch spec, register tools, then start the MCP server.

    Uses a dedicated event loop to synchronously wait for the OpenAPI spec
    before any async MCP machinery starts.

    Transport mode is selected by the MCP_PORT environment variable:
    - Set  → SSE/HTTP server on that port (used by Agent 2's sidecar, exposed on host port 4099)
    - Unset → stdio subprocess (used by Agent 1 as a local MCP child process)
    """
    try:
        # Synchronously fetch the OpenAPI spec before entering async MCP runtime
        loop = asyncio.new_event_loop()
        spec = loop.run_until_complete(fetch_spec())
        loop.close()

        # Dynamically register ~104 tools from the fetched spec
        register_dynamic_tools(spec)

        if MCP_PORT:
            # SSE mode: accessible over HTTP (e.g. curl, Agent 1 over network)
            mcp.run(transport="sse", port=MCP_PORT, host="0.0.0.0")
        else:
            # stdio mode: Agent 1 communicates via stdin/stdout pipes
            mcp.run(transport="stdio")
    except Exception as e:
        print(f"Fatal error: {e}")
        exit(1)


if __name__ == "__main__":
    main()
