# GEYAM — Comprehensive Project Overview

> Audience: FYP examiners and supervisor.
> Purpose: a reference document distilling the full GEYAM system — problem, stack, architecture, and every meaningful module — into one place so the written report can cite it precisely.
> Source of truth: `docs/PLANstage2.md` (locked Stage-2 plan), the FastAPI backend under `backend/`, the Flutter app under `frontend/geyam_pos/`, and `CLAUDE.md` (operator guide). Where the plan and the code disagree, this document favours the code that actually ships.

---

## Table of Contents

1. Problem Statement & Motivation
2. Scope — In / Out
3. Tech Stack and the Rationale for Each Choice
4. High-Level Architecture
5. Multi-Tenant Isolation (the safety gate)
6. Database Schema (every table)
7. Backend Routers (every endpoint)
8. Backend Services (every module)
9. ML / Computer-Vision Pipeline
10. Payments, Receipts, and Email
11. Background Jobs, Scheduler, and WebSockets
12. Flutter App — Screens, Widgets, State
13. Infrastructure, Deployment, and DNS
14. Testing Strategy
15. Risks, Failure Modes, and Mitigations
Appendix A — Repository Layout
Appendix B — Key Design Decisions Glossary

---

## 1. Problem Statement & Motivation

Small and medium packaged-food shops in Malaysia face three compounding operational pains. First, manual checkout is error-prone and slow: cashiers type SKUs, mis-scan barcodes, or argue prices when labels fall off. Second, inventory visibility is usually a spreadsheet that drifts from reality within a week, so owners discover stock-outs only when a customer is already at the counter. Third, payment reconciliation across cash, QR, and e-wallet is a manual end-of-day ritual that frequently loses money to unrecorded voids and mismatched deposits.

Off-the-shelf POS products (e.g., Loyverse, StoreHub) address the last two pains well but are single-tenant in the sense relevant here: each deployment is bolted to one shop, the machine-vision features — when they exist — are pre-trained on western product catalogues, and the QR-payment reconciliation is tied to one acquirer. A Malaysian convenience-food shop selling mamak-aisle snacks has no fine-tuned detector covering its catalogue, and adding one requires either sending photos to a vendor or subscribing to a SaaS plan priced for chains.

GEYAM is a multi-tenant Smart-POS SaaS designed around three commitments derived from those pains:

- Each shop gets its own YOLOv8 detector trained on its own short phone videos, no data leaves the tenant boundary unless the vision cascade escalates to the OpenAI fallback (quota-capped).
- Each shop gets its own Billplz DuitNow QR credentials, stored encrypted, so reconciliation is unambiguous and money never flows through an intermediary account.
- Every table carries `tenant_id` and every ORM query is filtered by a SQLAlchemy event hook that reads the tenant from the JWT, so one buggy endpoint cannot leak data across shops.

The academic contribution is the end-to-end integration: a detection cascade (fine-tuned YOLO → MediaPipe shortlist → OpenAI vision fallback → manual), a training pipeline that an owner can run from a phone video with no ML knowledge, row-level tenant isolation proven by a dedicated integration test, and a Flutter client that runs unchanged on web and Android against one FastAPI backend exposed via a Cloudflare Tunnel. The engineering contribution is a working demo of how far a single laptop plus free tiers (Cloudflare, Hostinger static, Resend, Billplz sandbox) can carry a realistic multi-tenant POS.

---

## 2. Scope — In / Out

### In scope (locked in `docs/PLANstage2.md`)

- Google OAuth owner authentication with 2FA via Google; bcrypt-hashed 6-digit PIN login for cashiers; 5 JWT types covering access, refresh, signup, receipt, and admin tokens.
- Per-tenant YOLOv8n training from owner-uploaded phone videos; detection cascade with pHash cache and per-tenant OpenAI quota.
- Full retail flow: menu CRUD (with image + CSV bulk import), cart, Billplz DuitNow QR checkout, webhook-driven state changes, void + owner-override void, stock-movement ledger, receipt PDF with QR, email via Resend.
- Owner dashboard: KPI cards, time-series, pie / bar charts, staff performance, low-stock alerts, anomaly z-score, LLM Q&A over the same data using local Ollama `phi3:mini`.
- Multi-tenant isolation with SQLAlchemy `do_orm_execute` event hook, tenant-scoped file uploads under `uploads/<tenant_id>/`, tenant-scoped WebSocket channels, admin impersonation path for supervised support.
- Flutter client for web and Android: same codebase, `kIsWeb` gate for landing page vs direct login, responsive POS layout, dark-mode-default theme with gradient KPI cards.
- Docker Compose deployment: Postgres 16, Redis, FastAPI+WS, RQ worker, scheduler, nightly backup; Cloudflare Tunnel exposing the laptop at `api.geyam.com`; Hostinger static hosting the Flutter web build at `geyam.com`.

### Out of scope

- Purchase-order, supplier, and customer-loyalty tables (present in earlier migrations, explicitly dropped in migration `0009`).
- Kubernetes, managed Postgres, or any cloud-hosted backend — everything runs on the owner's laptop by design.
- Windows-installer native app, native iOS build, hardware receipt printer / cash drawer drivers.
- Cash-payment workflow beyond recording a `payment_method="cash"` transaction — there is no till reconciliation.
- Stock-take workflow, multi-location inventory, and any form of real supplier procurement.

---

## 3. Tech Stack and the Rationale for Each Choice

### 3.1 Backend language — Python 3.12

Python was chosen because the entire computer-vision stack (Ultralytics YOLOv8, MediaPipe, OpenAI client, OpenCV, Pillow) lives first-class in Python and because the author's deep-learning coursework produced reusable code. Python's async story is good enough for I/O-bound POS workloads, and the 3.12 interpreter gives us `tomllib`, fine-grained `typing` improvements, and better error messages.

### 3.2 Web framework — FastAPI

FastAPI pairs Pydantic v2 validation with async-native request handling and generates an OpenAPI schema for free. The Pydantic schemas double as the documentation the Flutter client reads against (`http://localhost:9000/docs`). The dependency-injection system (`Depends`) is the cleanest way in Python to wire per-request auth, tenant scoping, and DB sessions.

### 3.3 ORM and migrations — SQLAlchemy 2.x (async) + Alembic

SQLAlchemy 2.x is the only mature async ORM in Python with a real event system. The tenant-scope hook hangs off `do_orm_execute`; no other ORM (Tortoise, SQLModel direct, Piccolo) exposes an equivalent. Alembic is the standard migration tool; nine migrations were applied and are committed under `backend/alembic/versions/`.

### 3.4 Database — PostgreSQL 16

Postgres is the right default for multi-tenant SaaS: JSONB for audit metadata and webhook payloads, `SELECT ... FOR UPDATE` for per-tenant tx-number sequencing, partial indexes on `(tenant_id, created_at DESC)` for dashboard queries, and transactional DDL so a bad migration rolls back cleanly. Version 16 adds parallel VACUUM and incremental sort — small wins, but the reason is Postgres's defaults: strict typing, CHECK constraints, UNIQUE composites.

### 3.5 Queue and cache — Redis + RQ

RQ was chosen over Celery because the project has three job types (training, receipt email, maintenance) and Celery's broker abstraction, beats, and canvas primitives are overkill. RQ jobs are plain Python functions; failure handling is transparent; Redis also doubles as the pub/sub bus the WebSocket hub listens on (`geyam:ws` channel).

### 3.6 Machine vision — Ultralytics YOLOv8n, MediaPipe EfficientDet-Lite0, OpenAI gpt-4o-mini

YOLOv8n is small (≈6M parameters), trains in minutes on CPU for a shop's ~20-item catalogue, and Ultralytics ships a CLI and Python API good enough that `run_batch` is under 200 lines. MediaPipe EfficientDet-Lite0 is used as a category-level shortlister — if the YOLO head is uncertain, the MediaPipe label narrows the candidate set without a full re-train. OpenAI gpt-4o-mini is the last-resort vision fallback: strictly quota-capped (default 50 calls/tenant/day), with a perceptual-hash Redis cache (7-day TTL) to prevent the same photo costing money twice.

### 3.7 Local LLM — Ollama with `phi3:mini`

For the dashboard "Ask GEYAM" feature, using a cloud LLM would send sales data out of the shop, require per-token billing, and create a latency floor. `phi3:mini` is small enough to run on a laptop's CPU, is accurate enough for template-style questions ("what sold best last week?"), and is free. Ollama is reached from the backend container via Docker's `host.docker.internal` mapping.

### 3.8 Authentication — Google OAuth (owner) + bcrypt PIN (cashier), JWT HS256

Google OAuth offloads the password-and-2FA problem entirely and lines up with the realistic owner persona (a shop owner with a Gmail). Cashier PINs are six digits because cashiers work in front of customers and typing a long password is neither fast nor private; bcrypt with a modest cost factor keeps brute-force infeasible given lockout and short JWT lifetimes. JWT HS256 with a single server-side secret was chosen over RS256 because the backend is single-node; there is no KMS to rotate. Access tokens are 24h for owners, 12h for cashiers; refresh tokens are 30 days.

### 3.9 Payments — Billplz DuitNow QR

Billplz is the local acquirer best-documented for Malaysian DuitNow QR with a sandbox suitable for a student project, per-collection API keys usable as per-tenant credentials, and HMAC-SHA256 webhook verification. Credentials are encrypted at rest with Fernet in `tenant_settings`. A production/sandbox toggle lives in the same table.

### 3.10 Email — Resend via `noreply@geyam.com`

Resend was chosen over SendGrid because its free tier is generous, its API is one POST, and its React-style templating is not needed (receipts are ReportLab-rendered PDFs attached as bytes). DNS for `geyam.com` is on Cloudflare (grey-cloud, not proxy-orange, so SPF and DKIM propagate cleanly); Hostinger still hosts the static site.

### 3.11 Frontend — Flutter (web + Android)

Flutter delivers one codebase for mobile cashiers and web owners without a separate React SPA. `kIsWeb` gates web-only features (landing page, 1200px max-width wrapper). Flutter's web HTML/Canvas renderer ships a Progressive Web App good enough for desktop owners; the Android build runs on any phone the cashier has. Charts use `fl_chart`; state uses `provider` (kept deliberately thin — theme, connectivity, notifications only); HTTP is plain `http` + `http_parser` for multipart uploads; Google OAuth uses `google_sign_in`.

### 3.12 Infrastructure — Docker Compose, Cloudflare Tunnel, Hostinger

Docker Compose was chosen because every service (db, redis, backend, worker, scheduler, backup) is a single-node process and Compose is the simplest way to keep them alive with healthchecks and restart policies. Cloudflare Tunnel is the free, no-port-forwarding way to expose a laptop at a subdomain (`api.geyam.com`) with TLS provided by Cloudflare. Hostinger serves the static Flutter web build. All three together cost under RM20/month plus free tiers.

### 3.13 Why NOT a cloud database, Kubernetes, or a monorepo

A managed Postgres would add cost and a second operator (network, backups, access). Kubernetes would add two orders of magnitude of complexity for one laptop. A monorepo (Nx, Turbo) is unnecessary for two services (one Python, one Dart) with clean boundaries. The stack is deliberately conservative so that the FYP examiner can boot it with `docker compose up -d` in five minutes.

### 3.14 Dev environment — Windows + WSL2

The owner's laptop runs Windows; WSL2 + Docker Desktop gives us a Linux Docker host, fast file-system access to the Windows workspace, and the ability to share the `./uploads` volume between the host (for debugging) and containers. All commands in `CLAUDE.md` assume WSL2; the Cloudflare Tunnel binary runs in WSL alongside Docker.

---

## 4. High-Level Architecture

The runtime decomposes into three tiers.

At the edge, `geyam.com` (Hostinger static) serves the built Flutter web app plus a public landing page with a Login button top-right. Mobile Android users skip the landing page and open straight into the Flutter app's login screen because `kIsWeb` is false. All API calls from either platform hit `api.geyam.com`, which is a Cloudflare Tunnel pointing to the laptop's FastAPI on `localhost:9000`.

On the laptop, Docker Compose runs six long-lived services. `db` is Postgres 16 on port 5433, `redis` is Redis 7 on port 6380, `backend` is the FastAPI + WebSocket server on port 9000, `worker` is an RQ worker consuming jobs from two queues (`training` and `receipts`), `scheduler` is a lightweight loop that fires the auto-void job every 60 seconds, and `backup` runs `pg_dump` nightly with a 7-day retention window. A `pgadmin` container is optional.

Inside the backend process, the FastAPI `lifespan` starts a background asyncio task (`run_subscriber(hub)`) that pulls messages off the `geyam:ws` Redis pub/sub channel and forwards them to the in-process WebSocket hub. This is how the RQ worker and the scheduler push real-time events (training finished, transaction auto-voided, low-confidence detection) to connected clients without each service running its own WebSocket server.

Uploads — tenant logos, product images, training videos, receipt PDFs — live on local disk under `./uploads/<tenant_id>/` and are served by FastAPI's `StaticFiles` mount at `/uploads`. The tenant-id prefix in the path is the second enforcement layer for multi-tenant isolation: even a bug that returned the wrong path would be rejected by the tenant-scoped JWT check on any authenticated endpoint reading it.

```
                 ┌───────────────────────────────┐
   browsers ───▶ │  geyam.com  (Hostinger)       │
                 │  static landing + Flutter web │
                 └───────────┬───────────────────┘
                             │ XHR / WS
                             ▼
                 ┌───────────────────────────────┐
                 │  api.geyam.com  (Cloudflare)  │
                 │      Tunnel → :9000           │
                 └───────────┬───────────────────┘
                             │
                 ┌───────────▼───────────────────┐
                 │   laptop (Docker Compose)     │
                 │                               │
                 │  backend  ──┐        ┌──┐     │
                 │  worker   ──┤ Redis  │  │     │
                 │  scheduler──┘        └──┘     │
                 │  db (Postgres 16)             │
                 │  backup (pg_dump nightly)     │
                 └───────────────────────────────┘
```

---

## 5. Multi-Tenant Isolation (the safety gate)

Tenant isolation is the single most important property of the system — if it breaks, shop A can see shop B's sales — and the plan's Rule 2 states explicitly that Phase 3+ cannot proceed until the integration test "Tenant A session cannot read Tenant B rows" is green. It is implemented as four cooperating layers.

### 5.1 `tenant_id` on every table except `tenants`

Every ORM model except `Tenant` itself carries a non-null `tenant_id` foreign key to `tenants.id`, with `ON DELETE CASCADE` so deleting a tenant removes their data. The `Tenant` model is flagged with `__tenant_root__ = True`; the event hook uses that marker to skip filtering on the one table that must be globally queryable (without a tenant context an owner login would have nothing to look up).

### 5.2 `ContextVar` per request

`app/tenant_context.py` declares two `ContextVar`s — `_current_tenant_id: Optional[int]` and `_tenant_scope_bypass: bool` — so concurrent requests each carry their own tenant without global mutable state and without passing `tenant_id` through every function signature. The `get_tenant()` FastAPI dependency reads `tenant_id` from the decoded access-token JWT and calls `tenant_context.set_current_tenant_id(tenant_id)` before the handler runs.

### 5.3 SQLAlchemy `do_orm_execute` event hook

`app/database.py` registers a listener on the ORM session that fires for every SELECT (insert/update are implicitly tenant-safe because they use objects already loaded under the scope). The hook reads the current tenant from the `ContextVar` and appends `with_loader_criteria(Model, Model.tenant_id == tenant_id, include_aliases=True)` to the query plan for every mapped model that has a `tenant_id` column and is not marked `__tenant_root__`. The end result is that every owner or cashier endpoint is a straight-line Python function — no manual `WHERE tenant_id =` — and you cannot forget the filter because it is not your responsibility to write.

### 5.4 `bypass_tenant_scope()` for legitimate cross-tenant paths

Admin endpoints, CLI scripts, RQ jobs, and the nightly backup sometimes need to see across tenants. They wrap those calls in an `async with bypass_tenant_scope():` context manager which flips the second `ContextVar` so the hook short-circuits. The ContextVar is restored on exit even if the body raises. `scripts/clone_tenant.py`, the admin tenants-list, and the scheduler's auto-void worker are the main users.

### 5.5 The file system and WebSocket also carry the tenant

Per-tenant uploads live under `uploads/<tenant_id>/{products,logos,receipts,train}/...` and the URL the backend returns to the Flutter client is `/uploads/{tenant_id}/...`, so the path itself is auditable. The WebSocket hub keys connected clients by `tenant_id`, so a `broadcast(tenant_id, message)` call can only fan out within one tenant.

### 5.6 The proof

`backend/tests/test_tenant_isolation.py` writes rows for two synthetic tenants, sets the ContextVar to tenant A, runs the owner-visible SELECTs, and asserts none of tenant B's rows appear — and separately asserts that a `bypass_tenant_scope()` block does see both. This test is run in CI and is the green gate for Rule 2.

---

## 6. Database Schema (every table)

All tables use SQLAlchemy `DeclarativeBase`. `tenant_id` FKs use `ON DELETE CASCADE`. Timestamps are `TIMESTAMP WITH TIME ZONE`. The Alembic migrations that build this schema are listed in §11.

### 6.1 `tenants` (root, `__tenant_root__ = True`)
`id PK, handle VARCHAR(50) UNIQUE, name VARCHAR(100), owner_email VARCHAR(255) UNIQUE, is_active BOOL, created_at`. The `handle` is the URL-safe shop slug (e.g. `"demo"`) used to scope cashier login.

### 6.2 `users`
`id PK, tenant_id FK indexed, username VARCHAR(80), email VARCHAR(255), google_sub VARCHAR(255) UNIQUE, pin_hash VARCHAR(255), role ∈ {"owner","cashier"} (CHECK), is_active BOOL, created_at`. Composite `UNIQUE(tenant_id, username)` so two tenants can both have a `staff1`. `google_sub` is NULL for cashiers (they do not log in via Google), `pin_hash` is NULL for owners.

### 6.3 `tenant_settings`
One row per tenant, PK is `tenant_id`. Columns: Fernet-encrypted `billplz_api_key`, `billplz_collection_id`, `billplz_xsign_key`, `billplz_mode ∈ {"sandbox","production"}`, `logo_path`, `receipt_footer`, `shop_contact_email`, `shop_contact_phone`, `yolo_conf_threshold FLOAT DEFAULT 0.60`, `yolo_conf_minimum FLOAT DEFAULT 0.40`, `openai_daily_limit INT DEFAULT 50`, `training_locked_at DATETIME NULLABLE`, `updated_at`.

### 6.4 `menu_items`
`id PK, tenant_id FK, name VARCHAR(100), label VARCHAR(80), price NUMERIC(8,2), category VARCHAR(50), barcode VARCHAR(64), stock_qty INT, reorder_point INT DEFAULT 5, avg_cost NUMERIC(8,2), image_path TEXT, is_active BOOL, frame_count INT, created_at, updated_at`. Composite `UNIQUE(tenant_id, label)` and `UNIQUE(tenant_id, name)` so the detector class label and the human name can never collide inside a shop.

### 6.5 `training_jobs`
`id PK, tenant_id FK, menu_item_id FK ON DELETE SET NULL, video_path TEXT, status ∈ {"queued","training","done","failed"} (CHECK), frames_extracted INT, error TEXT, queued_at, started_at, finished_at`. The worker acquires a per-tenant lock (`training_locked_at` in `tenant_settings`) before running.

### 6.6 `model_versions`
`id PK, tenant_id FK, filename VARCHAR(255), num_classes INT, accuracy FLOAT, is_active BOOL, trained_at, notes TEXT`. Only one row per tenant is `is_active=True`; the worker flips the old active inactive and the new one active inside one transaction to avoid the hot-reload LRU cache loading a stale model.

### 6.7 `openai_usage`
`id PK, tenant_id FK, day DATE, calls INT`. Composite `UNIQUE(tenant_id, day)`. Incremented transactionally each time the OpenAI stage actually calls the API (cache hits do not count).

### 6.8 `transactions`
`id PK, tenant_id FK, tx_number VARCHAR(30), staff_id FK(users.id) NULLABLE, receipt_email VARCHAR(255) NULLABLE, total NUMERIC(10,2), payment_method VARCHAR(20) DEFAULT "qr", payment_ref VARCHAR(100), status ∈ {"pending","paid","voided"} (CHECK), created_at, paid_at, voided_at, voided_by FK(users.id) NULLABLE`. Composite `UNIQUE(tenant_id, tx_number)` — the per-day sequence `"20260423-001"` is unique within a tenant. `tx_number` is computed via `SELECT ... FOR UPDATE` on the last row for the day to avoid races.

### 6.9 `transaction_items`
`id PK, transaction_id FK CASCADE, menu_item_id FK NULLABLE, quantity INT, unit_price NUMERIC(8,2), confidence FLOAT NULLABLE, source VARCHAR(20) NULLABLE` ∈ {"yolo","mediapipe","openai","manual"}. NULLABLE `menu_item_id` preserves line items even if the menu item is later archived (soft-deleted).

### 6.10 `payments`
`id PK, tenant_id FK, transaction_id FK CASCADE, provider VARCHAR(20) DEFAULT "billplz", bill_id VARCHAR(100), bill_url TEXT, amount NUMERIC(10,2), state VARCHAR(20), paid_at, raw_payload JSONB, created_at`. The `raw_payload` stores the full webhook body for audit and drill-down.

### 6.11 `receipts`
`id PK, tenant_id FK, transaction_id FK CASCADE UNIQUE, pdf_path TEXT, emailed_to VARCHAR(255), emailed_at, resend_id VARCHAR(100), created_at`. The `UNIQUE` on `transaction_id` enforces one receipt row per transaction.

### 6.12 `stock_movements`
`id PK, tenant_id FK, menu_item_id FK NULLABLE, delta INT, reason ∈ {"sale","po_receive","adjust_damage","adjust_loss","adjust_theft","adjust_miscount","adjust_expired","adjust_other","void_restore"} (CHECK), ref_type VARCHAR(40), ref_id INT, note TEXT, created_by FK(users.id) NULLABLE, created_at`. Every stock change is append-only; the current `stock_qty` on `menu_items` is the running total but the ledger is authoritative.

### 6.13 `audit_logs`
`id BIGINT PK, tenant_id FK NULLABLE indexed, user_id FK NULLABLE, action VARCHAR(80), entity VARCHAR(40), entity_id INT, meta JSONB, created_at`. `tenant_id` is NULLABLE so pre-tenant events (admin dev-login, failed Google OAuth) can be recorded. `action` uses a dotted namespace (`"auth.login_success"`, `"tx.override_void"`, `"menu.update"`) so the audit screen can filter by prefix.

---

## 7. Backend Routers (every endpoint)

Fourteen routers are mounted in `main.py`. Each endpoint below lists its HTTP method, path, role, request and response shape, and purpose.

### 7.1 `admin.py` — admin-only tenant management
`POST /admin/dev-login` (public) — email must be in `ADMIN_EMAILS`; returns an admin JWT.
`GET /admin/tenants` (admin) — lists every tenant via `bypass_tenant_scope()`.
`POST /admin/tenants` (admin) — create a tenant plus the pre-created owner row.
`POST /admin/tenants/{tenant_id}/impersonate` (admin) — mint an owner-scoped access token for the target tenant; audited as `"admin.impersonate"`.

### 7.2 `auth.py` — Google OAuth, PIN login, refresh
`POST /auth/google` (public) — accepts Google `id_token` or `access_token`; verifies via Google; returns either a full `TokenOut` if the owner exists or a short-lived `signup_token` if they need onboarding.
`POST /auth/google/signup` (public) — exchanges `signup_token + shop_name + handle` for a full owner `TokenOut`; creates the tenant + owner user.
`POST /auth/staff/login` (public) — `{tenant_handle, username, pin}` → cashier `TokenOut`.
`POST /auth/refresh` (public) — takes a refresh token, returns a fresh access token.
`POST /auth/logout` (authed) — audits the logout; stateless.
`GET /auth/me` (authed) — returns the decoded JWT claims for the client.

### 7.3 `users.py` — cashier management (owner only)
`GET /users` — list cashiers in the tenant.
`POST /users` — create a cashier; PIN must be six digits and not trivially repeated; username auto-generated as `staffN.{tenant_handle}` if blank.
`PATCH /users/{user_id}` — reset PIN or toggle `is_active`.
`DELETE /users/{user_id}` — soft delete (sets inactive).

### 7.4 `settings.py` — tenant settings (owner only)
`GET /settings` — never returns the raw encrypted keys, only whether Billplz is configured.
`PATCH /settings` — partial update; API keys only touched if the incoming field is non-empty so a blank save does not wipe credentials.
`POST /settings/logo` — multipart image upload; stored under `uploads/<tenant_id>/logo.jpg`.

### 7.5 `menu.py` — catalogue CRUD (owner only, except GET)
`GET /menu?include_archived=bool` — list; archived items are soft-deleted (`is_active=False`).
`POST /menu` — create.
`PATCH /menu/{item_id}` — update.
`DELETE /menu/{item_id}` — soft-delete.
`POST /menu/{item_id}/restore` — un-archive.
`POST /menu/{item_id}/image` — multipart image upload; resized, saved under `uploads/<tenant_id>/products/{item_id}.jpg`.
`POST /menu/bulk` — multipart CSV upload; requires `name` and `price` columns; upserts by name; returns `{inserted, updated, errors[]}`.

### 7.6 `train.py` — model training (owner only)
`POST /train/video` — multipart video upload, max 100 MB, max 30 s duration (verified with ffprobe); the middle frame is extracted for an instant preview; `training_jobs` row created with `status="queued"`.
`POST /train/run` — enqueues `run_batch(tenant_id)` on the `training` RQ queue; rejects if `training_locked_at` is set.
`GET /train/jobs?status=` — paginated training-job list.
`GET /model/status` — the current active `ModelVersion` (filename, num_classes, accuracy, trained_at, notes).

### 7.7 `detect.py` — vision cascade (authed)
`POST /detect` — multipart image (PNG/JPEG/WebP, 10 MB max). Runs the cascade and returns `{items: [{menu_item_id, label, name, price, confidence, source, needs_confirm}], source_breakdown, perceptual_hash, errors}`.

### 7.8 `transaction.py` — cart, QR, void
`POST /transaction` (authed) — create pending transaction from cart; deduplicates items by `menu_item_id`; validates stock; computes total; returns `TransactionOut`.
`POST /transaction/{tx_id}/qr` (authed) — calls Billplz `create_bill` using the decrypted per-tenant credentials, persists `payments` row, returns the QR as PNG plus the `bill_url`.
`POST /transaction/{tx_id}/recheck-billplz` (owner) — fetch latest state from Billplz (escape hatch if the webhook is lost).
`POST /transaction/{tx_id}/void` (authed) — cashier self-void inside a short grace window; reverses stock movements.
`POST /transaction/{tx_id}/override-void` (owner) — force-void with a mandatory reason; audited as `"tx.override_void"`.
`GET /transactions` (authed) — paginated list with date-range and status filters.
`GET /transactions/{tx_id}` (authed) — detail with items, payment, and the raw webhook payload.

### 7.9 `payment.py` — Billplz webhook
`POST /payments/webhook` (public-ish) — state-change callback; verifies the HMAC-SHA256 signature with `hmac.compare_digest`; updates the `payments` row; on `state="paid"`, enqueues `process_receipt(tx_id, tenant_id)` on the `receipts` queue; returns `{"status":"ok"}` always to keep Billplz from retrying forever.

### 7.10 `receipt.py` — receipt PDFs + email
`GET /receipts/{tx_id}/pdf` (authed) — stream the PDF.
`GET /receipts/{tx_id}/qr` (authed) — render a PNG QR whose payload is a public-receipt URL embedding a 30-day `receipt_token`.
`GET /receipts/public?token=...` (public, token-gated) — customer-facing receipt view.
`POST /receipts/{tx_id}/email` (authed) — enqueue the receipt-email job, optionally overriding the recipient.

### 7.11 `inventory.py` — stock management (owner only)
`GET /inventory` — list of `{id, name, stock_qty, reorder_point, avg_cost, low_stock}`.
`GET /inventory/low-stock` — same, filtered to items at or below reorder point.
`POST /inventory/adjust` — `{menu_item_id, delta, reason, note}`; writes a `stock_movements` row and updates the running total; `reason` is pattern-validated.

### 7.12 `dashboard.py` — KPIs, forecasting, reports, Q&A
`GET /dashboard?range_key=today|7d|30d` (owner) — aggregate KPIs plus recent transactions, staff performance, and anomaly z-score.
`GET /dashboard/charts?range_key=...` (owner) — time-series data for the charts (revenue-by-day, tx-count-by-day, source breakdown).
`GET /dashboard/mobile` (owner) — compact version.
`GET /forecast` (owner) — per-item EWMA demand, safety stock, reorder point, EOQ.
`GET /reports?format=json|csv|xlsx|pdf` (owner) — exportable report.
`POST /ask` (owner) — `{question}`; serialises the dashboard window to a compact string and feeds it plus the question to Ollama `phi3:mini`.

### 7.13 `audit.py` — read-only audit log (owner)
`GET /audit?page&page_size&action_prefix` — paginated list of `{id, user_id, action, entity, entity_id, meta, created_at}`.

### 7.14 `ws.py` — authenticated WebSocket
`WS /ws?token=...` — registers the client under its tenant in the in-process hub; sends `{"type":"hello","tenant_id":...}` on connect; echoes `{"type":"ack","echo":...}` for any message; tenant-scoped broadcasts arrive via the Redis pub/sub → `run_subscriber` bridge.

### 7.15 `main.py` only
`GET /health` — `{"status":"ok","phase":"13","stage":2}`.

---

## 8. Backend Services (every module)

All services live under `backend/app/services/`. Services are pure-Python modules callable from both async routers and sync RQ jobs.

**`audit.py`** — one function `audit(session, *, action, tenant_id=None, user_id=None, entity=None, entity_id=None, meta=None)` that inserts an `AuditLog` row; tenant/user id may be NULL for cross-tenant events.

**`billplz.py`** — Billplz HTTP client. `create_bill(mode, api_key, collection_id, amount, reference)` POSTs to Billplz v3, returns `{bill_id, bill_url}`. `fetch_bill(mode, api_key, bill_id)` polls state. `verify_webhook_signature(xsign_key, form_fields, x_signature)` uses `hmac.compare_digest` on an HMAC-SHA256 of the sorted form fields. Mode (`sandbox`/`production`) selects the base URL.

**`crypto.py`** — thin Fernet wrapper. `encrypt_secret(plain)` / `decrypt_secret(token)` both accept `None` (returning `None`), so settings code can blanket-encrypt fields without special-casing missing values.

**`google_oauth.py`** — two verifiers: `verify_google_id_token(raw_token)` calls Google's tokeninfo endpoint, `verify_google_access_token(access_token)` calls `userinfo`. Both return `{email, sub, email_verified}` or raise `HTTPException(401)`.

**`tx_numbering.py`** — `next_tx_number(session, tenant_id)` locks today's last row (`SELECT ... FOR UPDATE`) and returns the next `"YYYYMMDD-NNN"` string.

**`forecast.py`** — pure maths. `ewma(series, alpha=0.3)` is the exponentially-weighted moving average; `safety_stock(series, service_z=1.65, lead_time_days=7)` is σ·z·√L; `reorder_point(ewma_daily, lead_time_days, ss)` is daily·L + ss; `eoq(annual_demand, order_cost=20.0, holding_cost_per_unit=0.50)` is the textbook Economic Order Quantity; `z_score_anomaly(today, window)` returns the z-score of today against the last window of days; `daily_series_from_rows(rows, window_days=30)` bucketises raw rows into a dense daily series with zero-fills.

**`receipt_pdf.py`** — ReportLab. `render_receipt(...)` emits an A5 PDF with header (logo + shop name), an itemised table, the total, payment method + ref, footer text, and a QR block on the bottom-right linking to the public receipt URL.

**`resend_mailer.py`** — one function `send_receipt_email(to, subject, html, attachments=None)` that POSTs to Resend and returns the Resend message id; failures raise so the RQ job can retry.

**`training.py`** — the RQ job `run_batch(tenant_id)`. Flow: acquire the per-tenant training lock; for every queued `training_jobs` row, extract frames at `fps=2`, write centred 0.8×0.8 bounding-box labels to YOLO `.txt` files, build a `data.yaml`, run `YOLO("yolov8n.pt").train(...)` with a modest epoch budget, capture `mAP50`, save weights to `ml_models/<tenant_id>/<version>/best.pt`, insert a new `model_versions` row, flip the old active inactive, release the lock in `finally`. Errors are caught per-job and stored on the `training_jobs.error` column.

**`yolo_service.py` + `yolo_cache.py`** — `get_or_load_model(tenant_id)` is the only entry point used by `detect.py`. It checks the process-wide LRU cache (last 3 tenants) and loads from `ml_models/<tenant_id>/best.pt` on miss. A file-mtime check invalidates the cache when training completes so the next detection picks up the new weights without a process restart.

**`detection/cascade.py`** — orchestrator. Input: image bytes, tenant id. It calls `preprocess.load_and_prep` to decode, resize, and compute the perceptual hash. Stage A (YOLO): runs the cached model; items with `confidence ≥ yolo_conf_threshold` are "green", between `yolo_conf_minimum` and the threshold are "yellow" and marked `needs_confirm=True`, below minimum are dropped. Stage B (MediaPipe): runs the EfficientDet-Lite0 head over the same image and uses category aliases to shortlist candidate menu items (currently a stub returning `[]`, with the wiring complete and ready for activation). Stage C (OpenAI): only fires if the prior stages produced nothing green; checks the 7-day pHash cache in Redis first, enforces the daily quota, calls `gpt-4o-mini` with the shortlisted menu items, caches the result, increments `openai_usage`. Finally, items are deduplicated by `menu_item_id` keeping the maximum-confidence hit, then returned with `source_breakdown` and any stage errors.

**`detection/{yolo_stage,mediapipe_stage,openai_stage,preprocess}.py`** — per-stage helpers called only by `cascade.py`.

**`video_frames.py`** — `extract_middle_frame(video_path, out_path)` uses ffmpeg to seek to the midpoint and write a JPEG preview; `probe_duration_seconds(video_path)` uses ffprobe to reject videos over 30 s.

**`receipt_jobs.py`** — the RQ job `process_receipt(tx_id, tenant_id)`. Loads the transaction + items, builds the PDF via `receipt_pdf.render_receipt`, writes it to `uploads/<tenant_id>/receipts/<tx_id>.pdf`, sends it via `resend_mailer.send_receipt_email` if `receipt_email` is set, persists the `receipts` row, and publishes a `{type: "tx_paid", tx_id, total}` event on the `geyam:ws` Redis channel.

**`daily_summary.py`** — `run_daily_summary(tenant_id, date)` computes the previous-day rollup (revenue, tx count, top items, anomaly flag) to accelerate dashboard queries. Called by the scheduler; also safe to run ad hoc.

**`autovoid_worker.py`** — `autovoid_pending(tenant_id)` voids unpaid transactions older than the configured TTL (default 24 h); publishes `{type:"tx_autovoid", tx_ids}` per tenant.

**`ws_broker.py`** — Redis pub/sub bridge. `publish_sync(tenant_id, message)` is a fire-and-forget publish callable from any worker or scheduler process. `run_subscriber(hub)` is the long-lived async task started in FastAPI's `lifespan`; it reads from the `geyam:ws` Redis channel and forwards each message to the in-process WebSocket `hub` so connected clients in the matching tenant receive it.

**`ollama_ask.py`** — `ask(question, context)` POSTs to the local Ollama HTTP endpoint (`http://host.docker.internal:11434`), returns the generated text.

---

## 9. ML / Computer-Vision Pipeline

### 9.1 Training

The training pipeline is designed for a shop owner with no ML knowledge. Flow:

1. Owner taps "Upload video" on the Training screen, picks a 15–30 s phone video of one product rotating in the hand.
2. Flutter multipart-uploads the video to `POST /train/video`, which validates size and duration, stores the file under `uploads/<tenant_id>/train/<job_id>.mp4`, extracts the middle frame as a preview, and creates a `training_jobs` row with `status="queued"`.
3. Owner taps "Train now", which enqueues `run_batch(tenant_id)` on the `training` RQ queue.
4. The worker grabs the job, acquires the per-tenant training lock (a `training_locked_at` timestamp on `tenant_settings`), and iterates the queued jobs. For each: `ffmpeg` extracts frames at `fps=2`, a centred 0.8×0.8 bounding box is auto-labelled (the product dominates a phone video, so tight cropping is unnecessary), and a YOLO-format dataset is built at `training_data/<tenant_id>/<job_id>/images|labels`.
5. The dataset is combined with the tenant's existing frames from prior jobs (curriculum training), a `data.yaml` is written listing every class label, and `YOLO("yolov8n.pt").train(data=..., epochs=..., imgsz=...)` runs for a modest budget.
6. The best weights (`runs/detect/trainN/weights/best.pt`) are copied to `ml_models/<tenant_id>/<version>/best.pt`, a `model_versions` row is inserted with `num_classes` and the `mAP50` score, the previous active model is flipped `is_active=False`, and the new one is flipped `is_active=True` — all inside one transaction.
7. The worker publishes `{type: "training_done", accuracy, num_classes}` on Redis; the WebSocket hub fans it out to the tenant's connected clients; the owner sees the dashboard chip flip green.

Approximately 39 tenant model directories currently exist on disk under `backend/ml_models/`, each with its own `data.yaml` and `best.pt`.

### 9.2 Inference — the cascade

```
POST /detect  ──▶  preprocess (decode, resize, pHash)
                        │
                        ▼
                  ┌──── YOLO (tenant weights, cached) ────┐
                  │                                        │
         conf ≥ 0.60  ──▶ green hit, emit as-is            │
         0.40 ≤ conf < 0.60 ──▶ yellow, needs_confirm=True │
         conf < 0.40 ──▶ drop                              │
                  │                                        │
                  ▼                                        │
               any green?  ── YES ─▶ return                │
                  │ NO                                     │
                  ▼                                        │
                MediaPipe EfficientDet-Lite0               │
                (category shortlist via aliases)           │
                  │                                        │
                  ▼                                        │
                any usable?  ── YES ─▶ return              │
                  │ NO                                     │
                  ▼                                        │
                OpenAI gpt-4o-mini vision                  │
                (pHash-cached 7d, quota-gated)             │
                  │                                        │
                  ▼                                        │
              dedupe by menu_item_id (max conf)            │
                  │                                        │
                  ▼                                        │
           {items, source_breakdown, phash, errors}
```

The thresholds, minimum, and daily quota are per-tenant settings so an owner can tune their shop's trade-off between false positives and cost. The perceptual-hash cache is stored in Redis with a 7-day TTL under key `openai:phash:<tenant_id>:<hash>`.

---

## 10. Payments, Receipts, and Email

### 10.1 Billplz DuitNow QR flow

1. Cart is committed via `POST /transaction`, creating a `transactions` row (`status="pending"`) with its line items and stock checks.
2. Flutter calls `POST /transaction/{tx_id}/qr`. The backend decrypts this tenant's Billplz API key and X-Signature key, calls Billplz v3 `create_bill` with the amount, reference, and a callback URL pointing at `api.geyam.com/payments/webhook`, and persists a `payments` row with `bill_id`, `bill_url`, and `state="pending"`.
3. The backend renders the returned `bill_url` as a QR PNG and streams it to Flutter, which displays it in the payment dialog.
4. The POS screen polls `GET /transactions/{tx_id}` every 3 s.
5. When the customer scans-and-pays, Billplz fires `POST /payments/webhook` with the form-encoded bill fields and an `x_signature`. The handler recomputes the HMAC-SHA256 over the sorted form fields with `hmac.compare_digest` (timing-safe), and on a valid match updates `payments.state`, `paid_at`, `transactions.status="paid"`, and `paid_at`. It enqueues `process_receipt(tx_id, tenant_id)`.
6. The POS polling loop sees `status="paid"`, closes the QR dialog, and calls `GET /receipts/{tx_id}/qr` to swap in the receipt QR; the customer can scan it to download the PDF.

### 10.2 Receipts

PDFs are rendered by ReportLab (`services/receipt_pdf.py`) and saved under `uploads/<tenant_id>/receipts/<tx_id>.pdf`. The QR embedded on the PDF encodes `https://geyam.com/r?token=<receipt_token>`; the token is a 30-day read-only JWT scoped to that one transaction. The public receipt route decodes it and returns the metadata; no login required, so the customer can get a copy even months later, but they cannot see any other shop data.

### 10.3 Email

Resend sends emails from `noreply@geyam.com`. SPF and DKIM records live on Cloudflare DNS (grey-cloud, not proxy-orange, because Resend reads the raw records). The `process_receipt` RQ job attaches the PDF as bytes, not a URL, so the customer does not need to click through.

---

## 11. Background Jobs, Scheduler, and WebSockets

### 11.1 Alembic migrations (nine applied)

`0001_initial_schema.py` — tenants, users.
`0002_audit_logs.py` — audit log table, BIGINT PK.
`0003_tenant_settings.py` — per-tenant config and encrypted credentials.
`0004_menu_items.py` — catalogue with composite uniques.
`0005_training_and_models.py` — training_jobs + model_versions.
`0006_openai_usage.py` — daily quota counter.
`0007_transactions_and_customers.py` — transactions, transaction_items, payments, receipts, and (at the time) customers.
`0008_suppliers_and_pos.py` — supplier + purchase-order tables (later deprecated).
`0009_drop_legacy_tables.py` — drops PO/supplier/customer; consolidates email on `transactions.receipt_email`; adds `stock_movements`.

### 11.2 RQ jobs

Three job types, each an ordinary function in `services/`:
- `training.run_batch(tenant_id)` on queue `training`
- `receipt_jobs.process_receipt(tx_id, tenant_id)` on queue `receipts`
- `autovoid_worker.autovoid_pending(tenant_id)` (currently invoked by the scheduler loop; may migrate to RQ)

The worker container runs `rq worker training receipts` and has `redis` as a `depends_on`.

### 11.3 Scheduler

A lightweight loop every 60 s iterates every active tenant and runs `autovoid_pending(tenant_id)`; separately, a nightly cron-style loop runs `daily_summary.run_daily_summary`. Both use `bypass_tenant_scope()` inside with explicit tenant filters so they can cross tenants.

### 11.4 WebSockets

`/ws?token=...` accepts an access-token JWT in the query string because browsers cannot set custom headers on WS handshakes. The handler decodes the token, registers the socket with the in-process `hub` keyed by tenant, sends `{type:"hello"}`, and then reads-acks in a loop until disconnect. Downstream events come from Redis pub/sub (`geyam:ws` channel) — any worker or scheduler calls `ws_broker.publish_sync(tenant_id, message)` and the `run_subscriber` task in the backend process forwards it to every client registered under that tenant.

Message types currently emitted: `training_done`, `tx_paid`, `tx_autovoid`, `low_conf`.

---

## 12. Flutter App — Screens, Widgets, State

The Flutter project is under `frontend/geyam_pos/`. It compiles to both web (for the landing page + owner workflow) and Android (for cashier phones). `main.dart` wires three providers (theme, connectivity, notifications), switches between `LandingScreen` (web) and `LoginScreen` (mobile) with `kIsWeb`, and wraps the whole `MaterialApp` in a 1200-px-max-width `ConstrainedBox` on web.

### 12.1 Screens

`landing_screen.dart` — web-only public hero: dark scaffold, muted video background, feature grid (Camera, Inventory, Dashboards, AI Q&A), sakura-petal overlay for aesthetic, buttons to Login and Info.

`login_screen.dart` — two tabs: Owner (Google Sign-In button using `google_sign_in`) and Cashier (shop handle + username + 6-digit PIN). Handles the OAuth callback guard `_handled` to avoid double-calls, routes to `SignupScreen` if the backend returns a `signup_token`, to `TenantPickerScreen` for admin tokens, or to `DashboardScreen` for regular owners/cashiers.

`signup_screen.dart` — new owner onboarding: shop name and handle inputs with client-side validation, posts to `/auth/google/signup`, routes to `DashboardScreen` on success.

`tenant_picker_screen.dart` — admin-only: lists every tenant from `/admin/tenants`, search bar, "Open" per row which calls `/admin/tenants/{id}/impersonate` and then pushes `DashboardScreen`.

`pos_screen.dart` — cashier's main screen, responsive. Wide (≥700 px): scan/menu toggle on the left, cart on the right. Narrow: TabBar for Scan / Menu / Cart plus a sticky bottom checkout bar. Scan panel shows the last snapshot with `ConfidenceBadge` chips per detected item. Menu panel is a searchable grid. Cart panel lists line items with `qty ±`, remove, and a running total. Checkout opens a payment dialog that fetches a Billplz QR PNG and polls `/transactions/{id}` every 3 s. On paid, it swaps to the receipt QR and offers an "Email receipt" action.

`dashboard_screen.dart` — owner only. Range picker (Today / 7d / 30d) across a row of `GradientKpiCard`s (revenue, transaction count, avg basket, top item, low-stock count, anomaly z). Sales pie chart (top 6 items + Other), revenue line chart over the range, staff performance table, recent transactions list, detection source bar chart. A floating `AskChatBubble` posts to `/ask` against Ollama `phi3:mini`.

`menu_manager_screen.dart` — owner only: a `DataTableSoft` of menu items with name/category/price/stock/active and actions (upload image, edit, delete/restore). Toolbar has an archived toggle, a CSV import, and a "New item" button.

`csv_preview_screen.dart` — CSV import flow: parses the first 50 rows, shows a preview, confirms to `/menu/bulk`, reports `inserted`, `updated`, and per-row errors.

`training_screen.dart` — owner only: current active model card (version, classes count, `mAP50`, trained-at), jobs table (status / frames / queued-at / error), toolbar buttons to upload a video (with a menu-item picker) and to kick off `/train/run`.

`transactions_list_screen.dart` — owner + cashier: status-tab filter (All / Pending / Paid / Voided), paginated table (25 per page), row tap opens `TransactionDetailScreen`.

`transaction_detail_screen.dart` — summary header, line-items table, paid-only receipt QR + PDF link, and context-aware actions (void if pending, email + override-void if paid and owner).

`inventory_screen.dart` — owner only: All / Low-stock tabs, table with adjust button; the adjust dialog requires a reason picker and a non-zero delta.

`staff_manager_screen.dart` — owner only: cashier table, "New cashier" and "Reset PIN" dialogs, an active/inactive switch.

`settings_screen.dart` — owner only: Billplz block (mode, collection id, api key, x-sign key, "configured" chip), Shop & Receipt block (emails, phone, footer, logo upload), Detection thresholds block (YOLO confidence, minimum, OpenAI daily limit). API keys are only included in the PATCH if non-empty.

`audit_log_screen.dart` — owner only: action-prefix filter plus 50-per-page pagination, meta-JSON inline.

`reports_screen.dart` — owner only: format picker (JSON / CSV / XLSX / PDF), preview for JSON, `url_launcher` for binaries.

`menu_picker_screen.dart` and `cart_detail_screen.dart` — modal fallback screens for the POS flow (pick items when detection fails; review cart in a bigger layout).

`info_screen.dart` — web-only About page explaining the project.

### 12.2 Widgets

`gradient_kpi_card` wraps a label + value in a rotating gradient (six pairs: pink, violet, indigo, teal, rose, amber). `confidence_badge` pills the detection confidence and source with colour by `needs_confirm`. `notification_bell` is the app-bar action that shows unread WS events and an offline indicator. `glow_icon_tile` is the landing-page feature tile. `tabbed_nav` is the pill-style tab with animated underline. `geyam_leading` is the shared app-bar leading (menu + theme-toggle). `sakura_overlay` is the custom-painter petal animation. `section_card` is the shared bordered container. `app_drawer` is the role-aware navigation drawer. `data_table_soft` is the soft-styled table with optional column highlight. `ask_chat_bubble` is the floating Q&A popup.

### 12.3 State

`theme_provider` toggles dark/light. `connectivity_provider` listens to `connectivity_plus` and exposes `isOnline` plus a `guardMutation()` helper. `notification_provider` owns the WebSocket channel (connects on login with the JWT in the query string), parses incoming JSON, and keeps the last 50 events.

`ApiService` is a thin singleton: `get`, `post`, `patch`, `delete`, `uploadBytes`; injects `Authorization: Bearer` and `Content-Type`; blocks mutations when offline; throws `ApiException(statusCode, body)` on ≥ 400. No JSON-serializable models — the client deliberately treats responses as `Map<String, dynamic>` to stay loose against schema tweaks during Phase 13.

### 12.4 Config

`theme.dart` owns dark (`bgDark #0A1428`, `cardDark #121E3A`) and light palettes, the six KPI gradient pairs, and semantic colours (success / warning / error / info). `api_config.dart` reads `API_BASE_URL` from env (default `http://localhost:9000`). `main.dart` is the one place where web-vs-mobile routing happens.

### 12.5 Dependencies (`pubspec.yaml`)

`http`, `http_parser`, `mime`, `provider`, `image_picker`, `camera`, `fl_chart`, `web_socket_channel`, `connectivity_plus`, `file_picker`, `url_launcher`, `google_sign_in`, `video_player`. Assets: landing-page demo video and the Google logo.

---

## 13. Infrastructure, Deployment, and DNS

Docker Compose defines seven services. `db` is Postgres 16 on host port 5433 (non-standard to avoid colliding with local installs), with a healthcheck on `pg_isready`. `redis` is on host port 6380. `backend` (FastAPI + Uvicorn + WebSocket) binds `9000:8000`, depends on `db` and `redis`, mounts `./uploads`, `./ml_models`, and `./training_data`, and reads `./backend/.env`. `worker` runs `rq worker training receipts`. `scheduler` runs the auto-void loop. `backup` runs nightly `pg_dump` into `./backups/` with 7-day retention. `pgadmin` is optional.

`extra_hosts: host.docker.internal:host-gateway` on the backend container so `ollama_ask.py` can reach the host's Ollama on `:11434`.

DNS: `geyam.com` nameservers on Cloudflare. `api.geyam.com` is a CNAME to a Cloudflare Tunnel pointing at `localhost:9000`; the tunnel binary (`cloudflared`) runs in WSL alongside Docker. The static site at `geyam.com` is served by Hostinger and is updated by uploading the output of `flutter build web --release`. SPF and DKIM records for `noreply@geyam.com` sit on Cloudflare DNS (grey-cloud) so Resend can verify the sender.

Ports in summary: `9000` FastAPI, `5433` Postgres, `6380` Redis, `5050` pgadmin (if enabled), `11434` Ollama (on the host, not a container).

---

## 14. Testing Strategy

`backend/tests/` contains nine files. `conftest.py` configures `anyio` and the per-test DB lifecycle.

`test_phase3_phase4.py` covers Google OAuth login and signup, Billplz credential round-tripping, logo upload, and cashier creation with PIN validation. `test_phase5_phase6.py` covers menu CRUD, CSV bulk import, product-image upload, video upload with ffprobe duration validation, training-job queueing, and model activation. `test_phase7_detection.py` unit-tests the cascade stages with stubbed models so the CI does not need GPU, OpenAI keys, or Redis. `test_phase9_phase10.py` covers the transaction happy path, Billplz QR, receipt PDF, Resend email, webhook signature verification, and both void flows. `test_phase11_forecast.py` unit-tests EWMA, safety stock, reorder point, EOQ, and the z-score anomaly. `test_phase12_ws_broker.py` and `test_phase12_ws_hub.py` cover the Redis→hub bridge and the hub's register/unregister/broadcast. `test_tenant_isolation.py` is the big one: it seeds two tenants, runs the owner-visible SELECTs under tenant A's ContextVar, and asserts none of tenant B's rows appear — then flips `bypass_tenant_scope()` on and asserts both appear. This is the Rule-2 gate.

Tests run via `docker compose run --rm backend pytest -xvs`.

---

## 15. Risks, Failure Modes, and Mitigations

**Tenant leak via a missing filter.** Mitigated by the `do_orm_execute` hook (you cannot forget it) and the `test_tenant_isolation` integration test that must stay green for every PR.

**Lost Billplz webhook.** Network hiccups can drop a webhook. Mitigation: `POST /transaction/{tx_id}/recheck-billplz` is an owner-triggered escape hatch that polls Billplz and reconciles the `payments` row. The POS-poll loop also catches transitions even if the webhook is slow.

**Training lock stuck.** If the worker dies mid-training, `training_locked_at` stays set. Mitigation: the lock has a TTL; an operator can clear it via `docker compose exec db psql ... 'UPDATE tenant_settings SET training_locked_at=NULL WHERE tenant_id=...'`.

**OpenAI cost runaway.** Mitigated by the 7-day pHash cache and the per-tenant daily quota on `tenant_settings.openai_daily_limit`; once the quota is hit the cascade returns the yellow/unknown hits for manual confirm instead of calling the API.

**PIN brute-force.** Six-digit PINs have only 10⁶ space. Mitigated by: bcrypt with a modest cost factor, tenant-scoped username uniqueness, failed-login audit events, and short cashier token lifetime (12 h).

**Credential leakage in backups.** `tenant_settings` stores Billplz keys Fernet-encrypted; even the nightly `pg_dump` file is only as sensitive as the Fernet key, which lives in `.env` and never in git.

**Cloudflare Tunnel down.** If the laptop is off or the tunnel crashes, `api.geyam.com` returns 502 from Cloudflare's edge. The Flutter client shows an offline banner (via `ConnectivityProvider`) and blocks mutations with `guardMutation()`.

**Model-file regression.** If training produces a worse model than the previous active, the dashboard's "Active model" card still shows the new one. Mitigation: `num_classes` and `mAP50` are stored on `model_versions`, so an operator can roll back by flipping `is_active` in SQL. (An in-app rollback UI is in scope for a later phase.)

**Redis down.** Kills both the RQ queue and the pub/sub bridge. Mitigation: Compose healthchecks auto-restart Redis; the WebSocket hub degrades to "no live events" but the POS polling loop keeps working because it does not depend on WS.

---

## Appendix A — Repository Layout

```
geyam/
  CLAUDE.md
  docker-compose.yml
  docs/
    PLANstage1.md           # original single-shop plan (kept for reference)
    PLANstage2.md           # current multi-tenant plan — source of truth
    PROJECT_OVERVIEW.md     # this document
    SETUP.md
  designreference/          # PNG/WEBP visual references for Phase 13
  backend/
    main.py
    alembic.ini
    alembic/
      env.py
      versions/             # 0001 … 0009
    app/
      config.py
      database.py
      deps.py
      security.py
      tenant_context.py
      websocket.py
      models/               # tenant, user, menu_item, transaction, audit_log, …
      routers/              # admin, auth, users, settings, menu, train, detect,
                            # transaction, payment, receipt, inventory,
                            # dashboard, audit, ws
      services/             # billplz, crypto, google_oauth, forecast, receipt_pdf,
                            # resend_mailer, training, yolo_service, yolo_cache,
                            # detection/*, video_frames, receipt_jobs, daily_summary,
                            # autovoid_worker, ws_broker, tx_numbering, ollama_ask
      schemas/              # Pydantic request/response models (paired with routers)
    tests/                  # nine test files (see §14)
    scripts/                # create_tenant.py, seed_demo_tenant.py,
                            # append_seed_tenant.py, clone_tenant.py
    ml_models/              # ml_models/<tenant_id>/<version>/best.pt (≈39 tenants)
    training_data/          # training_data/<tenant_id>/job_<id>/{images,labels}/…
    uploads/                # uploads/<tenant_id>/{products,logos,receipts,train}/…
  frontend/geyam_pos/
    pubspec.yaml
    lib/
      main.dart
      config/               # theme.dart, api_config.dart, routes.dart
      providers/            # theme, connectivity, notification
      services/             # api_service.dart
      screens/              # landing, login, signup, tenant_picker, pos,
                            # dashboard, menu_manager, csv_preview, training,
                            # transactions_list, transaction_detail, inventory,
                            # staff_manager, settings, audit_log, reports,
                            # menu_picker, cart_detail, info
      widgets/              # gradient_kpi_card, confidence_badge,
                            # notification_bell, glow_icon_tile, tabbed_nav,
                            # geyam_leading, sakura_overlay, section_card,
                            # app_drawer, data_table_soft, ask_chat_bubble
      assets/               # videos/demo.mp4, images/google_logo.png
  hostinger/                # static landing page + deployment helpers
  scripts/                  # top-level helper scripts
```

---

## Appendix B — Key Design Decisions Glossary

**Tenant root.** The `Tenant` model is marked `__tenant_root__ = True`; the scope hook skips it so owner-login can resolve the tenant without yet being inside the scope.

**Access vs refresh vs signup vs receipt vs admin token.** Five JWT types, all signed with the same `JWT_SECRET`. Access tokens carry `tenant_id + user_id + role` and expire in 24 h (owner) or 12 h (cashier). Refresh tokens last 30 days. Signup tokens carry only `email + sub` and last 10 min — they exist so a Google-verified user with no tenant yet can finalise shop name + handle. Receipt tokens carry `tenant_id + tx_id` and last 30 days — they grant read-only access to one PDF without login. Admin tokens carry `email + role="admin"` and no `tenant_id` — they cannot hit non-admin endpoints.

**`tx_number` format.** `"YYYYMMDD-NNN"`, per-day per-tenant. Generated via `SELECT ... FOR UPDATE` on the last row for the day to handle races without a dedicated sequence.

**Soft delete.** Menu items and staff are soft-deleted via `is_active=False` so historical transactions and audit logs still resolve the reference.

**Stock-movement ledger.** `stock_movements` is append-only; `menu_items.stock_qty` is the running total but the ledger is authoritative. A void restores the sold quantities by writing a matching `void_restore` row.

**Per-tenant lock.** Training is serialised per tenant via a `training_locked_at` timestamp on `tenant_settings`. The worker clears it in a `finally` block.

**pHash cache key.** `openai:phash:<tenant_id>:<hash>` with 7-day TTL; the hash is computed on the preprocessed image so the same photo from different angles can still miss the cache.

**Owner-override void.** Any paid transaction can be voided by an owner with a mandatory reason string; the audit row records both the reason and the `voided_by` user id.

**Grey-cloud DNS for Resend.** Cloudflare proxy mode strips SPF/DKIM metadata; only grey-cloud (DNS-only) records propagate the email-auth metadata Resend needs.

**Why a ContextVar, not a thread-local.** FastAPI runs on asyncio; thread-locals cannot distinguish concurrent coroutines. `ContextVar` is the official async-safe equivalent.

**Why RQ and not Celery.** The project has three job types with straight-line logic. Celery's broker abstraction, beat, chords, and canvas primitives would be overhead. RQ is a Python function with a Redis queue and that is the whole mental model.

**Why `phi3:mini` locally and `gpt-4o-mini` in the cloud.** The LLM Q&A over sales data must not leave the shop, so it runs on Ollama on the laptop. The vision fallback must be accurate on rare items, so when it runs it runs against the best small vision model with strict quotas and a pHash cache.

---

*End of document. For the locked plan, see `docs/PLANstage2.md`; for operator commands, see `CLAUDE.md` and `docs/SETUP.md`.*
