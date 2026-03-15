#!/usr/bin/env bash
# Check whether an opencode server is healthy.
#
# Usage:
#   ./opencode_health.sh <base_url>
#
# Example:
#   ./opencode_health.sh http://localhost:4098

set -euo pipefail

if [[ $# -lt 1 ]]; then
  echo "Usage: $0 <base_url>" >&2
  exit 1
fi

BASE="${1%/}"

curl -sf "${BASE}/global/health" | jq .
