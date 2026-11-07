#!/usr/bin/env bash
# Runs the same checks as CI (.github/workflows/ci.yml), so a push does not turn CI red.
#
#   scripts/check.sh            backend and frontend (everything but the browser tests)
#   scripts/check.sh --fast     format, lint, types and unit tests only (no pytest, build, migrations)
#   scripts/check.sh --e2e      also the browser tests and API fuzzing, on the e2e stack
#   scripts/check.sh --backend  or --frontend: only that half
#
# The backend runs in the dev container (docker compose --profile dev), the frontend on this
# machine with pnpm. The migration check uses a throwaway database, never the dev data.
set -euo pipefail

cd "$(dirname "$0")/.."

fast=0 e2e=0 backend=1 frontend=1
for arg in "$@"; do
  case "$arg" in
    --fast) fast=1 ;;
    --e2e) e2e=1 ;;
    --backend) frontend=0 ;;
    --frontend) backend=0 ;;
    -h | --help)
      sed -n '2,11p' "$0" | sed 's/^# \{0,1\}//'
      exit 0
      ;;
    *)
      echo "Unknown option: $arg (see --help)" >&2
      exit 2
      ;;
  esac
done

failed=()
step() {
  local name=$1
  shift
  printf '\n\033[1m== %s\033[0m\n' "$name"
  if "$@"; then
    printf '\033[32mok\033[0m %s\n' "$name"
  else
    printf '\033[31mFAILED\033[0m %s\n' "$name"
    failed+=("$name")
  fi
}

compose_dev() {
  docker compose --profile dev run --rm --no-deps backend-dev "$@"
}

check_db=bookstore_check
psql_db() {
  docker compose exec -T db psql -U postgres -v ON_ERROR_STOP=1 -qc "$1"
}

migrations() {
  psql_db "DROP DATABASE IF EXISTS $check_db" &&
    psql_db "CREATE DATABASE $check_db" || return 1
  local status=0
  # shellcheck disable=SC2016 # expanded inside the container
  docker compose --profile dev run --rm --no-deps -e CHECK_DB="$check_db" backend-dev sh -ec '
    export DATABASE_URL="${DATABASE_URL%/*}/$CHECK_DB"
    alembic upgrade head > /dev/null
    alembic check
    alembic downgrade base > /dev/null
  ' || status=$?
  psql_db "DROP DATABASE IF EXISTS $check_db" || true
  return "$status"
}

generated_in_sync() {
  compose_dev python -m app.cli export-openapi openapi.json > /dev/null 2>&1 || return 1
  pnpm -s api:types:file > /dev/null || return 1
  if ! git diff --exit-code --stat -- backend/openapi.json src/api/generated/schema.d.ts; then
    echo "The API schema or the generated types changed: review and commit backend/openapi.json" \
      "and src/api/generated/schema.d.ts."
    return 1
  fi
}

if ((backend)); then
  docker compose up -d --wait db > /dev/null
  step "Backend format" compose_dev ruff format --check .
  step "Backend lint" compose_dev ruff check .
  step "Backend types (mypy)" compose_dev mypy
  if ((!fast)); then
    step "Migrations apply, match the models and roll back" migrations
    step "Backend tests" compose_dev pytest -q
  fi
fi

if ((frontend)); then
  if ((backend && !fast)); then
    step "API schema and generated types" generated_in_sync
  fi
  step "Frontend lint" pnpm -s lint
  step "Frontend types" pnpm -s typecheck
  step "Frontend unit tests" pnpm -s test
  if ((!fast)); then
    step "Frontend build" pnpm -s build
  fi
fi

if ((e2e)); then
  step "Browser tests" sh -c 'pnpm -s e2e:stack && pnpm -s e2e'
  step "API fuzzing (Schemathesis)" pnpm -s api:fuzz
fi

echo
if ((${#failed[@]})); then
  printf '\033[31m%d failed:\033[0m\n' "${#failed[@]}"
  printf '  - %s\n' "${failed[@]}"
  exit 1
fi
printf '\033[32mAll checks passed.\033[0m\n'
