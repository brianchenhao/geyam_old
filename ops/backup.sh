#!/usr/bin/env bash
# Nightly offsite backup of the geyam postgres DB.
#
# Pipeline: pg_dump (custom format) -> upload to Cloudflare R2 (bucket geyam-backups).
# Runs as root via cron (rclone config lives in /root/.config/rclone/rclone.conf per
# the plan). Manual invocation: sudo /opt/geyam/ops/backup.sh.
#
# Append-logs to /var/log/geyam-backup.log so cron evidence persists; Phase 6 will
# wire Healthchecks.io to monitor exit status. Exit non-zero on any failure so
# external monitoring can detect silent breakage.

set -euo pipefail

LOG=/var/log/geyam-backup.log
BUCKET=geyam-backups
TS=$(date +%Y-%m-%d-%H%M%S)
DUMP_NAME="geyam-${TS}.dump"
TMP_DIR=$(mktemp -d)
DUMP_PATH="${TMP_DIR}/${DUMP_NAME}"

# Always tear down the tempdir; surface failures into the log.
trap 'rm -rf "$TMP_DIR"' EXIT

# Redirect *everything* to the log AND stdout (cron captures stdout for mail / Healthchecks).
exec > >(tee -a "$LOG") 2>&1

echo "==== $(date -Iseconds) starting backup: ${DUMP_NAME} ===="

# Custom-format pg_dump from the running geyam-db container. --no-owner so the dump
# is restorable as any role; --clean so a restore wipes target objects first.
docker exec geyam-db pg_dump -U pos_user --no-owner -Fc geyam > "$DUMP_PATH"

size=$(stat -c%s "$DUMP_PATH")
if [[ "$size" -lt 1024 ]]; then
    # pg_dump can exit 0 on a near-empty DB (e.g. if the DB was dropped). Catch it.
    echo "FATAL: dump suspiciously small (${size} bytes) — aborting upload." >&2
    exit 1
fi

# Upload to R2. rclone copy is idempotent; same filename twice would overwrite.
rclone copy "$DUMP_PATH" "r2:${BUCKET}/" --progress=false

echo "==== $(date -Iseconds) done — uploaded ${DUMP_NAME} (${size} bytes) ===="
