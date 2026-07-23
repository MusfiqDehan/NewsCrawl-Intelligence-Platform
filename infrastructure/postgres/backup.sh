#!/bin/bash
# Nightly logical backup with retention. Runs inside the postgres-backup
# container (see docker-compose.prod.yml); dumps land in the postgres_backups
# volume. Copy them off-host with your own scheduler (rsync/rclone/S3).
set -euo pipefail

BACKUP_DIR=${BACKUP_DIR:-/backups}
RETENTION_DAYS=${BACKUP_RETENTION_DAYS:-14}
INTERVAL_SECONDS=${BACKUP_INTERVAL_SECONDS:-86400}

mkdir -p "$BACKUP_DIR"

while true; do
    stamp=$(date -u +%Y%m%dT%H%M%SZ)
    target="$BACKUP_DIR/newscrawl-$stamp.dump"
    echo "[backup] starting pg_dump -> $target"
    if pg_dump --format=custom --compress=9 --file="$target.tmp"; then
        mv "$target.tmp" "$target"
        echo "[backup] done: $(du -h "$target" | cut -f1)"
    else
        echo "[backup] FAILED" >&2
        rm -f "$target.tmp"
    fi

    find "$BACKUP_DIR" -name 'newscrawl-*.dump' -mtime "+$RETENTION_DAYS" -delete
    sleep "$INTERVAL_SECONDS"
done
