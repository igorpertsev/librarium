#!/usr/bin/env bash
# Update this server to a commit and restart the stack (used by .github/workflows/deploy.yml).
#
#   deploy/update.sh <commit>              # production: backup first
#   deploy/update.sh --no-backup <commit>  # staging
#
# It can also be the forced command of a restricted SSH key (see deploy/README.md): then the
# commit comes from SSH_ORIGINAL_COMMAND, e.g. `ssh deploy@host "update 1a2b3c4"`.
set -euo pipefail
cd "$(dirname "$0")/.."

args=("$@")
if (( ${#args[@]} == 0 )) && [[ -n "${SSH_ORIGINAL_COMMAND:-}" ]]; then
  # Forced command of a restricted key: the client asked for
  # "…/deploy/update.sh [--no-backup] <commit>" (deploy/ci-ssh.sh) or "update <commit>".
  read -r -a args <<<"$SSH_ORIGINAL_COMMAND"
  if [[ "${args[0]:-}" == "update" || "${args[0]:-}" == */deploy/update.sh ]]; then
    args=("${args[@]:1}")
  fi
  # A staging server can skip backups whatever the client asks.
  if [[ "${DEPLOY_NO_BACKUP:-0}" == "1" && "${args[0]:-}" != "--no-backup" ]]; then
    args=(--no-backup "${args[@]}")
  fi
fi
backup=1
if [[ "${args[0]:-}" == "--no-backup" ]]; then
  backup=0
  args=("${args[@]:1}")
fi
if (( ${#args[@]} != 1 )); then
  echo "usage: update.sh [--no-backup] <commit>" >&2
  exit 2
fi
ref="${args[0]}"
# A commit id only: nothing that the shell or git could read as options.
if [[ ! "$ref" =~ ^[0-9a-f]{7,40}$ ]]; then
  echo "update.sh: expected a commit id, got '${ref}'" >&2
  exit 2
fi
if [[ -n "$(git status --porcelain --untracked-files=no)" ]]; then
  echo "update.sh: local changes in $(pwd); not updating" >&2
  exit 1
fi

compose=(docker compose -f docker-compose.prod.yml)
if (( backup )); then
  deploy/backup.sh
fi
git fetch --quiet origin
git -c advice.detachedHead=false checkout --quiet --detach "$ref"
echo "$(date -u +%FT%TZ) deploying $(git log -1 --format='%h %s')"
# Fresh base images every time, so security fixes in Python, Node, Caddy and PostgreSQL arrive:
# --pull for the images built here, `pull` for the published ones (PostgreSQL).
"${compose[@]}" build --pull
"${compose[@]}" pull --ignore-buildable --quiet
# --wait: returns once every service with a health check is healthy (or fails).
"${compose[@]}" up -d --wait --wait-timeout 300
docker image prune -f >/dev/null
echo "$(date -u +%FT%TZ) running $(git rev-parse --short HEAD)"
