#!/usr/bin/env bash
# Hourly liveness heartbeat: probe https://api.geyam.com/healthz, then ping
# Healthchecks.io on success. If /healthz returns non-200 OR is unreachable,
# DO NOT ping HC — the check goes red after its grace window, triggering an
# alert. This is the "passive heartbeat" pattern with active payload checking.
#
# Cron entry (root, hourly):
#   5 * * * * /opt/geyam/ops/heartbeat-api.sh
# (Offset by 5 min so we don't collide with backup at 02:00.)

set -euo pipefail

[[ -f /etc/default/geyam ]] && source /etc/default/geyam
: "${HC_API_URL:=}"

if [[ -z "$HC_API_URL" ]]; then
    echo "HC_API_URL not set; skipping ping" >&2
    exit 0
fi

# Probe /healthz; fail fast (curl -f) on non-2xx. 10s ceiling on the whole probe.
if curl -fsS -m 10 -o /dev/null "https://api.geyam.com/healthz"; then
    curl -fsS -m 10 --retry 3 -o /dev/null "$HC_API_URL" || true
else
    # Optional /fail ping so we see the failure reason in HC events even before
    # the grace window expires. Caller's exit code drives nothing else.
    curl -fsS -m 10 --retry 3 -o /dev/null "${HC_API_URL}/fail" || true
    exit 1
fi
