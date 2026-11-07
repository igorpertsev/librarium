#!/usr/bin/env bash
# Load test (load/library.js) with k6 in Docker against the e2e stack (pnpm e2e:stack), which
# has rate limits off. Never point it at real data: it registers readers and fills carts.
#
#   pnpm load:test                                   20 visitors and 5 readers for a minute
#   VISITORS=50 READERS=10 DURATION=3m pnpm load:test
set -euo pipefail
cd "$(dirname "$0")/.."

if ! curl -fsS -o /dev/null http://localhost:8100/health; then
  echo "load: no e2e backend on http://localhost:8100; start it with: pnpm e2e:stack" >&2
  exit 2
fi
exec docker run --rm -i --network librarium-e2e_default \
  -e BASE_URL=http://backend:8000 -e VISITORS -e READERS -e DURATION \
  -v "$PWD/load:/load:ro" grafana/k6:2.3.0 run --quiet /load/library.js
