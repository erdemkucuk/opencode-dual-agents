---
name: multi-agent-opencode-microservices
description: Build a multi-agent system using opencode where two containerized agents communicate over HTTP. Agent 1 delegates tasks to Agent 2 using a skill and a Python script. Use when setting up inter-agent orchestration with opencode serve and Gemini as the LLM provider.
allowed-tools:
  - bash
  - read
  - write
---

# Multi-Agent OpenCode Microservices

## Overview

Two containerized agents each run `opencode serve`, exposing a REST endpoint. Both agents use Google Gemini as the LLM provider, configured via `GEMINI_API_KEY`. Agent 1 is equipped with a skill that delegates tasks to Agent 2 over HTTP.

**Important:** `POST /session/{id}/message` is **synchronous** — it blocks until inference completes and returns the full assistant response in the response body. Do **not** attempt to poll the SSE event stream (`GET /session/{id}/event`); that path is caught by opencode's SPA catch-all router and returns HTML, not events.

---

## Directory Layout

```
.
├── Dockerfile
├── docker-compose.yml
├── .env
├── agent1-config/
│   ├── opencode.json
│   ├── .opencode/
│   │   └── skills/
│   │       └── delegate-to-agent2/
│   │           └── SKILL.md
│   └── app/
│       └── scripts/
│           └── call_agent2.py
└── agent2-config/
    ├── opencode.json
    └── .opencode/
        └── (agent2-specific config, AGENTS.md, instructions, etc.)
```

---

## 1. Dockerfile (Shared Base)

A single image is used for both agents. Volume mounts provide each agent's configuration at runtime.

```dockerfile
FROM node:20-slim

RUN npm install -g opencode-ai && \
    apt-get update && apt-get install -y python3 python3-pip curl --no-install-recommends && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /app
EXPOSE 4096

# --hostname 0.0.0.0 is required in Docker.
# The default (127.0.0.1) binds only to the container loopback
# and is unreachable from other containers on the network.
CMD ["opencode", "serve", "--hostname", "0.0.0.0", "--port", "4096"]
```

---

## 2. Docker Compose

```yaml
networks:
  agents:
    driver: bridge

services:
  agent1:
    build: .
    volumes:
      - ./agent1-config:/app
    ports:
      - "4097:4096"
    environment:
      - GEMINI_API_KEY=${GEMINI_API_KEY}
    networks:
      - agents

  agent2:
    build: .
    volumes:
      - ./agent2-config:/app
    ports:
      - "4098:4096"
    environment:
      - GEMINI_API_KEY=${GEMINI_API_KEY}
    networks:
      - agents
```

Provide credentials in a `.env` file alongside `docker-compose.yml`:

```env
GEMINI_API_KEY=your-key-here
```

Agent 1 reaches Agent 2 at `http://agent2:4096`.

---

## 3. Provider Configuration

OpenCode uses `{env:VARIABLE_NAME}` syntax for environment variable substitution inside `opencode.json` (not shell-style `${VAR}`).

**`./agent1-config/opencode.json`** (and similarly for `agent2-config/opencode.json`):

```json
{
  "$schema": "https://opencode.ai/config.json",
  "provider": {
    "google": {
      "options": {
        "apiKey": "{env:GEMINI_API_KEY}"
      }
    }
  },
  "model": "google/gemini-2.5-pro"
}
```

Available Gemini models in opencode use the `google/` prefix, e.g.:

| Model string | Notes |
|---|---|
| `google/gemini-2.5-pro` | Best reasoning, higher cost |
| `google/gemini-2.5-flash` | Fast and cost-efficient |
| `google/gemini-2.0-flash` | Stable, widely available |

Run `/models` inside the TUI to see the full list available under your key.

---

## 4. Agent 1 Skill

Skills are **directories** whose name must exactly match the `name` field in the frontmatter (lowercase, hyphens only). Place this file at:

```
./agent1-config/.opencode/skills/delegate-to-agent2/SKILL.md
```

```markdown
---
name: delegate-to-agent2
description: Delegate tasks to Agent 2 for specialized processing or data retrieval. Use when the task requires Agent 2's specific capabilities.
allowed-tools:
  - bash
---

# Delegate to Agent 2

When you need Agent 2 to process something, call the cross-agent script with the prompt as the argument:

```bash
python3 /app/scripts/call_agent2.py "<prompt>"
```

Print the script's output as your response.
```

---

## 5. Inter-Agent Communication Script

### How the opencode message API works

`POST /session/{id}/message` is **synchronous** — it blocks until inference completes and returns the full assistant response in the response body. The correct flow is:

```
POST /session                →  creates session, returns { id }
POST /session/{id}/message   →  sends prompt, blocks, returns assistant response
```

> **Do not use `GET /session/{id}/event`** — that path is caught by opencode's SPA catch-all router and returns the web UI HTML instead of an SSE stream.

### Script

Save at `./agent1-config/app/scripts/call_agent2.py`:

```python
import sys
import json
import urllib.request

import os

BASE_URL = os.getenv("AGENT2_URL", "http://agent2:4096")


def request(method, path, body=None):
    data = json.dumps(body).encode("utf-8") if body is not None else None
    headers = {"Content-Type": "application/json"} if data else {}
    req = urllib.request.Request(
        f"{BASE_URL}{path}", data=data, headers=headers, method=method
    )
    with urllib.request.urlopen(req) as res:
        raw = res.read().decode("utf-8")
        return json.loads(raw) if raw.strip() else None


def create_session():
    result = request("POST", "/session")
    return result["id"]


def send_message(session_id, prompt):
    response = request(
        "POST",
        f"/session/{session_id}/message",
        body={"parts": [{"type": "text", "text": prompt}]},
    )
    for part in (response or {}).get("parts", []):
        if part.get("type") == "text":
            return part["text"]
    return ""


def ask_agent2(prompt):
    session_id = create_session()
    reply = send_message(session_id, prompt)
    print(reply)


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: call_agent2.py '<prompt>'", file=sys.stderr)
        sys.exit(1)
    ask_agent2(sys.argv[1])
```

---

## 6. Alternative: MCP Architecture

If Agent 2's role is executing specialized tools rather than independent reasoning, expose those tools as an MCP server. OpenCode natively connects to MCP servers, eliminating the session lifecycle and SSE handling entirely.

Run an MCP-compatible server on Agent 2 (e.g. using FastMCP) and configure Agent 1 to attach to it using `"type": "remote"`:

```json
{
  "$schema": "https://opencode.ai/config.json",
  "provider": {
    "google": {
      "options": {
        "apiKey": "{env:GEMINI_API_KEY}"
      }
    }
  },
  "model": "google/gemini-2.5-pro",
  "mcp": {
    "agent2-tools": {
      "type": "remote",
      "url": "http://agent2:8080/mcp",
      "enabled": true
    }
  }
}
```

Agent 1 then calls Agent 2's tools natively through OpenCode's built-in MCP support — no Python script or custom REST client needed.
