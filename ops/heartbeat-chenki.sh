#!/usr/bin/env bash
# Hourly chenki wakeup ping. HF Spaces sleep after ~48h of inactivity; pinging
# hourly keeps it warm so the first /menu/ask after a quiet period doesn't
# eat a cold-start delay (cold start = ~60s vs warm ~2s).
#
# Probes /health endpoint of the Space, then pings Healthchecks on success.
# Failures still ping /fail so the cause is visible without dashboard access.
#
# Cron entry (root, hourly, offset to avoid colliding with api heartbeat):
#   15 * * * * /opt/geyam/ops/heartbeat-chenki.sh

set -euo pipefail

[[ -f /etc/default/geyam ]] && source /etc/default/geyam
: "${HC_CHENKI_URL:=}"
: "${CHENKI_BASE:=https://brianchenhao-chenki-llm.hf.space}"

if [[ -z "$HC_CHENKI_URL" ]]; then
    echo "HC_CHENKI_URL not set; skipping ping" >&2
    exit 0
fi

# Use --max-time generously — a cold HF Space can take 60s+ to respond on first
# wake. We'd rather wait than spuriously alert.
if curl -fsS -m 90 -o /dev/null "${CHENKI_BASE}/health"; then
    curl -fsS -m 10 --retry 3 -o /dev/null "$HC_CHENKI_URL" || true
else
    curl -fsS -m 10 --retry 3 -o /dev/null "${HC_CHENKI_URL}/fail" || true
    exit 1
fi
