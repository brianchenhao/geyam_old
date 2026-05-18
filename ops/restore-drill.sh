#!/usr/bin/env bash
# Automated restore drill: pull latest R2 backup, restore into a sidecar DB,
# diff row counts vs live, then drop the sidecar. Plan Phase 3 step 7.
#
# Phase 6 will cron this weekly and wire Healthchecks.io. Exit non-zero if any
# table's row count diverges between live and restored — that's a corrupt backup.
#
# Runs as root because rclone config lives in /root/.config/rclone/rclone.conf.

set -euo pipefail

LOG=/var/log/geyam-restore-drill.log
BUCKET=geyam-backups
TEST_DB=geyam_restore_test
TMP_DIR=$(mktemp -d)

trap 'rm -rf "$TMP_DIR"; docker exec geyam-db psql -U pos_user -d postgres -c "DROP DATABASE IF EXISTS ${TEST_DB};" >/dev/null 2>&1 || true' EXIT

exec > >(tee -a "$LOG") 2>&1

echo "==== $(date -Iseconds) starting restore drill ===="

# Pick the lexicographically last dump (filenames sort by timestamp).
LATEST=$(rclone lsf "r2:${BUCKET}/" --include 'geyam-*.dump' | sort | tail -n1)
if [[ -z "$LATEST" ]]; then
    echo "FATAL: no backups in r2:${BUCKET}/" >&2
    exit 1
fi
echo "Latest backup: ${LATEST}"

rclone copy "r2:${BUCKET}/${LATEST}" "$TMP_DIR/"

# Drop+recreate the sidecar DB, copy the dump into the container, pg_restore.
docker exec geyam-db psql -U pos_user -d postgres -c "DROP DATABASE IF EXISTS ${TEST_DB};"
docker exec geyam-db psql -U pos_user -d postgres -c "CREATE DATABASE ${TEST_DB};"
docker cp "${TMP_DIR}/${LATEST}" "geyam-db:/tmp/${LATEST}"
docker exec geyam-db pg_restore -U pos_user --no-owner -d "${TEST_DB}" "/tmp/${LATEST}"
docker exec geyam-db rm "/tmp/${LATEST}"

# Diff row counts across every public-schema table in the live DB.
echo "Comparing row counts: live geyam vs restored ${TEST_DB}..."
TABLES=$(docker exec geyam-db psql -U pos_user -d geyam -t -A -c \
    "SELECT tablename FROM pg_tables WHERE schemaname='public' ORDER BY 1;")

diverged=0
for t in $TABLES; do
    live=$(docker exec geyam-db psql -U pos_user -d geyam -t -A -c "SELECT COUNT(*) FROM \"$t\";")
    restored=$(docker exec geyam-db psql -U pos_user -d "${TEST_DB}" -t -A -c "SELECT COUNT(*) FROM \"$t\";" 2>/dev/null || echo "MISSING")
    if [[ "$live" != "$restored" ]]; then
        echo "  DIVERGED: $t — live=$live restored=$restored"
        diverged=$((diverged + 1))
    else
        echo "  OK:       $t = $live"
    fi
done

if [[ "$diverged" -gt 0 ]]; then
    echo "==== $(date -Iseconds) drill FAILED — ${diverged} tables diverged ===="
    exit 1
fi

echo "==== $(date -Iseconds) drill PASSED — all row counts match ===="
