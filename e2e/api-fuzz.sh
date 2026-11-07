#!/usr/bin/env bash
# Fuzzes the API with Schemathesis on the throwaway e2e stack (start it with `pnpm e2e:stack`):
# thousands of requests generated from the OpenAPI schema, as a visitor, a reader and the e2e
# administrator. Fails on any 5xx answer, a response that does not match its documented schema,
# or a wrong content type. Never point it at real data: it creates, changes and deletes things.
#
#   pnpm api:fuzz                       10 examples per operation and phase
#   API_FUZZ_EXAMPLES=50 pnpm api:fuzz  more thorough
#
# A failure prints a curl command and a test case id that reproduce it.
set -euo pipefail

api=${API_FUZZ_URL:-http://localhost:8100} # the e2e backend, as this machine sees it
network=${API_FUZZ_NETWORK:-librarium-e2e_default}
image=schemathesis/schemathesis:4.32.3
examples=${API_FUZZ_EXAMPLES:-10}
# Test values of the e2e stack (e2e/docker-compose.yml).
admin_email=e2e-admin@example.com
admin_password=e2e-admin-password
# Operations that would sign the fuzzing user out or delete or lock their account.
skip='^/api/v1/(users/me|auth/logout|auth/change-password)$'

if ! curl -fsS -o /dev/null "$api/health"; then
  echo "api-fuzz: no e2e backend at $api; start it with: pnpm e2e:stack" >&2
  exit 2
fi

token_for() { # email password
  curl -fsS -X POST "$api/api/v1/auth/login" -H 'content-type: application/json' \
    -d "{\"email\": \"$1\", \"password\": \"$2\"}" |
    python3 -c 'import json, sys; print(json.load(sys.stdin)["access_token"])'
}

reader_email="fuzz-reader-$(date +%s)-$$@example.com"
reader_password="Fuzz-reader-$(date +%s)-$$"
curl -fsS -o /dev/null -X POST "$api/api/v1/auth/register" -H 'content-type: application/json' \
  -d "{\"email\": \"$reader_email\", \"password\": \"$reader_password\", \"full_name\": \"Fuzz Reader\",
       \"telegram\": \"@fuzz_reader\", \"preferred_contact_method\": \"telegram\"}"

log=$(mktemp)
trap 'rm -f "$log"' EXIT
failed=()
fuzz() { # name [token]
  local name=$1 token=${2:-} status=0
  printf '\n\033[1m== API fuzzing as %s\033[0m\n' "$name"
  local auth=()
  [[ -n "$token" ]] && auth=(-e "API_TOKEN=$token")
  # shellcheck disable=SC2016 # expanded inside the container
  docker run --rm --network "$network" "${auth[@]+"${auth[@]}"}" -e EXAMPLES="$examples" \
    -e SKIP="$skip" --entrypoint sh "$image" -c '
      set -- run http://backend:8000/openapi.json --url http://backend:8000 \
        --checks not_a_server_error,response_schema_conformance,content_type_conformance \
        --max-examples "$EXAMPLES" --workers 4 --no-color --exclude-path-regex "$SKIP"
      if [ -n "${API_TOKEN:-}" ]; then
        set -- "$@" --header "Authorization: Bearer $API_TOKEN"
      fi
      st "$@"' > "$log" 2>&1 || status=$?
  if ((status)); then
    # The failures with their reproduction, then the summary.
    sed -n '/=* FAILURES =*/,$p' "$log" | sed -E 's/Bearer [A-Za-z0-9._-]+/Bearer <token>/g'
    failed+=("$name")
  else
    grep -A1 'Test cases:' "$log" | tail -1
  fi
}

fuzz visitor
fuzz reader "$(token_for "$reader_email" "$reader_password")"
fuzz administrator "$(token_for "$admin_email" "$admin_password")"

echo
if ((${#failed[@]})); then
  printf '\033[31mAPI fuzzing found problems as: %s\033[0m\n' "${failed[*]}"
  exit 1
fi
printf '\033[32mAPI fuzzing passed.\033[0m\n'
