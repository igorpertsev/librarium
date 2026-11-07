#!/usr/bin/env bash
# Quick checks of a running site after a deploy (used by .github/workflows/deploy.yml).
#
#   deploy/smoke.sh https://staging.library.example.com
#
# Read-only: it changes nothing. Exits non-zero at the first failed check.
set -euo pipefail
base="${1:?usage: deploy/smoke.sh <site URL>}"
base="${base%/}"
tmp="$(mktemp)"
trap 'rm -f "$tmp"' EXIT

fail() { echo "FAIL: $*" >&2; exit 1; }
get() { # get <path> → body in $tmp, prints the HTTP status; TLS must be valid
  curl -sS --max-time 15 -o "$tmp" -w '%{http_code}' "$base$1"
}

# The backend may still be starting: wait up to two minutes for the readiness probe.
for attempt in $(seq 1 24); do
  status="$(get /api/v1/health || true)"
  [[ "$status" == "200" ]] && break
  (( attempt == 24 )) && fail "/api/v1/health answered ${status:-nothing}"
  sleep 5
done
grep -q '"database":"ok"' "$tmp" || fail "database not ready: $(cat "$tmp")"
echo "ok   backend and database are up"

[[ "$(get /)" == "200" ]] || fail "the home page does not load"
grep -q 'id="root"' "$tmp" || fail "the home page is not the app"
echo "ok   the app loads"

[[ "$(get /api/v1/library/rules)" == "200" ]] || fail "library rules"
grep -q '"books_per_batch"' "$tmp" || fail "library rules look wrong"
[[ "$(get '/api/v1/books?page_size=1')" == "200" ]] || fail "the catalogue does not answer"
grep -q '"items"' "$tmp" || fail "the catalogue looks wrong"
echo "ok   the catalogue answers"

[[ "$(get /manifest.webmanifest)" == "200" ]] || fail "the app manifest is missing"
headers="$(curl -sS --max-time 15 -D - -o /dev/null "$base/")"
for header in strict-transport-security content-security-policy x-content-type-options; do
  grep -qi "^$header:" <<<"$headers" || fail "missing header $header"
done
echo "ok   security headers are set"
echo "Smoke test passed for $base"
