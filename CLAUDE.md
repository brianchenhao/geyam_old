# Geyam

Smart POS SaaS for packaged-food shops in Malaysia. Multi-tenant, single-VPS deployment.
This is a Final Year Project (FYP) — Chapter 5 (`SystemDevelopment`) and Chapter 6
(`TestingAndEvaluation`) drafts live in `docs/chapters/`.

## What's where

```
backend/        FastAPI app — SQLAlchemy async, Alembic migrations, ultralytics YOLO for
                menu-item detection, Billplz/Stripe payments, Resend receipts, Chenki LLM
                client for /ask. Entry: backend/main.py.
frontend/       Flutter app (`geyam_pos`) — cashier + owner POS, Google Sign-In, WebSocket
                tx broadcasts.
ops/            Production deployment — ops/docker-compose.yml, ops/Caddyfile, runbooks
                (CUTOVER.md, RESTORE.md), helper scripts (deploy.sh, backup.sh,
                restore-drill.sh, setup-rclone.sh, run-migrations.sh) plus the Phase 1 VPS
                bootstrap scripts.
docs/           Academic chapters + ALGORITHMS.md.
.github/        CI: builds backend image, pushes to ghcr.io/brianchenhao/geyam-backend
                on push to main or stage-3-phase-*.
docker-compose.yml   Local-dev stack (db on 5433, redis on 6380, backend on 9000, pgadmin
                on 5050). Distinct from ops/docker-compose.yml which is the production stack.
```

## Stage 3 architecture (Stage 2 was laptop-only)

```
Public → Cloudflare proxy + WAF → VPS in Singapore (DigitalOcean s-1vcpu-2gb)
                                       │
                              Caddy 2 (TLS via CF Origin Cert)
                                       │
                                  FastAPI / uvicorn
                                   │           │
                              Postgres 16   Redis 7
```

Backups: nightly `pg_dump -Fc` → Cloudflare R2 bucket `geyam-backups`,
30-day object lifecycle, weekly automated restore drill.

External LLM: Chenki on a Hugging Face Space (`chenki-llm.hf.space`), called from the
backend's `/menu/ask` route.

## Local development

```sh
docker compose up -d
# Backend at http://localhost:9000
# Swagger UI at http://localhost:9000/docs
# pgAdmin at http://localhost:5050 (admin@geyam.com / admin)
```

Migrations:
```sh
docker exec geyam-backend-1 alembic upgrade head
```

Tests:
```sh
docker exec geyam-backend-1 pytest
```

## Production deployment

Public hostname is `api.geyam.com` (Cloudflare-proxied). To pull the latest backend
image and restart on the VPS:

```sh
./ops/deploy.sh
```

For the full one-time cutover from laptop to VPS, see `ops/CUTOVER.md`.
For disaster recovery from R2 backup, see `ops/RESTORE.md`.

## Commit style (Stage 3 onwards)

Conventional Commits format `<type>(<scope>): <description>`. Lowercase imperative,
≤72-char subject.

Scope must be one of: `pos, orders, menu, auth, billplz, stripe, subscriptions, signup,
yolo, llm, antsilk, alerts, dashboard, migrations, ops, deploy, ci, deps, docs, release`.

**No AI attribution** — never add `Co-Authored-By`, "Generated with", or similar
trailers. Only allowed footers: `Closes #n`, `Fixes #n`, `Refs #n`, `BREAKING CHANGE:`.

Pushes go to `geyam_old` via direct URL — `git push https://github.com/brianchenhao/geyam_old.git <branch>:<branch>` — not `origin` (legacy mirror).

## Stage 3 status (2026-05-25)

| Phase | What | Status |
|---|---|---|
| 1 | VPS provisioning + hardening | Done |
| 2 | Database migration to VPS | Done (schema at alembic 0016, RLS deferred — Stage 2 has no DB RLS) |
| 3 | Offsite backup pipeline | Done (R2 + 30-day lifecycle + restore drill) |
| 4 | App migration (cutover) | Done (cutover executed 2026-05-19 ~23:33 KL) |
| 5 | Cloudflare edge hardening | Done (Tor block + ratelimit via CF API; Caddy L7 @not_cf for §7; UFW CF-only as defense-in-depth; Bot Fight Mode = manual dashboard toggle) |
| 6 | Monitoring + `/healthz` | Done (Healthchecks.io 4 checks + webhook → alerts.py; UptimeRobot on /healthz; Telegram+Resend dispatch; container log caps + host logrotate) |
| 7 | Antsilk WAF middleware | Done engineering 2026-05-25 (sqli/xss/path_traversal/rate_limit verified live; CF-Connecting-IP shim works); 7-day soak ends 2026-06-01 |
| 8 | Chenki LLM (replacing Ollama) | Done. Cashier `/menu/ask` via ChenkiClient singleton + warmup in lifespan. Owner `/ask` migrated 2026-05-27: keyword classifier picks 1 of 8 analytics tools, chenki summarises the JSON; `services/ollama_chat.py` deleted, ollama removed from compose + config. |
| 9 | Stripe billing | Routes + audit decorator + plan enforcement + Flutter banner implemented 2026-06-04. Pending: Stripe Dashboard setup (products + webhook), env vars, live-mode cutover. Runbook at `ops/PHASE9.md`. |
| 10 | Self-serve signup | Schema migrated (onboarding_state); routes pending |
| 11 | Pricing/landing page | Pending |
| 12 | Customer records | Optional, deferred |

## Authoritative project docs (not all tracked in git)

- `docs/PLAN-stage3-Geyam.md` — Stage 3 roadmap with locked decisions. Lives locally
  only (gitignored).
- `ops/CUTOVER.md` — Phase 4 cutover runbook (time-anchored, with rollback criteria).
- `ops/RESTORE.md` — disaster recovery runbook (distinct from the automated drill).
