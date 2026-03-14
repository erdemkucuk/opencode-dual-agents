import { Server } from "@modelcontextprotocol/sdk/server/index.js";
import { StdioServerTransport } from "@modelcontextprotocol/sdk/server/stdio.js";
import { StreamableHTTPServerTransport } from "@modelcontextprotocol/sdk/server/streamableHttp.js";
import {
  CallToolRequestSchema,
  ListToolsRequestSchema,
  type Tool,
} from "@modelcontextprotocol/sdk/types.js";
import { createServer } from "http";
import { z } from "zod";

const OPENCODE_BASE = process.env.OPENCODE_BASE_URL ?? "http://localhost:4096";
const MCP_PORT = process.env.MCP_PORT ? parseInt(process.env.MCP_PORT, 10) : null;

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function log(...args: unknown[]): void {
  // Always write to stderr so stdout stays clean for MCP stdio protocol
  process.stderr.write(args.join(" ") + "\n");
}

async function callOpencode(
  method: string,
  path: string,
  pathParams: Record<string, string> = {},
  queryParams: Record<string, string> = {},
  body?: unknown,
): Promise<unknown> {
  let resolvedPath = path;
  for (const [key, value] of Object.entries(pathParams)) {
    resolvedPath = resolvedPath.replace(`{${key}}`, encodeURIComponent(value));
  }

  const url = new URL(OPENCODE_BASE + resolvedPath);
  for (const [key, value] of Object.entries(queryParams)) {
    if (value !== undefined && value !== "") url.searchParams.set(key, value);
  }

  const init: RequestInit = { method: method.toUpperCase() };
  if (body !== undefined) {
    init.body = JSON.stringify(body);
    init.headers = { "Content-Type": "application/json" };
  }

  const res = await fetch(url.toString(), init);
  const text = await res.text();
  try {
    return JSON.parse(text);
  } catch {
    return text;
  }
}

function sanitizeName(raw: string): string {
  return raw
    .replace(/([A-Z])/g, (m, c, i) => (i === 0 ? c : `_${c}`))
    .toLowerCase()
    .replace(/[^a-z0-9_]/g, "_")
    .replace(/__+/g, "_")
    .replace(/^_|_$/g, "");
}

// ---------------------------------------------------------------------------
// OpenAPI spec types
// ---------------------------------------------------------------------------

interface OpenAPIParam {
  name: string;
  in: "path" | "query" | "header" | "cookie";
  required?: boolean;
  schema?: { type?: string };
  description?: string;
}

interface OpenAPIOperation {
  operationId?: string;
  summary?: string;
  description?: string;
  parameters?: OpenAPIParam[];
  requestBody?: { content?: { "application/json"?: { schema?: unknown } } };
}

interface OpenAPISpec {
  paths?: Record<string, Record<string, OpenAPIOperation>>;
}

// ---------------------------------------------------------------------------
// Fetch opencode OpenAPI spec (with retry, max 20 s)
// ---------------------------------------------------------------------------

async function fetchSpec(): Promise<OpenAPISpec> {
  for (let attempt = 0; attempt < 10; attempt++) {
    try {
      const res = await fetch(`${OPENCODE_BASE}/doc`);
      if (res.ok) return (await res.json()) as OpenAPISpec;
    } catch {
      // not ready yet
    }
    await new Promise((r) => setTimeout(r, 2000));
    if (attempt % 3 === 0) log(`[mcp] Waiting for opencode (attempt ${attempt + 1})…`);
  }
  throw new Error("opencode never became healthy after 20 s");
}

// ---------------------------------------------------------------------------
// Build tool registry from OpenAPI spec
// ---------------------------------------------------------------------------

interface ToolEntry {
  tool: Tool;
  httpMethod: string;
  path: string;
  pathParams: OpenAPIParam[];
  queryParams: OpenAPIParam[];
  hasBody: boolean;
}

function buildTools(spec: OpenAPISpec): ToolEntry[] {
  const entries: ToolEntry[] = [];

  for (const [path, methods] of Object.entries(spec.paths ?? {})) {
    for (const [httpMethod, op] of Object.entries(methods)) {
      if (!op?.operationId) continue;

      const name = sanitizeName(op.operationId);
      const description = (op.summary ?? op.description ?? `${httpMethod.toUpperCase()} ${path}`).slice(0, 500);

      const params = op.parameters ?? [];
      const pathParams = params.filter((p) => p.in === "path");
      const queryParams = params.filter((p) => p.in === "query");
      const hasBody = httpMethod !== "get" && httpMethod !== "delete" && op.requestBody !== undefined;

      // Build JSON Schema for the tool input
      const properties: Record<string, unknown> = {};
      const required: string[] = [];

      for (const p of pathParams) {
        properties[p.name] = { type: "string", description: p.description ?? p.name };
        if (p.required !== false) required.push(p.name);
      }
      for (const p of queryParams) {
        properties[p.name] = { type: "string", description: p.description ?? p.name };
      }
      if (hasBody) {
        properties["body"] = { type: "object", description: "JSON request body" };
      }

      const tool: Tool = {
        name,
        description,
        inputSchema: {
          type: "object" as const,
          properties: properties as Record<string, { type: string; description: string }>,
          required: required.length > 0 ? required : undefined,
        },
      };

      entries.push({ tool, httpMethod, path, pathParams, queryParams, hasBody });
    }
  }

  return entries;
}

// ---------------------------------------------------------------------------
// High-level workflow tool definitions
// ---------------------------------------------------------------------------

function workflowTools(): ToolEntry[] {
  const makeEntry = (tool: Tool, handler: (args: Record<string, unknown>) => Promise<string>): ToolEntry => ({
    tool,
    httpMethod: "__workflow__",
    path: "__workflow__",
    pathParams: [],
    queryParams: [],
    hasBody: false,
    // Store handler on the entry for dispatch below
    ...(Object.assign({}, { _handler: handler })),
  }) as unknown as ToolEntry & { _handler: typeof handler };

  return [
    makeEntry(
      {
        name: "opencode_health",
        description: "Check if the opencode server is healthy.",
        inputSchema: { type: "object", properties: {} },
      },
      async () => JSON.stringify(await callOpencode("get", "/global/health"), null, 2),
    ),
    makeEntry(
      {
        name: "opencode_ask",
        description:
          "Send a one-shot prompt to opencode and return the response. Creates a session, sends the message synchronously, and returns the assistant reply.",
        inputSchema: {
          type: "object",
          properties: {
            prompt: { type: "string", description: "The prompt to send" },
            directory: { type: "string", description: "Working directory" },
          },
          required: ["prompt"],
        },
      },
      async ({ prompt, directory }) => {
        const q: Record<string, string> = {};
        if (directory) q["directory"] = String(directory);
        const session = (await callOpencode("post", "/session", {}, q)) as { id: string };
        const response = await callOpencode(
          "post",
          `/session/{id}/message`,
          { id: session.id },
          q,
          { parts: [{ type: "text", text: String(prompt) }] },
        );
        return JSON.stringify(response, null, 2);
      },
    ),
    makeEntry(
      {
        name: "opencode_run",
        description:
          "Run a task asynchronously: create session, fire async prompt, poll until idle (max 20 s), return messages.",
        inputSchema: {
          type: "object",
          properties: {
            prompt: { type: "string", description: "Task prompt" },
            directory: { type: "string", description: "Working directory" },
            timeout_ms: { type: "string", description: "Max wait ms (default 20000)" },
          },
          required: ["prompt"],
        },
      },
      async ({ prompt, directory, timeout_ms }) => {
        const q: Record<string, string> = {};
        if (directory) q["directory"] = String(directory);
        const timeout = parseInt(String(timeout_ms ?? "20000"), 10);
        const session = (await callOpencode("post", "/session", {}, q)) as { id: string };
        await callOpencode(
          "post",
          `/session/{id}/prompt_async`,
          { id: session.id },
          q,
          { parts: [{ type: "text", text: String(prompt) }] },
        );
        const deadline = Date.now() + timeout;
        while (Date.now() < deadline) {
          await new Promise((r) => setTimeout(r, 2000));
          const status = (await callOpencode("get", "/session/status")) as Record<string, Record<string, unknown>>;
          if (!status[session.id] || status[session.id]["running"] !== true) break;
        }
        const messages = await callOpencode("get", `/session/{id}/message`, { id: session.id }, q);
        return JSON.stringify(messages, null, 2);
      },
    ),
    makeEntry(
      {
        name: "opencode_status",
        description: "Get opencode server health, session count, and provider list.",
        inputSchema: { type: "object", properties: {} },
      },
      async () => {
        const [health, sessions, providers] = await Promise.all([
          callOpencode("get", "/global/health"),
          callOpencode("get", "/session"),
          callOpencode("get", "/provider"),
        ]);
        return JSON.stringify(
          { health, session_count: (sessions as unknown[]).length, providers },
          null,
          2,
        );
      },
    ),
    makeEntry(
      {
        name: "opencode_context",
        description: "Get current project context: path, VCS info, and config.",
        inputSchema: {
          type: "object",
          properties: { directory: { type: "string", description: "Working directory" } },
        },
      },
      async ({ directory }) => {
        const q: Record<string, string> = {};
        if (directory) q["directory"] = String(directory);
        const [path, vcs, config] = await Promise.all([
          callOpencode("get", "/path", {}, q),
          callOpencode("get", "/vcs", {}, q),
          callOpencode("get", "/config", {}, q),
        ]);
        return JSON.stringify({ path, vcs, config }, null, 2);
      },
    ),
  ] as unknown as ToolEntry[];
}

// ---------------------------------------------------------------------------
// Create and configure the MCP Server
// ---------------------------------------------------------------------------

function createMcpServer(entries: ToolEntry[]): Server {
  const server = new Server(
    { name: "agent2-opencode-bridge", version: "1.0.0" },
    { capabilities: { tools: {} } },
  );

  // Build a dispatch map: tool name → handler
  const dispatch = new Map<string, (args: Record<string, unknown>) => Promise<string>>();

  for (const entry of entries) {
    const e = entry as typeof entry & { _handler?: (args: Record<string, unknown>) => Promise<string> };
    if (e._handler) {
      dispatch.set(entry.tool.name, e._handler);
    } else {
      const { httpMethod, path, pathParams, queryParams, hasBody } = entry;
      dispatch.set(entry.tool.name, async (args) => {
        const pPath: Record<string, string> = {};
        const pQuery: Record<string, string> = {};
        let body: unknown;
        for (const p of pathParams) {
          if (args[p.name] !== undefined) pPath[p.name] = String(args[p.name]);
        }
        for (const p of queryParams) {
          if (args[p.name] !== undefined) pQuery[p.name] = String(args[p.name]);
        }
        if (hasBody && args["body"] !== undefined) body = args["body"];
        const result = await callOpencode(httpMethod, path, pPath, pQuery, body);
        return typeof result === "string" ? result : JSON.stringify(result, null, 2);
      });
    }
  }

  server.setRequestHandler(ListToolsRequestSchema, async () => ({
    tools: entries.map((e) => e.tool),
  }));

  server.setRequestHandler(CallToolRequestSchema, async (req) => {
    const { name, arguments: args } = req.params;
    const handler = dispatch.get(name);
    if (!handler) {
      return { content: [{ type: "text", text: `Unknown tool: ${name}` }], isError: true };
    }
    try {
      const text = await handler((args ?? {}) as Record<string, unknown>);
      return { content: [{ type: "text", text }] };
    } catch (err) {
      const msg = err instanceof Error ? err.message : String(err);
      return { content: [{ type: "text", text: `Error: ${msg}` }], isError: true };
    }
  });

  return server;
}

// ---------------------------------------------------------------------------
// Main
// ---------------------------------------------------------------------------

async function main(): Promise<void> {
  log(`[mcp] Connecting to opencode at ${OPENCODE_BASE}…`);
  const spec = await fetchSpec();
  log("[mcp] OpenAPI spec loaded.");

  const derivedEntries = buildTools(spec);
  const wfEntries = workflowTools();
  const allEntries = [...derivedEntries, ...wfEntries];

  log(`[mcp] ${derivedEntries.length} derived tools + ${wfEntries.length} workflow tools = ${allEntries.length} total.`);

  const server = createMcpServer(allEntries);

  if (MCP_PORT !== null) {
    // HTTP Stream mode — sidecar in agent2 container
    const transport = new StreamableHTTPServerTransport({ sessionIdGenerator: undefined });
    const httpServer = createServer((req, res) => {
      // Collect body chunks then pass parsed JSON to transport
      const chunks: Buffer[] = [];
      req.on("data", (chunk: Buffer) => chunks.push(chunk));
      req.on("end", () => {
        let body: unknown;
        try { body = JSON.parse(Buffer.concat(chunks).toString()); } catch { body = undefined; }
        transport.handleRequest(req, res, body).catch((err: unknown) => {
          log("[mcp] handleRequest error:", err);
          if (!res.headersSent) { res.writeHead(500).end("Internal server error"); }
        });
      });
    });
    await server.connect(transport);
    httpServer.listen(MCP_PORT, "0.0.0.0", () => {
      log(`[mcp] HTTP stream server listening on port ${MCP_PORT}`);
    });
  } else {
    // Stdio mode — spawned as child process by agent1's opencode
    const transport = new StdioServerTransport();
    await server.connect(transport);
    log("[mcp] stdio transport connected.");
  }
}

main().catch((err) => {
  log("[mcp] Fatal error:", err);
  process.exit(1);
});
