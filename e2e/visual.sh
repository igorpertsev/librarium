#!/usr/bin/env bash
# Visual regression tests (playwright.visual.config.ts) in the Playwright Docker image, against a
# fresh e2e stack, so the screenshots match the reference images in e2e/visual/__screenshots__ on
# every machine and in CI.
#
#   pnpm e2e:visual                        compare with the reference images
#   pnpm e2e:visual --update-snapshots     write new reference images (review them before committing)
#
# Differences end up in test-results-visual/ (expected, actual and diff images per screenshot).
set -euo pipefail
cd "$(dirname "$0")/.."

image=mcr.microsoft.com/playwright:v1.65.0-noble # keep in step with @playwright/test
stack=(docker compose -f e2e/docker-compose.yml)

# A freshly seeded database, so the pages show the same data every time.
"${stack[@]}" down --remove-orphans > /dev/null 2>&1 || true
"${stack[@]}" up -d --build --wait > /dev/null

# Linux node_modules live in a volume (the checkout's may be built for another OS); the files
# written into the checkout are handed back to the current user at the end.
docker run --rm --init --ipc=host --network librarium-e2e_default \
  -v "$PWD:/work" -v librarium-visual-node-modules:/work/node_modules -w /work \
  -e CI="${CI:-}" -e VISUAL_BACKEND_URL=http://backend:8000 \
  -e HOST_UID="$(id -u)" -e HOST_GID="$(id -g)" \
  "$image" bash -c '
    set -uo pipefail
    # The pnpm version from package.json (the image has no corepack).
    npm install --global --silent "$(node -p "require(\"./package.json\").packageManager")" || exit 1
    # The store stays inside the volume (not in the checkout); errors only.
    pnpm install --frozen-lockfile --loglevel error --store-dir node_modules/.pnpm-store \
      --config.confirmModulesPurge=false || exit 1
    pnpm exec playwright test -c playwright.visual.config.ts "$@"
    status=$?
    chown -R "$HOST_UID:$HOST_GID" e2e/visual test-results-visual playwright-report-visual 2> /dev/null
    exit $status
  ' visual "$@"
