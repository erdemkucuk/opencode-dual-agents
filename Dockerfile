FROM node:20-slim

RUN npm install -g opencode-ai && \
    apt-get update && apt-get install -y curl jq procps iputils-ping bash git net-tools --no-install-recommends && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /agent
EXPOSE 4096

# --hostname 0.0.0.0 is required in Docker.
# The default (127.0.0.1) binds only to the container loopback
# and is unreachable from other containers on the network.
CMD ["opencode", "serve", "--hostname", "0.0.0.0", "--port", "4096"]
