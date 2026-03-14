FROM node:20-slim

# Install system dependencies and Python 3.12
RUN apt-get update && apt-get install -y \
    curl \
    jq \
    procps \
    iputils-ping \
    bash \
    git \
    net-tools \
    python3 \
    python3-pip \
    python3-venv \
    --no-install-recommends && \
    rm -rf /var/lib/apt/lists/*

RUN npm install -g opencode-ai

# Build the custom Python FastMCP bridge server
COPY mcp-server/ /mcp-server/
RUN python3 -m venv /mcp-server/.venv && \
    /mcp-server/.venv/bin/pip install -r /mcp-server/requirements.txt

# Agent2 entrypoint (runs opencode serve + MCP server together)
COPY scripts/entrypoint-agent2.sh /scripts/entrypoint-agent2.sh
RUN chmod +x /scripts/entrypoint-agent2.sh

WORKDIR /agent
EXPOSE 4096 4095

# --hostname 0.0.0.0 is required in Docker.
CMD ["opencode", "serve", "--hostname", "0.0.0.0", "--port", "4096"]
