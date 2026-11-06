#!/usr/bin/env bash
# Dump the production database to a timestamped file and delete old dumps. Optionally copy
# each dump off the VM with rclone (to object storage, another server, ...).
#
#   deploy/backup.sh                      # writes to ~/librarium-backups
#   BACKUP_DIR=/mnt/backups KEEP_DAYS=30 deploy/backup.sh
#   RCLONE_REMOTE=oci:librarium-backups deploy/backup.sh     # plus an off-site copy
#
# RCLONE_REMOTE is an rclone destination ("remote:bucket/path") configured in
# ~/.config/rclone/rclone.conf; rclone runs in a container, nothing to install. Off-site copies
# older than REMOTE_KEEP_DAYS (default 90) are deleted there.
#
# Cron (daily at 03:00):  0 3 * * * /home/ubuntu/librarium/deploy/backup.sh >> /home/ubuntu/librarium-backups/backup.log 2>&1
# Check that a dump restores: deploy/verify-backup.sh. Restore: "Backups" in deploy/README.md.
set -euo pipefail

cd "$(dirname "$0")/.."
BACKUP_DIR="${BACKUP_DIR:-$HOME/librarium-backups}"
KEEP_DAYS="${KEEP_DAYS:-14}"
RCLONE_REMOTE="${RCLONE_REMOTE:-}"
REMOTE_KEEP_DAYS="${REMOTE_KEEP_DAYS:-90}"
RCLONE_IMAGE="${RCLONE_IMAGE:-rclone/rclone:1.69}"
RCLONE_CONFIG_DIR="${RCLONE_CONFIG_DIR:-$HOME/.config/rclone}"
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

if [[ -n "$RCLONE_REMOTE" ]]; then
  rclone() {
    docker run --rm --user "$(id -u):$(id -g)" \
      -v "$RCLONE_CONFIG_DIR:/config/rclone" -v "$BACKUP_DIR:/data:ro" \
      "$RCLONE_IMAGE" "$@"
  }
  rclone copy "/data/$(basename "$target")" "$RCLONE_REMOTE" --no-traverse
  # Only old dumps written by this script are removed from the destination.
  rclone delete "$RCLONE_REMOTE" --include 'librarium-*.dump' --min-age "${REMOTE_KEEP_DAYS}d"
  echo "$(date -u +%FT%TZ) copied off-site to $RCLONE_REMOTE"
fi
