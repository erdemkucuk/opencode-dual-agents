import os
import httpx
import asyncio
import json
import re
from typing import Any, Dict, List, Optional
from mcp.server.fastmcp import FastMCP
from dotenv import load_dotenv

load_dotenv()

OPENCODE_BASE = os.getenv("OPENCODE_BASE_URL", "http://localhost:4096")
MCP_PORT = os.getenv("MCP_PORT")
if MCP_PORT:
    MCP_PORT = int(MCP_PORT)

mcp = FastMCP("agent2-opencode-bridge")

def sanitize_name(raw: str) -> str:
    s1 = re.sub('(.)([A-Z][a-z]+)', r'\1_\2', raw)
    s2 = re.sub('([a-z0-9])([A-Z])', r'\1_\2', s1).lower()
    return re.sub(r'[^a-z0-9_]', '_', s2).strip('_')

async def call_opencode(
    method: str,
    path: str,
    path_params: Dict[str, Any] = None,
    query_params: Dict[str, Any] = None,
    body: Any = None
) -> Any:
    resolved_path = path
    if path_params:
        for key, value in path_params.items():
            resolved_path = resolved_path.replace(f"{{{key}}}", str(value))
    
    url = f"{OPENCODE_BASE}{resolved_path}"
    
    async with httpx.AsyncClient(timeout=30.0) as client:
        try:
            response = await client.request(
                method=method.upper(),
                url=url,
                params=query_params,
                json=body
            )
            try:
                return response.json()
            except:
                return response.text
        except Exception as e:
            return f"Error calling opencode: {str(e)}"

async def fetch_spec() -> Dict[str, Any]:
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
    paths = spec.get("paths", {})
    for path, methods in paths.items():
        for http_method, op in methods.items():
            operation_id = op.get("operationId")
            if not operation_id:
                continue
            
            tool_name = sanitize_name(operation_id)
            summary = op.get("summary") or op.get("description") or f"{http_method.upper()} {path}"
            description = summary[:500]
            
            params = op.get("parameters", [])
            path_params_spec = [p for p in params if p.get("in") == "path"]
            query_params_spec = [p for p in params if p.get("in") == "query"]
            has_body = http_method.lower() not in ["get", "delete"] and "requestBody" in op

            def make_handler(m, p, pps, qps, hb):
                async def handler(**kwargs):
                    path_vals = {}
                    query_vals = {}
                    body_val = None
                    for spec_p in pps:
                        name = spec_p["name"]
                        if name in kwargs: path_vals[name] = kwargs[name]
                    for spec_p in qps:
                        name = spec_p["name"]
                        if name in kwargs: query_vals[name] = kwargs[name]
                    if hb and "body" in kwargs: body_val = kwargs["body"]
                    
                    result = await call_opencode(m, p, path_vals, query_vals, body_val)
                    if isinstance(result, (dict, list)):
                        return json.dumps(result, indent=2)
                    return str(result)
                return handler

            handler = make_handler(http_method, path, path_params_spec, query_params_spec, has_body)
            mcp.tool(name=tool_name, description=description)(handler)

# High-level workflow tools
@mcp.tool()
async def opencode_health() -> str:
    """Check if the opencode server is healthy."""
    result = await call_opencode("get", "/global/health")
    return json.dumps(result, indent=2)

@mcp.tool()
async def opencode_ask(prompt: str, directory: Optional[str] = None) -> str:
    """Send a one-shot prompt to opencode and return the response."""
    q = {}
    if directory: q["directory"] = directory
    session = await call_opencode("post", "/session", query_params=q)
    if isinstance(session, str) or "id" not in session: return f"Failed to create session: {session}"
    session_id = session["id"]
    response = await call_opencode("post", f"/session/{session_id}/message", query_params=q, body={"parts": [{"type": "text", "text": prompt}]})
    return json.dumps(response, indent=2)

@mcp.tool()
async def opencode_run(prompt: str, directory: Optional[str] = None, timeout_ms: int = 20000) -> str:
    """Run a task asynchronously and poll for completion."""
    q = {}
    if directory: q["directory"] = directory
    session = await call_opencode("post", "/session", query_params=q)
    if isinstance(session, str) or "id" not in session: return f"Failed to create session: {session}"
    session_id = session["id"]
    await call_opencode("post", f"/session/{session_id}/prompt_async", query_params=q, body={"parts": [{"type": "text", "text": prompt}]})
    deadline = asyncio.get_event_loop().time() + (timeout_ms / 1000.0)
    while asyncio.get_event_loop().time() < deadline:
        await asyncio.sleep(2)
        status = await call_opencode("get", "/session/status")
        if isinstance(status, dict) and session_id in status:
            if status[session_id].get("running") is not True: break
        else: break
    messages = await call_opencode("get", f"/session/{session_id}/message", query_params=q)
    return json.dumps(messages, indent=2)

@mcp.tool()
async def opencode_status() -> str:
    """Get opencode server health, session count, and provider list."""
    health = await call_opencode("get", "/global/health")
    sessions = await call_opencode("get", "/session")
    providers = await call_opencode("get", "/provider")
    session_count = len(sessions) if isinstance(sessions, list) else 0
    return json.dumps({"health": health, "session_count": session_count, "providers": providers}, indent=2)

@mcp.tool()
async def opencode_context(directory: Optional[str] = None) -> str:
    """Get current project context: path, VCS info, and config."""
    q = {}
    if directory: q["directory"] = directory
    path = await call_opencode("get", "/path", query_params=q)
    vcs = await call_opencode("get", "/vcs", query_params=q)
    config = await call_opencode("get", "/config", query_params=q)
    return json.dumps({"path": path, "vcs": vcs, "config": config}, indent=2)

def main():
    try:
        # We need a loop to fetch the spec
        loop = asyncio.new_event_loop()
        spec = loop.run_until_complete(fetch_spec())
        loop.close()
        
        register_dynamic_tools(spec)
        
        if MCP_PORT:
            mcp.run(transport="sse", port=MCP_PORT, host="0.0.0.0")
        else:
            mcp.run(transport="stdio")
    except Exception as e:
        print(f"Fatal error: {e}")
        exit(1)

if __name__ == "__main__":
    main()
