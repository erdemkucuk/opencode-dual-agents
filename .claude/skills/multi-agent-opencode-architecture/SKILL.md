---
name: multi-agent-opencode-microservices
description: Build a multi-agent system using opencode where two containerized agents communicate over HTTP. Agent 1 delegates tasks to Agent 2 using the opencode-mcp bridge. Use when setting up inter-agent orchestration with opencode serve and Gemini as the LLM provider.
---

# Multi-Agent OpenCode Microservices

## Overview

Two containerized agents each run `opencode serve`, exposing a REST endpoint. Both agents use Google Gemini as the LLM provider, configured via `GEMINI_API_KEY`. Agent 1 is equipped with the `opencode-mcp` tool, which allows it to delegate tasks to Agent 2 over HTTP using the Model Context Protocol (MCP).

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
│   └── AGENTS.md
└── agent2-config/
    ├── opencode.json
    └── AGENTS.md
```

---

## 1. Dockerfile (Shared Base)

A single image is used for both agents. Volume mounts provide each agent's configuration at runtime.

```dockerfile
FROM node:20-slim

RUN npm install -g opencode-ai opencode-mcp && \
    apt-get update && apt-get install -y curl jq procps iputils-ping bash git net-tools --no-install-recommends && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /agent
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
      - ./agent1-config:/agent
    ports:
      - "4097:4096"
    environment:
      - GEMINI_API_KEY=${GEMINI_API_KEY}
    networks:
      - agents

  agent2:
    build: .
    volumes:
      - ./agent2-config:/agent
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

Agent 1 reaches Agent 2 at `http://agent2:4096` through the `opencode-mcp` bridge.

---

## 3. Provider Configuration

OpenCode uses `{env:VARIABLE_NAME}` syntax for environment variable substitution inside `opencode.json` (not shell-style `${VAR}`).

**`./agent1-config/opencode.json`**:

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
  "model": "google/gemini-3-flash-preview",
  "mcp": {
    "agent2": {
      "type": "local",
      "enabled": true,
      "command": ["opencode-mcp"],
      "environment": {
        "OPENCODE_BASE_URL": "http://agent2:4096"
      }
    }
  }
}
```

**`./agent2-config/opencode.json`**:

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
  "model": "google/gemini-3-flash-preview"
}
```

Available Gemini models in opencode use the `google/` prefix, e.g.:

| Model string | Notes |
|---|---|
| `google/gemini-3-flash-preview` | Latest preview, fast and capable |
| `google/gemini-2.5-pro` | Best reasoning, higher cost |
| `google/gemini-2.0-flash` | Stable, widely available |

Run `/models` inside the TUI to see the full list available under your key.

---

## 4. How Delegation Works (opencode-mcp)

Instead of a custom script, Agent 1 uses `opencode-mcp` configured as a local MCP tool. This tool exposes the ability to interact with another OpenCode agent's sessions as tools.

When Agent 1 needs to delegate to Agent 2, it will automatically see Agent 2's capabilities (if configured as tools) or can use the `opencode-mcp` bridge to send messages.

### Verification with curl

You can test the delegation by sending a message to Agent 1 that requires it to talk to Agent 2:

```bash
SESSION=$(curl -s -X POST http://localhost:4097/session | jq -r '.id')
curl -s -X POST "http://localhost:4097/session/$SESSION/message" \
  -H "Content-Type: application/json" \
  -d '{"parts":[{"type":"text","text":"Ask Agent 2 what its name is."}]}' \
  | jq -r '.parts[] | select(.type=="text") | .text'
```
