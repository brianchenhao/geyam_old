#!/usr/bin/env bash
# Install host-side logrotate config for Geyam.
#
# Idempotent — safe to re-run after edits to logrotate-geyam.conf.
# Validates the config with `logrotate --debug` before installing.
#
# Usage (on VPS as root or via sudo):
#   sudo bash /opt/geyam/ops/install-logrotate.sh

set -euo pipefail

SRC="$(cd "$(dirname "$0")" && pwd)/logrotate-geyam.conf"
DST="/etc/logrotate.d/geyam"

if [[ ! -f "$SRC" ]]; then
    echo "FAIL  source config missing: $SRC" >&2
    exit 1
fi

if [[ $EUID -ne 0 ]]; then
    echo "FAIL  must run as root (logrotate.d is root-only)" >&2
    exit 1
fi

echo "[1/3] Dry-run validation"
if ! logrotate --debug "$SRC" >/dev/null 2>&1; then
    echo "FAIL  logrotate rejected the config:" >&2
    logrotate --debug "$SRC" 2>&1 | head -20 >&2
    exit 1
fi

echo "[2/3] Installing to $DST"
install -m 0644 -o root -g root "$SRC" "$DST"

echo "[3/3] Listing effective rotation for known paths"
logrotate --debug /etc/logrotate.conf 2>&1 \
    | grep -A1 "geyam-backup.log" \
    | head -10 \
    || echo "      (no matches yet — logs may not exist; rotation will start once they do)"

echo "OK    logrotate config installed. Verify next run with: cat /var/lib/logrotate/status | grep geyam"
