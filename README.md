# Geyam

> **Multi-tenant Smart POS SaaS for packaged-food shops.** Built solo. Runs on a $14.40/month Singapore VPS.

Each shop's owner signs in with Google (2FA via Google), creates cashier accounts with PIN-only logins, and trains a per-tenant YOLOv8 model by filming products in their actual lighting. Cashiers point a phone at a tray; the system detects items, applies the per-tenant menu, takes DuitNow QR payment via Billplz, and emails receipts. Every table outside `tenants` carries `tenant_id` and is filtered by a SQLAlchemy event hook reading the JWT — one tenant cannot read another's data, full stop.

## Status

| Stage | What it covers | State |
|---|---|---|
| **Stage 1** | Single-shop MVP — YOLO + Postgres + Flutter, one operator | Complete |
| **Stage 2** | Multi-tenant rewrite — Google OAuth, row-level isolation, Billplz, dashboard, receipts | In progress on `main` |
| **Stage 3** | Production hardening, portfolio integration (Antsilk + Chenki), Stripe billing | Phase 1 done — see the `stage-3-phase-1` branch |

## Tech stack

| Layer | Choice |
|---|---|
| Backend | Python 3.12 · FastAPI · SQLAlchemy (async) · Alembic |
| Queue / cache | Redis · RQ |
| Database | PostgreSQL 16 · row-level tenant isolation via SQLAlchemy event hook |
| Vision cascade | YOLOv8 (per-tenant weights) → MediaPipe EfficientDet-Lite0 → OpenAI gpt-4o-mini |
| LLM Q&A | Ollama `phi3:mini` (Stage 2) → **Chenki** Hugging Face Space (Stage 3) |
| Auth | Google OAuth (owners) · bcrypt PIN (cashiers) · JWT sessions |
| Customer payments | Billplz DuitNow QR · per-tenant credentials, Fernet-encrypted at rest |
| Subscription billing | Stripe Subscriptions (Stage 3) |
| Frontend | Flutter (web + Android APK) · `fl_chart` |
| Hosting | DigitalOcean SGP1 Droplet · Docker Compose · Caddy (Stage 3) |
| Edge | Cloudflare proxy (WAF + DDoS) on `api.geyam.com` |
| Offsite backups | `pg_dump` → Cloudflare R2, 30-day retention, monthly restore drill |
| Security middleware | **Antsilk** (Stage 3) — custom Python WAF |

## Cost

**$14.40 / month total** for the full multi-tenant SaaS stack:

| Item | Cost |
|---|---|
| DigitalOcean Droplet — Basic Regular 2 GB / 1 vCPU / 50 GB SSD, SGP1 | $12.00 |
| DigitalOcean weekly backups | $2.40 |
| Cloudflare R2 backups · DNS · WAF | $0 |
| Hugging Face Space · Healthchecks.io · UptimeRobot · Resend · GitHub Actions | $0 |

## Companion projects

Geyam interlocks with two other Python projects shipping in parallel — together they're a three-piece portfolio:

- **Antsilk** — pip-installable Python WAF middleware. Provides the edge security layer Geyam's FastAPI backend was missing. A custom Postgres sink writes every blocked request straight into Geyam's main DB so WAF events are queryable alongside business data. Production integration lands in Stage 3 Phase 7.
- **Chenki** — pip-installable LLM client plus a Hugging Face Space. Replaces the local Ollama `phi3:mini` that ran the Stage 2 `/ask` route. Singleton client warmed on app startup to absorb HF Space cold starts. Production integration lands in Stage 3 Phase 8.

## Repository layout

```
backend/             FastAPI app — SQLAlchemy models, Alembic migrations, RQ workers, tests
frontend/geyam_pos/  Flutter app — Android APK + web build for Hostinger
docs/                Project documentation
deploy/              Stage-2 deployment scripts (Cloudflare Tunnel era)
docker-compose.yml   Local dev stack — db · redis · backend · worker · scheduler · backup
start.sh             Local dev entrypoint
```

Stage-3 VPS provisioning + hardening scripts live in `ops/` on the `stage-3-phase-1` branch.

## Author

Brian Chen — `brianchenjunhao@gmail.com`

Built as a final-year project.
