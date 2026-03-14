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

# Custom MCP bridge entrypoint (runs opencode serve + optional MCP sidecar)
COPY mcp-server/entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

WORKDIR /agent
EXPOSE 4096 4095

ENTRYPOINT ["/entrypoint.sh"]
