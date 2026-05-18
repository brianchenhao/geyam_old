#!/usr/bin/env bash
# Install rclone and configure the r2 remote on the VPS.
#
# Run as root (or with sudo) — the rclone config lives in /root/.config/rclone/
# so the backup cron (also root) can read it. Plan Phase 3 step 2-3.
#
# Required env vars (export before invoking, or pass via a one-off `env A=… B=…`):
#   R2_ACCOUNT_ID         — Cloudflare account id (32 hex chars), forms the endpoint
#                           https://<account>.r2.cloudflarestorage.com
#   R2_ACCESS_KEY_ID      — bucket-scoped access key from R2 dashboard
#   R2_SECRET_ACCESS_KEY  — corresponding secret
#
# Idempotent: re-running with the same env overwrites the config in place.

set -euo pipefail

: "${R2_ACCOUNT_ID:?must export R2_ACCOUNT_ID}"
: "${R2_ACCESS_KEY_ID:?must export R2_ACCESS_KEY_ID}"
: "${R2_SECRET_ACCESS_KEY:?must export R2_SECRET_ACCESS_KEY}"

if [[ "$EUID" -ne 0 ]]; then
    echo "FATAL: setup-rclone.sh must run as root (or via sudo)." >&2
    exit 1
fi

if ! command -v rclone >/dev/null 2>&1; then
    echo "Installing rclone via apt..."
    apt-get update -qq
    apt-get install -y rclone
fi

CONFIG_DIR=/root/.config/rclone
CONFIG=${CONFIG_DIR}/rclone.conf
mkdir -p "$CONFIG_DIR"
umask 077

cat > "$CONFIG" <<EOF
[r2]
type = s3
provider = Cloudflare
region = auto
access_key_id = ${R2_ACCESS_KEY_ID}
secret_access_key = ${R2_SECRET_ACCESS_KEY}
endpoint = https://${R2_ACCOUNT_ID}.r2.cloudflarestorage.com
acl = private
# Skip the implicit CreateBucket / HeadBucket probe rclone does before every PUT.
# Our R2 token has Object Read & Write but not bucket-admin — that probe 403s,
# masking the actual upload as a failure. Bucket exists, we know it; skip the check.
no_check_bucket = true
EOF
chmod 600 "$CONFIG"

echo "Wrote ${CONFIG} (mode 600)."
echo "Listing bucket geyam-backups (should succeed even when empty):"
rclone ls r2:geyam-backups
echo "rclone setup OK."
