#!/usr/bin/env bash
# Phase 1 step 8: 4 GB swapfile, swappiness=10.
#
# Verification target (PLAN-stage3-Geyam.md Phase 1 §8):
#   "free -h shows swap"
#
# This is NON-OPTIONAL on a 2 GB Droplet (plan §1, "Key Risks"). Postgres +
# Redis + FastAPI + Caddy live on a 2 GiB box; OOM-killer reaping the backend
# container is the dominant ongoing risk of Stage 3. Swap is a safety net so
# memory pressure spikes (e.g. a heavy report query) don't kill processes.
#
# swappiness=10 keeps swap as a last resort. vfs_cache_pressure=50 keeps inode
# caches a bit longer than the default — helpful when Postgres is hot.
#
# Run as root on the VPS. Idempotent.

set -euo pipefail

if [[ $EUID -ne 0 ]]; then
  echo "Must run as root" >&2
  exit 1
fi

SWAPFILE=/swapfile
SIZE_BYTES=$((4 * 1024 * 1024 * 1024))  # 4 GiB

if [[ -e "$SWAPFILE" ]] && swapon --show=NAME --noheadings | grep -Fxq "$SWAPFILE"; then
  echo "$SWAPFILE already active — skipping create."
else
  if [[ ! -e "$SWAPFILE" ]]; then
    # fallocate is fast; some filesystems don't support it, fall back to dd.
    if ! fallocate -l "$SIZE_BYTES" "$SWAPFILE" 2>/dev/null; then
      dd if=/dev/zero of="$SWAPFILE" bs=1M count=4096 status=progress
    fi
    chmod 600 "$SWAPFILE"
    mkswap "$SWAPFILE"
  fi
  swapon "$SWAPFILE"
fi

# Persist across reboots. Only append if not already in fstab.
if ! grep -Eq "^\s*${SWAPFILE//\//\\/}\s+" /etc/fstab; then
  echo "$SWAPFILE none swap sw 0 0" >> /etc/fstab
fi

# Tunables — write a sysctl drop-in so it survives reboot.
SYSCTL_DROPIN=/etc/sysctl.d/60-geyam-swap.conf
cat > "$SYSCTL_DROPIN" <<'EOF'
# Stage 3 — swap is a safety net, not a hot path.
vm.swappiness=10
vm.vfs_cache_pressure=50
EOF
sysctl --load="$SYSCTL_DROPIN"

free -h
swapon --show
echo
echo "Swap configured. Watch /proc/meminfo:SwapFree and Healthchecks alerts if it"
echo "starts being heavily used — that's the canary for resize-up budget talk."
