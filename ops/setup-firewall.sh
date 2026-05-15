#!/usr/bin/env bash
# Phase 1 step 4: UFW firewall — allow 22, 80, 443 only.
#
# Verification target (PLAN-stage3-Geyam.md Phase 1 §4):
#   "nmap shows only 3 open ports"
#
# Phase 5 will further restrict :443 to Cloudflare IP ranges only. This step
# only sets the baseline — anything-from-anywhere on 22/80/443. Don't lock
# down to CF IPs here, or you'll be unable to use --resolve smoke tests
# during the Phase 4 cutover.
#
# Run as root on the VPS. Idempotent (ufw allow is a no-op if rule exists).

set -euo pipefail

if [[ $EUID -ne 0 ]]; then
  echo "Must run as root" >&2
  exit 1
fi

if ! command -v ufw >/dev/null 2>&1; then
  apt-get update
  DEBIAN_FRONTEND=noninteractive apt-get install -y ufw
fi

# Defaults. Reset to a clean slate first so re-runs don't accumulate cruft.
ufw --force reset
ufw default deny incoming
ufw default allow outgoing

# Allow SSH FIRST, before enabling. Enabling without 22 open severs your session.
ufw allow 22/tcp comment 'ssh'
ufw allow 80/tcp comment 'http (Caddy ACME + redirect)'
ufw allow 443/tcp comment 'https (Caddy)'

ufw --force enable
ufw status verbose

echo
echo "Sanity check from your laptop:"
echo "  nmap -Pn -p 1-1024 <droplet-ip>      # expect 22, 80, 443 open; everything else closed"
