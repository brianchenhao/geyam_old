#!/usr/bin/env bash
# Phase 5 step 7: lock UFW :80 + :443 to Cloudflare IP ranges only.
#
# Verification target (PLAN-stage3-Geyam.md Phase 5 §7):
#   "curl from non-CF IP refused"
#
# Builds on setup-firewall.sh (Phase 1 §4), which leaves 22/80/443 open to
# anywhere. This script keeps :22 wide (SSH must remain reachable from
# anywhere — fail2ban + key-only auth covers SSH defense) but rewrites
# :80 and :443 to allow only Cloudflare's published IPv4 + IPv6 ranges.
#
# Why :80 too: even though Caddy on :80 just redirects to https, leaving it
# open to the world means scanners hit it constantly. Locking it to CF
# means the redirect still works for legitimate users (CF always reaches
# us via CF IPs, regardless of upstream-customer protocol) and scanner
# traffic is dropped at the UFW layer before Caddy sees it.
#
# CF source of truth:
#   https://www.cloudflare.com/ips-v4
#   https://www.cloudflare.com/ips-v6
# These are updated occasionally. Re-run this script if CF announces a
# range change (rare — last expansion was 2023).
#
# Run as root on the VPS. Idempotent: deletes existing :80/:443 ALLOW rules
# and rebuilds from scratch.

set -euo pipefail

if [[ "$EUID" -ne 0 ]]; then
    echo "FATAL: restrict-firewall-cf.sh must run as root (or via sudo)." >&2
    exit 1
fi

if ! command -v ufw >/dev/null 2>&1; then
    echo "FATAL: ufw not installed — run setup-firewall.sh first." >&2
    exit 1
fi

# Fetch CF ranges. Fail loudly if either list is empty (network issue,
# DNS hijack, or CF outage — none of which we want to silently accept).
echo "Fetching Cloudflare IP ranges..."
v4=$(curl -fsS https://www.cloudflare.com/ips-v4 | awk 'NF')
v6=$(curl -fsS https://www.cloudflare.com/ips-v6 | awk 'NF')
if [[ -z "$v4" || -z "$v6" ]]; then
    echo "FATAL: failed to fetch CF IP ranges. Aborting." >&2
    exit 1
fi
echo "  v4: $(echo "$v4" | wc -l) CIDRs"
echo "  v6: $(echo "$v6" | wc -l) CIDRs"

# Delete existing :80 + :443 rules (any source). ufw status numbered shifts
# numbering after each delete, so we collect rule numbers, then iterate in
# reverse order.
echo "Removing existing :80 and :443 rules..."
mapfile -t to_del < <(
    ufw status numbered \
    | awk '/[[:space:]](80|443)\/tcp/ {gsub(/[\[\]]/, "", $1); print $1}' \
    | sort -rn
)
for n in "${to_del[@]}"; do
    yes | ufw delete "$n" || true
done

# Allow :80 + :443 from each CF range. Comment includes the CIDR so the
# rule is greppable and reversible.
echo "Adding CF-only allow rules..."
while read -r cidr; do
    [[ -z "$cidr" ]] && continue
    ufw allow proto tcp from "$cidr" to any port 80  comment "cf-v4 80 $cidr"  >/dev/null
    ufw allow proto tcp from "$cidr" to any port 443 comment "cf-v4 443 $cidr" >/dev/null
done <<< "$v4"

while read -r cidr; do
    [[ -z "$cidr" ]] && continue
    ufw allow proto tcp from "$cidr" to any port 80  comment "cf-v6 80 $cidr"  >/dev/null
    ufw allow proto tcp from "$cidr" to any port 443 comment "cf-v6 443 $cidr" >/dev/null
done <<< "$v6"

ufw reload >/dev/null
ufw status verbose | head -20
echo
echo "Done. Verify from a non-CF source:"
echo "  curl --resolve api.geyam.com:443:168.144.46.142 -v https://api.geyam.com/docs"
echo "  ^ should fail to connect (UFW drops). Compare to:"
echo "  curl https://api.geyam.com/docs"
echo "  ^ should still return 200 (traffic via CF)."
