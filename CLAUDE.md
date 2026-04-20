# GEYAM — Stage 2

## What This Is

Multi-tenant Smart POS SaaS for packaged food. Stage 2 evolves the Stage 1 single-shop MVP (same repo, same folder) into a multi-tenant platform where each shop's owner signs in with real Gmail (2FA via Google), creates cashier accounts (PIN-only login), trains a per-tenant YOLO model by filming products, and runs a full retail flow — inventory, purchase orders, DuitNow QR payments via Billplz, email receipts, rich dashboard — with strict per-tenant data isolation. Full spec lives in `docs/PLAN_STAGE2.md` — always consult it before making architectural decisions.

## Project History

- `docs/PLAN_STAGE1.md` — original MVP plan (kept here as reference, frozen)
- `docs/PLAN_STAGE2.md` — current plan, extends Stage 1
- This repo is a duplicate of the Stage 1 `geyam\` folder, taken at Stage 1 final state. The original `geyam\` folder is preserved separately as the backup demo.

## Tech Stack

- Backend: Python 3.12, FastAPI, SQLAlchemy (async), Alembic, RQ + Redis
- Database: PostgreSQL 16 (row-level tenant isolation via SQLAlchemy event hook)
- ML: YOLOv8 (Ultralytics, per-tenant weights), MediaPipe EfficientDet-Lite0, OpenAI gpt-4o-mini (vision fallback, quota-capped)
- LLM Q&A: Ollama phi3:mini (local)
- Auth: Google OAuth for owners, bcrypt PIN for cashiers, JWT sessions (owner 24h / cashier 12h + 30-day refresh)
- Payments: Billplz DuitNow QR (per-tenant creds, Fernet-encrypted at rest, sandbox/production toggle)
- Email: Resend via noreply@geyam.com (SPF+DKIM on Cloudflare DNS — nameservers are Cloudflare; Hostinger still hosts static site)
- Frontend: Flutter (web + Android), fl_chart, dark-mode-default Stage 1 palette. **Phase 13 UI must match `designreference/light mode.png` and `designreference/dark mode.webp`** — gradient KPI cards, tabbed top nav, glowing violet/teal icon tiles, section cards with subtle borders. Full visual vocabulary in `docs/PLANstage2.md` → "Design Reference — Phase 13 Flutter UI".
- Infra: Docker Compose, Cloudflare Tunnel → laptop :9000; Hostinger serves Flutter web build

## Dev Environment

- OS: Windows (WSL2 + Docker Desktop). Use forward slashes inside containers; backslashes only in Windows Explorer / PowerShell.
- Repo root: `C:\Programming (Local)\FYP Claude\geyam-stage2\` (duplicated from `geyam\`, fresh git init).
- Stage 1 backup at `C:\Programming (Local)\FYP Claude\geyam\` — frozen, never edit. Used as fallback demo if Stage 2 breaks.
- Stage 2 reorganizes files gradually: flat Stage 1 layout → `backend/`, `frontend/`, `infra/`, `scripts/`, `uploads/`, `docs/`. Claude Code handles the moves during Phase 1.
- Existing Cloudflare Tunnel already points at `localhost:9000` — keep this port, don't change it.

## Architecture (one paragraph)

geyam.com (Hostinger static) serves the Flutter web build and a landing page with a Login button top-right (web only — mobile/Android skip straight to login). All API calls go to api.geyam.com which is a Cloudflare Tunnel to the laptop's FastAPI on :9000. The laptop runs five containers: db (Postgres), redis, backend (FastAPI + WebSocket), worker (RQ for training, receipt email, report export), scheduler (auto-void every 60s), and backup (nightly pg_dump with 7-day retention). Uploads live on local disk under `./uploads/<tenant_id>/`. Every table except `tenants` carries `tenant_id` and every query is filtered by a SQLAlchemy event hook that reads `tenant_id` from the JWT.

## Key Endpoints

- `POST /auth/google` (owner) · `POST /auth/staff/login` (cashier PIN) · `POST /auth/refresh`
- `POST /detect` (cascade: YOLO → MediaPipe → OpenAI; response includes `source` field: `"yolo" | "mediapipe" | "openai"`)
- `POST /train/video` + `POST /train/run` (batched, per-tenant lock)
- `POST /transaction` → `POST /transaction/{id}/qr` → `POST /payments/webhook`
- `POST /transaction/{id}/override-void` (owner-only paid TX void with reason)
- `GET /transactions` + `GET /transactions/{id}` (drill-down with webhook payload)
- `GET /dashboard` + `GET /reports` + `POST /ask` (Ollama phi3:mini)
- `WS /ws` (per-tenant channel for auto-void banners, low-conf alerts)

## Current Phase

**Phase 0 — External setup in progress** (DNS, Google Cloud, Billplz sandbox, Resend, Ollama pull, Fernet key). Start Phase 1 only after `.env` is fully populated.

## Migration Posture (Stage 1 → Stage 2)

- Keep Stage 1 code functional during the transition; do not delete files until their Stage 2 replacement is tested.
- Existing Stage 1 shop data becomes the "default tenant" via a one-shot backfill migration.
- Cloudflare Tunnel, Hostinger domain, `.env` secrets already configured — reuse, don't recreate.

## Commands

```bash
# Boot infra
docker compose up -d db redis

# Apply migrations (runs on backend container start too)
docker compose run --rm backend alembic upgrade head

# Start backend + worker + scheduler
docker compose up -d backend worker scheduler

# Create a tenant
docker compose run --rm backend python scripts/create_tenant.py \
  --email brianchenjunhao@gmail.com --handle brianchenjunhao --name "Brian's Shop"

# Seed demo tenant
docker compose run --rm backend python scripts/seed_demo_tenant.py

# Health check (local)
curl http://localhost:9000/health

# Expose to internet (tunnel already points at :9000 from Stage 1)
cloudflared tunnel --url http://localhost:9000 run geyam

# Flutter web build (for Hostinger upload)
cd frontend/geyam_pos && flutter build web --release

# Flutter Android APK (sideload)
cd frontend/geyam_pos && flutter build apk --release

# Switch to Stage 1 backup demo (stop Stage 2 first)
docker compose down
cd "C:\Programming (Local)\FYP Claude\geyam"
uvicorn main:app --host 0.0.0.0 --port 9000

# Back to Stage 2 development
cd "C:\Programming (Local)\FYP Claude\geyam-stage2"
docker compose up -d

# Tests
docker compose run --rm backend pytest -xvs
```

## Rules

1. **Consult `docs/PLAN_STAGE2.md` before implementing anything new.** All architecture, schema, API, and flow decisions are locked there. If the plan and this file disagree, the plan wins.
2. **Phase 2 tenant isolation is the gate.** Do not build Phase 3+ until the integration test "Tenant A session cannot read Tenant B rows" is green.
3. **Hardcode first, abstract later.** Get the happy path working end-to-end before adding configuration, retries, or clever abstractions.
4. **Git commit after every working step.** Commit messages reference the phase + step number (e.g. `phase-1 step-3: alembic init`). This repo is the Stage 2 fork — the Stage 1 `geyam\` folder is never modified.
5. **Test every endpoint with curl before touching Flutter.** Webhooks first, UI last.
6. **Never log or commit secrets.** `.env`, `FERNET_KEY`, Billplz creds, JWT secret, Google OAuth secret, Resend API key must never land in git. `.env.example` with placeholders is fine.
7. **When stuck more than 10 minutes, stub the dependency and move on** — leave a TODO with the phase + step number.
8. **Never delete a working Stage 1 file until its Stage 2 replacement is tested.** Keep the old file next to the new one during the transition, then remove in a separate commit.