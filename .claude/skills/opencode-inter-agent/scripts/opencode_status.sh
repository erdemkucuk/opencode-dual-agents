#!/usr/bin/env bash
# Get a combined snapshot of an opencode server's health, session count, and providers.
#
# Bundles three API calls (health, sessions, providers) into one JSON response.
#
# Usage:
#   ./opencode_status.sh <base_url>
#
# Example:
#   ./opencode_status.sh http://localhost:4098

set -euo pipefail

if [[ $# -lt 1 ]]; then
  echo "Usage: $0 <base_url>" >&2
  exit 1
fi

BASE="${1%/}"

HEALTH=$(curl -sf "${BASE}/global/health")
SESSIONS=$(curl -sf "${BASE}/session")
PROVIDERS=$(curl -sf "${BASE}/provider")

SESSION_COUNT=$(echo "$SESSIONS" | jq 'if type == "array" then length else 0 end')

jq -n \
  --argjson health "$HEALTH" \
  --argjson session_count "$SESSION_COUNT" \
  --argjson providers "$PROVIDERS" \
  '{"health": $health, "session_count": $session_count, "providers": $providers}'
