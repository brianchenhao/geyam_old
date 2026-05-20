#!/usr/bin/env bash
# Configure Cloudflare edge hardening for api.geyam.com (Phase 5 steps 3, 4, 5).
#
# What this applies:
#   - Bot Fight Mode = ON                                   (Phase 5 §5)
#   - Custom firewall ruleset blocking Tor exits + bad ASNs (Phase 5 §4)
#   - HTTP ratelimit ruleset: /auth/* → 10 req/min/IP, 10m  (Phase 5 §3)
#
# Phase 5 §1 (orange-cloud proxy) was done during the Phase 4 cutover.
# Phase 5 §2 (verify origin-IP not leaked) is a verification — see
# verify-cf-phase5.sh.
# Phase 5 §6 (CF-Connecting-IP reaches backend) is wired by Caddyfile line 31
# and verified by verify-cf-phase5.sh.
# Phase 5 §7 (origin firewall to CF IPs only) lives in restrict-firewall-cf.sh
# and runs on the VPS.
#
# Required env vars (export before invoking, or pass via a one-off
# `env A=… B=… ./ops/setup-cf-waf.sh`):
#   CF_API_TOKEN  — API token with at least Zone:Read + Zone WAF:Edit +
#                   Zone Settings:Edit, scoped to geyam.com.
#                   Create at https://dash.cloudflare.com/profile/api-tokens
#                   using template "Edit zone WAF" + the Settings:Edit
#                   permission added.
#
# Optional env vars:
#   CF_ZONE       — defaults to "geyam.com". Override only if testing in a
#                   sibling zone.
#   CF_BAD_ASNS   — space-separated list of ASNs to block alongside Tor.
#                   Default is empty (Tor-only). Keep this conservative —
#                   blocking DO/OVH/AWS wholesale will lock out legitimate
#                   users. Add only ASNs you've personally confirmed are
#                   abusing your origin.
#
# Idempotent: discovers existing rulesets by name and PATCHes them instead
# of creating duplicates. Re-running is safe.
#
# Requires: curl, jq.

set -euo pipefail

: "${CF_API_TOKEN:?must export CF_API_TOKEN (Zone:Read + WAF:Edit + Settings:Edit on geyam.com)}"
: "${CF_ZONE:=geyam.com}"
: "${CF_BAD_ASNS:=}"

if ! command -v jq >/dev/null 2>&1; then
    echo "FATAL: jq not installed (apt-get install jq)" >&2
    exit 1
fi

API=https://api.cloudflare.com/client/v4
AUTH=(-H "Authorization: Bearer ${CF_API_TOKEN}" -H "Content-Type: application/json")

cf() {
    # cf METHOD PATH [JSON_BODY]
    local method=$1 path=$2 body=${3:-}
    if [[ -n "$body" ]]; then
        curl -sS -X "$method" "${API}${path}" "${AUTH[@]}" --data "$body"
    else
        curl -sS -X "$method" "${API}${path}" "${AUTH[@]}"
    fi
}

check_ok() {
    # check_ok JSON CONTEXT — exits non-zero if .success != true.
    local json=$1 ctx=$2
    if [[ "$(echo "$json" | jq -r '.success')" != "true" ]]; then
        echo "FATAL: ${ctx} failed:" >&2
        echo "$json" | jq -r '.errors // .' >&2
        exit 1
    fi
}

# -- 1. Discover zone id ------------------------------------------------------
echo "[1/4] Discovering zone id for ${CF_ZONE}..."
zones_json=$(cf GET "/zones?name=${CF_ZONE}")
check_ok "$zones_json" "zone lookup"
zone_id=$(echo "$zones_json" | jq -r '.result[0].id // empty')
if [[ -z "$zone_id" ]]; then
    echo "FATAL: zone ${CF_ZONE} not found on this API token's account" >&2
    exit 1
fi
echo "      zone_id=${zone_id}"

# -- 2. Bot Fight Mode --------------------------------------------------------
# Note: /zones/{id}/bot_management requires a dedicated "Bot Management:Edit"
# token permission that isn't covered by Zone WAF:Edit or Zone Settings:Edit.
# If the call returns Authentication error, fall through — user toggles it
# manually in the dashboard (Security → Bots → Bot Fight Mode = ON).
echo "[2/4] Enabling Bot Fight Mode..."
bot_json=$(cf PUT "/zones/${zone_id}/bot_management" '{"fight_mode": true}')
if [[ "$(echo "$bot_json" | jq -r '.success')" == "true" ]]; then
    echo "      Bot Fight Mode: $(echo "$bot_json" | jq -r '.result.fight_mode')"
else
    err_msg=$(echo "$bot_json" | jq -r '.errors[0].message // "unknown"')
    echo "      SKIPPED: ${err_msg}"
    echo "      → flip manually: dash.cloudflare.com → ${CF_ZONE}"
    echo "        Security → Bots → Bot Fight Mode → ON"
fi

# -- 3. Custom firewall ruleset (Tor + optional ASNs) -------------------------
echo "[3/4] Configuring custom firewall ruleset (Tor + bad ASNs)..."
# Cloudflare encodes Tor exit nodes as ISO country code "T1" (pseudo-code).
# The current expression field is ip.src.country; ip.geoip.country is the
# older alias. Same story for ASN: ip.src.asnum is current.
fw_expr='(ip.src.country eq "T1")'
if [[ -n "$CF_BAD_ASNS" ]]; then
    asn_set=$(echo "$CF_BAD_ASNS" | tr ' ' '\n' | awk 'NF' | paste -sd' ' -)
    fw_expr="(ip.src.country eq \"T1\") or (ip.src.asnum in {${asn_set}})"
fi
fw_rules=$(jq -n --arg expr "$fw_expr" '{
    name: "geyam-firewall-custom",
    kind: "zone",
    phase: "http_request_firewall_custom",
    rules: [{
        action: "block",
        expression: $expr,
        description: "geyam: block Tor exits + curated bad ASNs",
        enabled: true
    }]
}')
rulesets_json=$(cf GET "/zones/${zone_id}/rulesets")
check_ok "$rulesets_json" "rulesets list"
fw_id=$(echo "$rulesets_json" | jq -r \
    '.result[] | select(.phase=="http_request_firewall_custom" and .kind=="zone") | .id' \
    | head -1)
if [[ -n "$fw_id" ]]; then
    echo "      updating existing ruleset id=${fw_id}"
    out=$(cf PUT "/zones/${zone_id}/rulesets/${fw_id}" "$fw_rules")
else
    echo "      creating new firewall ruleset"
    out=$(cf POST "/zones/${zone_id}/rulesets" "$fw_rules")
fi
check_ok "$out" "firewall ruleset apply"
echo "      firewall expression: ${fw_expr}"

# -- 4. Rate-limit ruleset on /auth/* ----------------------------------------
echo "[4/4] Configuring rate-limit ruleset (/auth/* 10/min/IP)..."
rl_rules=$(jq -n '{
    name: "geyam-ratelimit",
    kind: "zone",
    phase: "http_ratelimit",
    rules: [{
        action: "block",
        ratelimit: {
            # cf.colo.id is required by the API — rate counters live per
            # colocation. ip.src is the actual rate-limit key; cf.colo.id
            # just satisfies the counter-locality constraint.
            characteristics: ["ip.src", "cf.colo.id"],
            # Free tier rate limit only permits period: 10 (seconds) and
            # mitigation_timeout: 10. 2 req / 10s ~ 12 req/min, the
            # closest fit to the plan target of "10 req/min/IP". Net
            # effect with 10s timeout is a hard 2/10s cap, since offenders
            # re-trigger immediately on next breach. Upgrade Pro+ for
            # 60s windows + longer block durations.
            period: 10,
            requests_per_period: 2,
            mitigation_timeout: 10
        },
        expression: "(starts_with(http.request.uri.path, \"/auth/\"))",
        description: "geyam: ~10 req/min/IP on /auth/* (2/10s), 10m block on breach",
        enabled: true
    }]
}')
rl_id=$(echo "$rulesets_json" | jq -r \
    '.result[] | select(.phase=="http_ratelimit" and .kind=="zone") | .id' \
    | head -1)
if [[ -n "$rl_id" ]]; then
    echo "      updating existing ruleset id=${rl_id}"
    out=$(cf PUT "/zones/${zone_id}/rulesets/${rl_id}" "$rl_rules")
else
    echo "      creating new ratelimit ruleset"
    out=$(cf POST "/zones/${zone_id}/rulesets" "$rl_rules")
fi
check_ok "$out" "ratelimit ruleset apply"

echo
echo "Done. Next steps:"
echo "  1. From the VPS as root:  sudo bash ops/restrict-firewall-cf.sh"
echo "  2. From the laptop:       bash ops/verify-cf-phase5.sh"
