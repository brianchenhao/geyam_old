#!/usr/bin/env bash
# Nightly offsite backup of the geyam postgres DB.
#
# Pipeline: pg_dump (custom format) -> upload to Cloudflare R2 (bucket geyam-backups).
# Runs as root via cron (rclone config lives in /root/.config/rclone/rclone.conf per
# the plan). Manual invocation: sudo /opt/geyam/ops/backup.sh.
#
# Append-logs to /var/log/geyam-backup.log so cron evidence persists. Pings
# Healthchecks.io on start/success/fail when HC_BACKUP_URL is set (Phase 6 step 3) —
# if unset, the pings are silently skipped so the backup itself still runs.
# Exit non-zero on any failure so external monitoring can detect silent breakage.

set -euo pipefail

LOG=/var/log/geyam-backup.log
BUCKET=geyam-backups
TS=$(date +%Y-%m-%d-%H%M%S)
DUMP_NAME="geyam-${TS}.dump"
TMP_DIR=$(mktemp -d)
DUMP_PATH="${TMP_DIR}/${DUMP_NAME}"

# Healthchecks.io ping URL — sourced from /etc/default/geyam if present (root-owned,
# mode 600), else from the environment. URL itself is a secret-equivalent (anyone
# who knows it can spoof a "backup ok" ping), hence the file lives outside the repo.
[[ -f /etc/default/geyam ]] && source /etc/default/geyam
: "${HC_BACKUP_URL:=}"

# Always tear down the tempdir; surface failures into the log.
trap 'rm -rf "$TMP_DIR"' EXIT

# Redirect *everything* to the log AND stdout (cron captures stdout for mail / Healthchecks).
exec > >(tee -a "$LOG") 2>&1

hc_ping() {
    # $1 = path suffix ("" for success, "/start" or "/fail").
    # Curl with retries; never fail the backup because the ping failed.
    [[ -z "$HC_BACKUP_URL" ]] && return 0
    curl -fsS -m 10 --retry 3 -o /dev/null "${HC_BACKUP_URL}${1}" || true
}

# Signal "starting" so HC can detect runs that never report completion.
hc_ping "/start"

# If anything below exits non-zero, ping /fail before exiting. Logs already
# captured by the exec-tee above carry the actual error.
trap 'rc=$?; rm -rf "$TMP_DIR"; if [[ $rc -ne 0 ]]; then hc_ping "/fail"; fi; exit $rc' EXIT

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

# Success ping (no suffix on Healthchecks.io URL = success).
hc_ping ""
