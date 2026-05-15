#!/usr/bin/env bash
# Phase 1 step 6: pin VPS clock to Asia/Kuala_Lumpur.
#
# Verification target (PLAN-stage3-Geyam.md Phase 1 §6):
#   "date shows MY time"
#
# Why MY local time on a Singapore VPS: every cron'd job in Stage 3 — nightly
# pg_dump at 02:00, monthly restore drill, Healthchecks heartbeats — schedules
# off MY business hours. Plus humans read logs in MY time.
#
# Run as root. Idempotent.

set -euo pipefail

if [[ $EUID -ne 0 ]]; then
  echo "Must run as root" >&2
  exit 1
fi

TZ=Asia/Kuala_Lumpur

CURRENT="$(timedatectl show --property=Timezone --value)"
if [[ "$CURRENT" == "$TZ" ]]; then
  echo "Timezone already $TZ — skipping."
else
  timedatectl set-timezone "$TZ"
fi

# Ensure NTP is on so the wall clock actually tracks UTC properly (Droplet images
# usually have this on, but make it explicit).
timedatectl set-ntp true || true

timedatectl
date
