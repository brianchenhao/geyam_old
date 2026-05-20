# Phase 5 — Cloudflare edge hardening (runbook)

Applies the seven Phase 5 steps from `docs/PLAN-stage3-Geyam.md`. Three
scripts in `ops/` do the heavy lifting; one Cloudflare API token is the only
new credential needed.

## Pre-flight

Confirm Phase 4 cutover is still healthy:

```sh
curl -fsS https://api.geyam.com/docs | head -c 200
ssh deploy@168.144.46.142 "docker ps --format 'table {{.Names}}\t{{.Status}}'"
```

Both should look unchanged from the post-cutover state. If anything looks
wrong, fix Phase 4 first — don't layer WAF rules on a broken origin.

## Cloudflare API token

Create a fresh token at <https://dash.cloudflare.com/profile/api-tokens>:

- Template: **Edit zone WAF**
- Add permission: **Zone → Zone Settings → Edit** (for Bot Fight Mode)
- Zone Resources: **Include → Specific zone → geyam.com**
- TTL: 24 hours is enough for the rollout. Token can be deleted afterwards.

Export it locally before running the script:

```sh
export CF_API_TOKEN="<paste-token>"
```

Token never leaves your shell session — `setup-cf-waf.sh` consumes it
through env, doesn't persist it anywhere.

## 1. Configure CF rules (Bot Fight + WAF + rate-limit)

From the laptop (anywhere with curl + jq + the token):

```sh
bash ops/setup-cf-waf.sh
```

Applies, idempotently:

- **§3** `/auth/*` rate limit: 10 req/min/IP, 10-minute block on breach
- **§4** Custom firewall ruleset: blocks `ip.geoip.is_tor`. To extend with
  curated ASNs later: `CF_BAD_ASNS="13335 16509" bash ops/setup-cf-waf.sh`
- **§5** Bot Fight Mode = ON

Re-running is safe: existing rulesets are updated in place, not duplicated.

## 2. Lock origin firewall to CF IPs

On the VPS as root:

```sh
ssh deploy@168.144.46.142
sudo bash /opt/geyam/ops/restrict-firewall-cf.sh
```

This script:

- Fetches CF IP ranges from `cloudflare.com/ips-v4` and `/ips-v6`
- Removes the existing wide-open `:80` and `:443` UFW rules
- Adds per-CIDR `ALLOW` rules so only CF can reach the origin
- Leaves `:22` (SSH) untouched — key-only auth + fail2ban handle SSH

If the ops/ directory on the VPS is out of date, sync first:

```sh
scp ops/restrict-firewall-cf.sh deploy@168.144.46.142:/opt/geyam/ops/
```

## 3. Verify

From the laptop:

```sh
bash ops/verify-cf-phase5.sh
```

Checks:

- **§2** Origin IP not in response headers or error bodies
- **§3** `/auth/*` rate limit triggers within 12 rapid requests
- **§5** Bot Fight Mode reachable (`cf-mitigated` header or `cf-ray` proves
  CF is in front and processing UA-based decisions)
- **§7** Direct-IP request to `168.144.46.142:443` refused

Tests not run automatically:

- **§1** Orange-cloud proxy — done at cutover. `dig +short api.geyam.com`
  should still return Cloudflare anycast IPs (104.21.x.x / 172.67.x.x range),
  not 168.144.46.142.
- **§4** Tor block — needs a Tor exit IP to send from. Test from any
  torsocks-enabled host: `torsocks curl -v https://api.geyam.com/docs`
  should be blocked at the CF edge with a 403 page.
- **§6** CF-Connecting-IP reaches FastAPI — wired by `Caddyfile:31`. To
  confirm empirically:
  ```sh
  ssh deploy@168.144.46.142 \
    "docker logs --tail 50 geyam-caddy | grep -o 'CF-Connecting-IP[^,]*'"
  ```
  Real client IPs (not CF's own ranges) should appear. Full verification
  lands at Phase 7 when Antsilk's PostgresSink writes them to
  `antsilk_events.ip_address`.

## Rollback

Each step is independently reversible.

- **Rate limit / firewall ruleset / Bot Fight Mode**: dashboard →
  Security → WAF → Custom Rules / Rate Limiting Rules → toggle off.
  Or via API: delete the rulesets `setup-cf-waf.sh` created (their `name`
  fields begin with `geyam-`).
- **Origin firewall**: `sudo bash /opt/geyam/ops/setup-firewall.sh` resets
  UFW to the Phase 1 baseline (22/80/443 open to anywhere).
- **Bot Fight Mode**: `curl -X PUT .../zones/<id>/bot_management -d
  '{"fight_mode": false}'`.

## Common gotchas

- **Rate limit ate my own traffic.** If you're hammering `/auth/google`
  while testing, you'll trip your own rule. Block lasts 10 min by default.
  Wait it out or temporarily widen `requests_per_period` while iterating.
- **`restrict-firewall-cf.sh` cut me off from the origin.** That's exactly
  what it should do for non-CF sources. If you need direct origin access
  for debugging (e.g. SSH tunnel to Postgres), `ssh` over 22 still works —
  use that, don't reopen 443 to the world.
- **`cf-mitigated` not present on free tier.** Bot Fight on free doesn't
  always emit the header. Falling back to `cf-ray` presence is OK; verify
  the toggle in dashboard if in doubt.
- **CF IP ranges changed.** Rare (last expansion 2023) but possible.
  Symptom: legitimate users get connection refused. Re-run
  `restrict-firewall-cf.sh` to pull the current list.
