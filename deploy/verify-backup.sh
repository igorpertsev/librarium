#!/usr/bin/env bash
# Restore drill: load a dump into a throwaway PostgreSQL container (no network, removed
# afterwards) and print what it contains. Exits non-zero if the dump does not restore.
#
#   deploy/verify-backup.sh                         # newest dump in ~/librarium-backups
#   deploy/verify-backup.sh ~/librarium-backups/librarium-20261106T030000Z.dump
#
# Cron (Sundays at 04:00):  0 4 * * 0 /home/ubuntu/librarium/deploy/verify-backup.sh >> /home/ubuntu/librarium-backups/backup.log 2>&1
set -euo pipefail

BACKUP_DIR="${BACKUP_DIR:-$HOME/librarium-backups}"
POSTGRES_IMAGE="${POSTGRES_IMAGE:-postgres:16-alpine}"
dump="${1:-$(ls -1t "$BACKUP_DIR"/librarium-*.dump 2>/dev/null | head -n 1 || true)}"
if [[ -z "$dump" || ! -f "$dump" ]]; then
  echo "No dump found (looked in $BACKUP_DIR)." >&2
  exit 1
fi

container="librarium-restore-check-$$"
trap 'docker rm -f "$container" >/dev/null 2>&1 || true' EXIT
docker run -d --name "$container" --network none \
  -e POSTGRES_PASSWORD=restore-check -e POSTGRES_DB=restore_check \
  "$POSTGRES_IMAGE" >/dev/null

# The image's first start runs an init server on the Unix socket only; TCP readiness means
# the real server is up.
for _ in $(seq 1 60); do
  if docker exec "$container" pg_isready -q -h 127.0.0.1 -U postgres -d restore_check; then break; fi
  sleep 1
done

docker exec -i "$container" \
  pg_restore -h 127.0.0.1 -U postgres -d restore_check --no-owner --exit-on-error < "$dump"

docker exec "$container" psql -h 127.0.0.1 -U postgres -d restore_check -At -F ': ' -c "
  SELECT 'schema revision', version_num FROM alembic_version
  UNION ALL SELECT 'users', count(*)::text FROM users
  UNION ALL SELECT 'books', count(*)::text FROM books
  UNION ALL SELECT 'orders', count(*)::text FROM orders
  UNION ALL SELECT 'newest order', coalesce(max(created_at)::text, '-') FROM orders"
echo "$(date -u +%FT%TZ) restore check passed: $dump"
