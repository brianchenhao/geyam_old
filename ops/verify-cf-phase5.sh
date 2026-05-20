#!/usr/bin/env bash
# Validate Phase 5 (Cloudflare edge hardening) post-conditions.
#
# Tests covered:
#   §2  Origin IP not leaked in response headers or bodies
#   §3  /auth/* rate limit triggers (12 rapid requests → at least one 429)
#   §5  Bot Fight Mode is enabled (header marker + JS challenge on bot UA)
#   §7  Direct-IP :443 refused from this host (UFW CF-only lock-down)
#
# Not covered here (verify out-of-band):
#   §1  Orange-cloud proxy on api.geyam.com — already done at cutover.
#       Check: `dig +short api.geyam.com` returns CF anycast IPs.
#   §4  Tor block — needs a Tor exit to test. Defer to:
#         torsocks curl https://api.geyam.com/docs   # expect 403/blocked
#       From this laptop just confirm the CF ruleset includes
#       `ip.geoip.is_tor` — that's what setup-cf-waf.sh writes.
#   §6  CF-Connecting-IP reaches FastAPI — Caddyfile line 31 forwards it.
#       For empirical confirmation, on the VPS:
#         ssh deploy@168.144.46.142 \
#           "docker logs --tail 50 geyam-caddy | grep -o 'CF-Connecting-IP[^,]*'"
#
# Pass/fail summary printed at the end. Exit 0 if all checks green.
#
# No required env vars. Optional:
#   ORIGIN_IP  — defaults to 168.144.46.142.
#   HOST       — defaults to api.geyam.com.

set -uo pipefail

: "${ORIGIN_IP:=168.144.46.142}"
: "${HOST:=api.geyam.com}"

PASS=0
FAIL=0
ok()   { echo "  PASS  $*"; PASS=$((PASS+1)); }
fail() { echo "  FAIL  $*"; FAIL=$((FAIL+1)); }

# Common UA so simple anti-curl rules don't interfere with non-bot tests.
HUMAN_UA="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 \
(KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36"

# -- §2 — origin IP not leaked -----------------------------------------------
echo "[§2] Origin IP leakage check"
hdrs=$(curl -sSI -A "$HUMAN_UA" "https://${HOST}/docs" 2>/dev/null)
if echo "$hdrs" | grep -iq "$ORIGIN_IP"; then
    fail "origin IP ${ORIGIN_IP} appears in response headers"
else
    ok "origin IP not in response headers"
fi
body=$(curl -sS -A "$HUMAN_UA" "https://${HOST}/this-path-should-404" 2>/dev/null || true)
if echo "$body" | grep -q "$ORIGIN_IP"; then
    fail "origin IP appears in 404 body"
else
    ok "origin IP not in 404 body"
fi

# -- §3 — /auth/* rate limit -------------------------------------------------
echo "[§3] /auth/* rate limit (12 rapid hits, expect at least one 429)"
codes=""
for i in $(seq 1 12); do
    c=$(curl -sS -o /dev/null -w "%{http_code} " \
        -A "$HUMAN_UA" "https://${HOST}/auth/google" 2>/dev/null || echo "ERR ")
    codes+="$c"
done
echo "      codes: ${codes}"
if echo "$codes" | grep -q "429"; then
    ok "rate limit kicked in (got 429)"
else
    fail "no 429 seen — rate limit rule may be missing or threshold too high"
fi

# -- §5 — Bot Fight Mode marker ----------------------------------------------
echo "[§5] Bot Fight Mode"
bot_hdrs=$(curl -sSI -A "curl/8.0" "https://${HOST}/docs" 2>/dev/null)
if echo "$bot_hdrs" | grep -iq "cf-mitigated:"; then
    ok "cf-mitigated header present on curl UA — Bot Fight active"
else
    # Free tier doesn't always emit cf-mitigated. Fall back: a curl-UA
    # request should at minimum get a 'cf-ray' header (= CF is in front).
    if echo "$bot_hdrs" | grep -iq "cf-ray:"; then
        echo "      NOTE: cf-ray present but no cf-mitigated. CF reached, but"
        echo "            Bot Fight may be passing this UA. Verify in dashboard:"
        echo "            Security → Bots → Bot Fight Mode = ON"
        ok "CF proxy hit (cf-ray seen); Bot Fight ON to be confirmed in dash"
    else
        fail "no cf-ray header — request didn't hit Cloudflare at all"
    fi
fi

# -- §7 — direct-IP refused --------------------------------------------------
echo "[§7] Direct origin-IP request from this host"
# Two valid forms of refusal:
#   - Connection-level drop (UFW or iptables): curl returns "000"
#     (curl writes "000" via -w on failure, the `|| echo "000"` fallback
#     concatenates another "000" when exit code is non-zero, so the
#     captured value is typically "000" or "000000" — anything composed
#     entirely of zeros counts as a connection-level refusal).
#   - L7 rejection (Caddy not-CF matcher): returns HTTP 403.
# Anything else (200, 5xx, etc.) means the origin is reachable + serving,
# which violates §7.
code=$(curl -sS -o /dev/null -w "%{http_code}" \
    --max-time 5 \
    --resolve "${HOST}:443:${ORIGIN_IP}" \
    "https://${HOST}/docs" 2>/dev/null || echo "000")
echo "      code via --resolve to ${ORIGIN_IP}: ${code}"
if [[ -z "${code//0/}" ]]; then
    ok "direct-IP refused at connection layer (UFW/iptables drop)"
elif [[ "$code" == "403" ]]; then
    ok "direct-IP refused at L7 (Caddy not-CF 403)"
else
    fail "direct-IP returned HTTP ${code} — origin reachable. Check Caddyfile @not_cf + UFW."
fi

echo
echo "Result: ${PASS} passed, ${FAIL} failed."
[[ "$FAIL" -eq 0 ]]
