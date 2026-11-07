#!/usr/bin/env bash
# Lighthouse budgets (lighthouserc.json) for the production build: the catalogue and sign-in
# pages, served by `vite preview` and talking to the e2e stack (start it with `pnpm e2e:stack`).
# Fails on accessibility or best practices under 0.95, layout shift over 0.1, errors in the
# console, or more than 300 KB of JavaScript; a low performance score is only a warning (covers
# come from Open Library). Reports: .lighthouseci/.
set -euo pipefail
cd "$(dirname "$0")/.."

if ! curl -fsS -o /dev/null http://localhost:8100/health; then
  echo "lighthouse: no e2e backend on http://localhost:8100; start it with: pnpm e2e:stack" >&2
  exit 2
fi
# CI has Playwright's Chromium; locally an installed Chrome is found by itself.
if [[ -z "${CHROME_PATH:-}" && -n "${CI:-}" ]]; then
  CHROME_PATH="$(node -e "console.log(require('@playwright/test').chromium.executablePath())")"
  export CHROME_PATH
fi
VITE_API_URL=http://localhost:8100/api/v1 pnpm -s build > /dev/null
rm -rf .lighthouseci
exec pnpm dlx @lhci/cli@0.15.1 autorun --config=lighthouserc.json
