---
name: opencode-inter-agent
description: >
  Teach an agent how to communicate with another opencode agent using the five
  scripts: opencode_health, opencode_ask, opencode_run, opencode_run_final,
  and opencode_status. Use this skill whenever an agent needs to delegate a
  task, check agent availability, or retrieve results from a peer opencode agent.
tools: Bash
---

# Inter-Agent Communication via opencode Scripts

To communicate with a peer opencode agent, run the scripts in `scripts/`.
Each script takes the target agent's base URL as its first argument and
speaks directly to the agent's HTTP API.

## Environment Variables

| Variable | Required | Description |
|---|---|---|
| `$TARGET` | **mandatory** | Base URL of the target opencode agent (e.g. `http://localhost:4098`) |
| `$PROMPT` | **mandatory** | The instruction or question to send to the peer agent |
| `$DIRECTORY` | optional | Working directory path for the session context on the peer agent |
| `$TIMEOUT_MS` | optional | Max milliseconds to wait for async task completion (default: `20000`) |

---

## Scripts

### `opencode_health`

Check whether a peer agent is up and accepting requests.

```bash
bash scripts/opencode_health.sh $TARGET
```

Returns the agent's health status as JSON.

---

### `opencode_ask`

Send a one-shot prompt and get the response immediately.
Use for short queries where you need an answer right away.

```bash
bash scripts/opencode_ask.sh $TARGET "$PROMPT" "$DIRECTORY"
```

Returns the full response JSON.

---

### `opencode_run`

Delegate a task and receive the complete message history once done.
Use when you want to inspect all intermediate steps (tool calls, reasoning, etc.).

```bash
bash scripts/opencode_run.sh $TARGET "$PROMPT" "$DIRECTORY" "$TIMEOUT_MS"
```

Returns a JSON array of all messages produced during the session.

---

### `opencode_run_final`

Delegate a task and receive only the last message once done.
Use when you only care about the final answer, not intermediate steps.

```bash
bash scripts/opencode_run_final.sh $TARGET "$PROMPT" "$DIRECTORY" "$TIMEOUT_MS"
```

Returns JSON of the last message produced during the session.

---

### `opencode_status`

Get a combined snapshot: health, active session count, and available providers.
Use to understand what the peer agent is doing before deciding how to delegate.

```bash
bash scripts/opencode_status.sh $TARGET
```

Returns `{ health, session_count, providers }` as JSON.

---

## Decision Guide

| Situation | Script |
|---|---|
| Is the peer agent alive? | `opencode_health` |
| Quick question, need answer now | `opencode_ask` |
| Complex task, need full trace | `opencode_run` |
| Complex task, only need final answer | `opencode_run_final` |
| How busy / what can the peer do? | `opencode_status` |

---

## Workflow Pattern: Safe Delegation

Always check health before delegating a critical task:

```bash
bash scripts/opencode_health.sh "$TARGET"
bash scripts/opencode_run_final.sh "$TARGET" "$PROMPT"
```

For fire-and-observe workflows:

```bash
bash scripts/opencode_status.sh "$TARGET"
bash scripts/opencode_run.sh "$TARGET" "$PROMPT"
# parse the returned JSON array for tool calls and intermediate results
```

---

## Examples

```bash
TARGET=http://localhost:4098
PROMPT="What is your name?"

bash scripts/opencode_health.sh "$TARGET"
bash scripts/opencode_ask.sh "$TARGET" "$PROMPT"
bash scripts/opencode_run_final.sh "$TARGET" "List the files in /tmp"
bash scripts/opencode_status.sh "$TARGET"
```
