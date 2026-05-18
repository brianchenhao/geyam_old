# Geyam — Phase 4 cutover runbook

Moving production from the **laptop + Cloudflare Tunnel** to the **VPS + Cloudflare proxy**. Mirror of the plan's `Critical Feature Detail` section, adapted for the actual paths/commands in this repo.

Highest-risk step in Stage 3. Treat like a real ops procedure: have someone on call, do a dry run, do it at 03:00 KL on a non-Friday.

---

## Preconditions

Before scheduling cutover, all of the following must be true:

- [ ] Phases 1, 2, 3 complete on the VPS (see [`PLAN-stage3-Geyam.md`](../docs/PLAN-stage3-Geyam.md)).
- [ ] `ops/backup.sh` ran successfully last night → R2 has a recent dump.
- [ ] Backend image pushed to GHCR (`ghcr.io/brianchenhao/geyam-backend:latest`).
- [ ] CF Origin Certificate installed at `/opt/geyam/caddy/cf-origin.{crt,key}` on the VPS (mode 644 for the cert, 600 for the key, owned by root since caddy runs as root inside the container).
- [ ] `/opt/geyam/ops/docker-compose.yml` reflects the Phase 4 version (db + redis + backend + caddy).
- [ ] DNS for `api.geyam.com` is in Cloudflare's control (orange cloud may be off currently — Phase 5 toggles it).
- [ ] Buddy on call (text channel open).

---

## Timeline

### T-48h

Stand up VPS, run Phases 1-3 fully. Confirm the VPS Postgres has a recent (but not current) dump of laptop data via `./ops/run-migrations.sh` smoke + a manual pg_dump+restore.

### T-24h — Lower DNS TTL

Cloudflare → `geyam.com` → DNS → edit `api` record → **TTL = Auto** is fine if proxied, but if currently unproxied:

```
Set TTL = 60s
```

Verify:
```
dig api.geyam.com
# answer section should show TTL near 60
```

Wait at least one TTL cycle so any cached upstream resolvers drop the old IP fast.

### T-12h — Dry run with staging

Pick a throwaway hostname like `api-staging.geyam.com`, point its A record at the VPS public IP, ensure Caddy serves it.

End-to-end smoke:

```
# From laptop:
curl --resolve api-staging.geyam.com:443:168.144.46.142 \
    https://api-staging.geyam.com/docs
```

Should return 200. If not, debug **now**, not at T+0.

### T-1h — Final go/no-go

- [ ] Was last night's `backup.sh` cron run successful? (`tail /var/log/geyam-backup.log`)
- [ ] Is `geyam-db` on VPS healthy? (`docker ps | grep geyam-db`)
- [ ] Is the backend image current? (`docker pull ghcr.io/brianchenhao/geyam-backend:latest` should show "up to date")
- [ ] Are tenant Slack/Telegram channels notified of the planned 5-10 min downtime?

If anything is red — **abort, reschedule.** No partial cutovers.

### T+0 — Stop laptop backend

```
# On the laptop:
docker compose stop backend worker scheduler
# Laptop DB stays up briefly to serve in-flight reads.
```

From this moment, **writes are refused**.

### T+1m — Final delta sync

```
# Laptop → /tmp:
docker exec geyam-db-1 pg_dump -U pos_user --no-owner -Fc geyam > /tmp/final.dump
ls -la /tmp/final.dump

# SCP to VPS:
scp /tmp/final.dump deploy@168.144.46.142:/tmp/final.dump

# rsync the data dirs (these aren't in pg_dump):
rsync -av --delete ./backend/uploads/        deploy@168.144.46.142:/opt/geyam/uploads/
rsync -av --delete ./backend/ml_models/      deploy@168.144.46.142:/opt/geyam/ml_models/
rsync -av --delete ./backend/training_data/  deploy@168.144.46.142:/opt/geyam/training_data/
```

### T+3m — Restore on VPS

```
ssh deploy@168.144.46.142

# Stop backend so no one writes during restore:
docker compose -p geyam -f /opt/geyam/ops/docker-compose.yml stop backend

# Drop+recreate via the existing db:
docker cp /tmp/final.dump geyam-db:/tmp/final.dump
docker exec geyam-db psql -U pos_user -d postgres -c "DROP DATABASE IF EXISTS geyam;"
docker exec geyam-db psql -U pos_user -d postgres -c "CREATE DATABASE geyam;"
docker exec geyam-db pg_restore -U pos_user --no-owner -d geyam /tmp/final.dump
docker exec geyam-db rm /tmp/final.dump

# Re-apply Stage 3 migrations the laptop dump doesn't have (0011-0016):
/opt/geyam/ops/run-migrations.sh

# Bring backend back:
docker compose -p geyam -f /opt/geyam/ops/docker-compose.yml --env-file /opt/geyam/.env.production up -d backend

# Watch boot logs:
docker logs -f geyam-backend
```

Look for: alembic up to date, uvicorn `Application startup complete`, no tracebacks.

### T+5m — Smoke test the new origin

From the laptop, bypass DNS by resolving manually:

```
curl --resolve api.geyam.com:443:168.144.46.142 -k https://api.geyam.com/docs
# Expect 200. -k accepts the self-signed-from-our-POV CF Origin Cert when bypassing DNS.
```

If 200: proceed. If not: **rollback** (see below).

### T+6m — Flip DNS

Cloudflare → `geyam.com` → DNS → `api` record → change content to `168.144.46.142`. Make sure orange cloud is **OFF** for now (Phase 5 turns it on later). Click Save.

### T+8m — Verify from a real external network

From your phone (cellular, not WiFi) or `dig` on a remote machine:

```
dig api.geyam.com +short
# should return 168.144.46.142 (not the old Tunnel target)

curl https://api.geyam.com/docs
# should return 200 via VPS
```

### T+10m — Announce cutover complete

Post in tenant channels: *"VPS migration complete. If you see anything unusual, ping me."*

---

## Post-cutover

### T+15m — Real end-to-end test

Open the Flutter app, do a real test transaction: login → scan item → pay Billplz sandbox → receipt email arrives.

### T+30m — Spot-check antsilk events

Once Phase 7 is live this matters more, but at minimum:

```
docker exec geyam-db psql -U pos_user -d geyam -c "SELECT COUNT(*), MAX(timestamp) FROM antsilk_events;"
```

### T+1h — Monitoring sanity

If Phase 6 is live: Healthchecks.io heartbeats green. Otherwise: tail `/var/log/caddy/access.log` for 5 minutes, confirm no flood of 5xx.

### T+24h — Begin decom

If quiet for 24 hours, **do not delete laptop data yet**. Just decommission the laptop Cloudflare Tunnel:

```
# Laptop:
cloudflared tunnel delete <tunnel-name>  # or stop the systemd service
```

The laptop Postgres + uploads remain as a hot fallback for 7 more days.

### T+7d — Archive laptop data

If still no incidents:

```
# Laptop: archive then optionally wipe
docker exec geyam-db-1 pg_dump -U pos_user --no-owner -Fc geyam > ./backups/laptop-final-$(date +%Y%m%d).dump
# Move that file somewhere safe (laptop external drive, R2 cold-tier, etc.).
# Then you can `docker compose down -v` to free the laptop's volumes.
```

---

## Rollback

At any time **before T+24h**, if you see:

- Postgres errors that aren't fixable in 10 minutes
- Antsilk false-positives blocking real tenants
- Missing uploads (404s on previously-working images)
- DNS resolution failures from the tenant side

**Rollback** = flip DNS back to the laptop CF Tunnel target, restart laptop FastAPI, investigate the VPS at leisure.

```
# In Cloudflare DNS: edit api → set back to the old Tunnel CNAME/target.
# On laptop:
docker compose up -d backend worker scheduler
```

This is exactly why the laptop data stays hot for 7 days.

---

## Don'ts (pre-emptive)

- **Do NOT** cutover on a Friday or before a public holiday weekend.
- **Do NOT** cutover within 7 days of your viva / submission deadline.
- **Do NOT** skip the T-12h dry run with `api-staging`.
- **Do NOT** delete laptop data on day 1 — the 7-day window is the whole rollback insurance.
