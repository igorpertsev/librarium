#!/usr/bin/env bash
# Dump the production database to a timestamped file and delete old dumps.
#
#   deploy/backup.sh                      # writes to ~/librarium-backups
#   BACKUP_DIR=/mnt/backups KEEP_DAYS=30 deploy/backup.sh
#
# Cron (daily at 03:00):  0 3 * * * /home/ubuntu/librarium/deploy/backup.sh >> /home/ubuntu/librarium-backups/backup.log 2>&1
# Restore: see "Backups" in deploy/README.md.
set -euo pipefail

cd "$(dirname "$0")/.."
BACKUP_DIR="${BACKUP_DIR:-$HOME/librarium-backups}"
KEEP_DAYS="${KEEP_DAYS:-14}"
COMPOSE=(docker compose -f docker-compose.prod.yml)

mkdir -p "$BACKUP_DIR"
chmod 700 "$BACKUP_DIR"
timestamp="$(date -u +%Y%m%dT%H%M%SZ)"
target="$BACKUP_DIR/librarium-$timestamp.dump"

# Write to a temporary name first so an interrupted run never leaves a "valid-looking" file.
"${COMPOSE[@]}" exec -T db sh -c 'pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" --format=custom' \
  > "$target.partial"
mv "$target.partial" "$target"
chmod 600 "$target"

find "$BACKUP_DIR" -name 'librarium-*.dump' -mtime +"$KEEP_DAYS" -delete
echo "$(date -u +%FT%TZ) backup written: $target ($(du -h "$target" | cut -f1))"
