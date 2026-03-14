FROM node:20-slim

RUN npm install -g opencode-ai && \
    apt-get update && apt-get install -y curl jq procps iputils-ping bash git net-tools --no-install-recommends && \
    rm -rf /var/lib/apt/lists/*

# Build the custom FastMCP bridge server
COPY mcp-server/ /mcp-server/
RUN cd /mcp-server && npm install && npm run build

# Agent2 entrypoint (runs opencode serve + MCP server together)
COPY scripts/entrypoint-agent2.sh /scripts/entrypoint-agent2.sh
RUN chmod +x /scripts/entrypoint-agent2.sh

WORKDIR /agent
EXPOSE 4096 4095

# --hostname 0.0.0.0 is required in Docker.
# The default (127.0.0.1) binds only to the container loopback
# and is unreachable from other containers on the network.
CMD ["opencode", "serve", "--hostname", "0.0.0.0", "--port", "4096"]
