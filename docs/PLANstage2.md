# GEYAM — Stage 2: Multi-Tenant SaaS + Retail Expansion

A multi-tenant Smart POS SaaS for packaged food. Each shop's owner signs in with their real Gmail (2FA enforced by Google), creates cashier accounts under them (PIN-only login), trains a YOLO model on their own products, and runs a full retail flow — inventory, purchase orders, DuitNow QR payments via Billplz, email receipts, and a rich dashboard — all isolated per tenant.

---

## What This System Does

Stage 1 was a single-shop demo. Stage 2 turns GEYAM into a real multi-tenant platform. You (the admin) create a tenant tied to an owner's Gmail. The owner logs in via Google (Google enforces 2FA), creates cashier accounts (PIN-only), and manages their catalog, inventory, POs, and Billplz credentials. Cashiers use a Flutter mobile POS: camera → detection cascade (tenant YOLO → MediaPipe fallback with cashier shortlist → OpenAI Vision last resort) → cart → DuitNow QR via Billplz → webhook-confirmed transaction → auto-emailed receipt if the customer is attached. A public landing page on geyam.com (web only) sits in front of the login. Mobile and Windows builds skip the landing.

---

## Locked Scope Summary (no ambiguity)

```
Roles              : owner, cashier (two only)
Owner count        : exactly one owner per tenant (owner_email UNIQUE)
Owner login        : Google OAuth; 2FA enforced by Google
Cashier login      : username + 6-digit PIN only (no password)
PIN policy         : 6 digits required; blocklist trivial PINs (000000, 111111, 222222,
                     333333, 444444, 555555, 666666, 777777, 888888, 999999,
                     123456, 654321, 012345)
Sessions (JWT)     : owner access 24h, cashier access 12h, refresh token 30 days
No-tenant Google   : 403 "contact admin"
Auth hardening     : every auth attempt logged to audit_logs (no rate limit, no lockout)
Admin access       : ADMIN_EMAILS env var (comma-separated). Whitelisted emails can hit
                     /admin/tenants AND impersonate the demo-tenant owner for screencasts.
                     brianchen.crisp@gmail.com is in this list by default.
Tenants            : admin-created via CLI + hidden admin page
Google OAuth       : reuse existing Google Cloud project; update authorized redirect URIs to
                     include https://geyam.com/auth/callback and http://localhost:PORT/auth/callback
Billplz            : per-tenant credentials (api_key, collection_id, xsign) in Settings
Billplz mode       : per-tenant 'sandbox' or 'production' toggle in Settings
Billplz missing    : sale blocked with "Configure Billplz in Settings" error (no cash fallback)
Payment timeout    : auto-void after 10 min + WebSocket notification to staff
TX numbering       : GY{YYYYMMDD}-{N} per-tenant sequence (e.g. GY20260420-0042)
Paid TX recovery   : owner-only "manager override void" with reason (restores stock, audits)
Receipt            : digital always; email auto on paid if customer attached; manual email always
Receipt branding   : shop name + owner contact + logo + itemized + total + payment + footer
Email sender       : noreply@geyam.com (SPF + DKIM set up in Cloudflare DNS, verified in Resend)
Detection cascade  : YOLO (≥0.60) → MediaPipe+category-shortlist → OpenAI gpt-4o-mini
OpenAI quota       : 50 calls/tenant/day, configurable per tenant
Low-confidence UX  : yellow badge, tap to confirm/replace
Zero-detection UX  : manual menu grid on POS
Shortlist picker   : blocking modal; cashier picks one or taps 'Skip'
Post-sale POS      : 3-sec success screen → auto-return to camera
Menu CRUD          : single-form + CSV bulk (upsert by name)
CSV columns        : name, price, category, barcode, stock_qty, reorder_point, image_url
Product images     : auto-extracted middle frame from video, manual override in form
Soft delete        : menu_items.is_active=false; YOLO class retained (unused)
Reactivation       : 'Show archived' toggle + Restore button (works for menu items AND suppliers)
Customer           : optional dialog at checkout (email / phone); no loyalty
Customer dedup     : lookup by (tenant_id, email); reuse existing row if match, else create
Inventory          : stock + POs + suppliers + movements + weighted avg cost
Negative stock     : blocked; sale rejected if insufficient
Partial PO receive : allowed; status=partial until full
Stock adjust       : dropdown reasons (damage / loss / theft / miscount / expired / other)
Training           : batched; owner hits "Train Now" after queuing videos
Training concurrency: per-tenant lock; second Train Now returns 409 'training in progress'
Training failure   : job status='failed'; active model unchanged; banner notifies owner
Video limits       : 30 sec, 100 MB max per upload
Image limits       : logo ≤ 2MB, product image ≤ 5MB, auto-resize longest edge → 1024px (Pillow)
Dashboard          : Today default; 7d / 30d / custom chips
Charts             : fl_chart
Theme              : Stage 1 palette (navy #000080, accent #1E90FF); dark mode default
Language           : English only (UI, receipts, reports)
Locale             : Asia/Kuala_Lumpur, MYR fixed
LLM for /ask       : local Ollama phi3:mini (under 4B params)
Reports            : sales by day + item perf + staff perf + inventory valuation (CSV/XLSX/PDF)
Audit events       : auth + menu/inventory + transactions + settings
Audit retention    : indefinite
Notifications      : in-app banner + WebSocket push
Offline handling   : graceful degraded mode (banner, block mutations)
File storage       : local disk ./uploads/<tenant>/ served by FastAPI StaticFiles
Backups            : nightly pg_dump container, 7-day retention
Deployment         : laptop (sleep prevented + auto-restart service) + Cloudflare Tunnel
Mobile distro      : Android only, sideload APK via USB / direct link (no iOS, no Play Store)
Landing page       : web only (kIsWeb). Hero + features + demo MP4 + Login top-right
Demo tenant        : static seed, never resets; admin impersonates owner via ADMIN_EMAILS whitelist
Deferred           : full refunds/returns with money movement, card gateway, promotions,
                     hardware, loyalty points, iOS build, bilingual UI
```

---

## Architecture

```
┌──────────────────────────────────────────────────────────────┐
│  geyam.com (Hostinger static)                                │
│  - Landing page (web only)  → Login (top-right)              │
│  - Flutter Web (owner dashboard)                             │
│  - demo.mp4 served inline                                    │
│  HTTPS via Cloudflare                                        │
└───────────────────────────────┬──────────────────────────────┘
                                │
                     api.geyam.com (Cloudflare Tunnel)
                                │
┌───────────────────────────────▼──────────────────────────────┐
│  YOUR LAPTOP                                                 │
│                                                              │
│  ┌───────────────┐   ┌──────────────────────────────────┐    │
│  │  FastAPI       │   │  Detection Cascade               │    │
│  │  + Auth        │◄──│   1. Tenant YOLO (conf ≥ 0.60)    │    │
│  │  + Billplz     │   │   2. MediaPipe + shortlist        │    │
│  │  + Resend      │   │   3. OpenAI gpt-4o-mini (last)    │    │
│  │  + Audit       │   └──────────────────────────────────┘    │
│  │  + WebSocket   │                                          │
│  └───────┬───────┘                                           │
│          │                                                   │
│  ┌───────▼────────┐   ┌──────────────┐   ┌───────────────┐   │
│  │  PostgreSQL     │   │  RQ (Redis)  │   │  Local disk   │   │
│  │  row-level      │   │  jobs:       │   │  uploads/     │   │
│  │  tenant_id on   │   │  - train     │   │    <tenant>/  │   │
│  │  every table    │   │  - export    │   │    logo.png   │   │
│  │                 │   │  - auto-void │   │    products/  │   │
│  │                 │   │  - receipt   │   │    videos/    │   │
│  └────────────────┘   └──────────────┘   └───────────────┘   │
│                                                              │
│  Backup container: pg_dump → ./backups (7-day retention)     │
│  Uptime: sleep prevented + backend as launchd/systemd svc    │
└──────────────────────────────────────────────────────────────┘

┌───────────────────┐
│  Flutter Mobile   │
│  Cashier POS +    │
│  Owner light-dash │──► REST + WebSocket → api.geyam.com
└───────────────────┘

External:
  Google OAuth    → verifies owner identity (2FA enforced by Google)
  Billplz (per-tenant) → DuitNow QR + webhook → /payments/webhook
  Resend          → email receipts + reports
  OpenAI API      → gpt-4o-mini vision fallback, cached, quota-capped
  Ollama (local)  → phi3:mini for /ask
```

---

## User Roles (final)

**Owner** — Signs up via Google OAuth (must match a tenant record created by admin). Full permissions: staff, menu, inventory, POs, customers, Billplz credentials, receipt branding, dashboards, reports, LLM Q&A.

**Cashier** — Username + PIN only (6-digit). Created by owner. Can run POS, attach customers, void pending transactions, see low-stock badges in-cart. Cannot see costs, dashboards, settings, or audit log.

**Admin (you)** — Out-of-band. CLI script + hidden `/admin/tenants` page (gated by your own Google email whitelisted in `.env` as `ADMIN_EMAILS`). Creates tenants, resets owner links, triggers backups.

---

## Core Flows

### Flow 1 — Admin onboards a new shop

```
You run: python scripts/create_tenant.py --email brianchenjunhao@gmail.com \
           --handle brianchenjunhao --name "Brian's Shop"
    │
    ▼
tenants row created; owner user row pre-created (role=owner, google_sub=null)
    │
    ▼
Owner visits geyam.com → clicks Login → Google OAuth
    │
    ▼
Backend matches google email to tenants.owner_email → links google_sub → issues JWT
    │
    ▼
Owner lands on Dashboard (empty state with "Add your first product" CTA)
```

### Flow 2 — Owner builds catalog

```
Owner opens Settings → enters Billplz API key, collection_id, x-sign key
    │
    ▼
Owner opens Menu Manager:
  Option A: single-add form (name, price, category, barcode, stock, reorder_point, image)
  Option B: CSV bulk upload → preview → confirm → upsert by name
    │
    ▼
Owner opens Training → "Upload video" per product (≤30 sec, ≤100 MB)
Videos queued as jobs (status=pending)
    │
    ▼
Owner clicks "Train Now" → RQ worker processes all queued videos in one batch
    │
    ▼
Model saved to ml_models/<tenant_id>/best.pt; hot-reloaded into memory
```

### Flow 3 — Cashier makes a sale with DuitNow QR

```
Cashier opens mobile app → enters username + 6-digit PIN → JWT
    │
    ▼
POS screen → snap tray photo → POST /detect
    │
    ▼
Cascade:
  1. Tenant YOLO                                         
     - ≥ 0.60 → add to cart (green badge)               
     - < 0.60 but > 0.40 → add to cart with YELLOW badge 
       (tap badge → confirm or replace via menu picker)
     - none > 0.40 → fall through
  2. MediaPipe EfficientDet-Lite0 detects generic objects
     - Map to menu via category alias (e.g. "bottle" → "drink")
     - If 1 candidate → suggest with yellow badge
     - If >1 candidate → show cashier a shortlist picker
     - If 0 candidates → fall through
  3. OpenAI gpt-4o-mini vision (quota-gated, pHash cached)
     - Returns names → fuzzy-matched to menu
     - Yellow badge always (requires confirm)
     - If quota exceeded → skip, notify cashier
    │
    ▼
If total detections = 0 → cashier opens menu grid → taps items manually (source='manual')
    │
    ▼
Optional: cashier taps "Attach customer" → dialog (skip / email / phone)
    │
    ▼
Cashier hits Confirm → POST /transaction (status=pending, number=GY20260420-0042)
    │
    ▼
Block if any line item's quantity > stock_qty (negative-stock protection)
    │
    ▼
POST /transaction/{id}/qr → Billplz bill via tenant credentials → return bill_url
    │
    ▼
Cashier shows QR. Customer scans + pays in bank app.
Billplz → POST /payments/webhook → x-signature verified → status=paid
    │
    ▼
Server: stock decremented (stock_movements rows), audit entries, WebSocket push to cashier
If customer attached → receipt PDF generated → Resend email sent
    │
    ▼
Cashier sees green checkmark + "Email receipt" button (works even if auto-sent, resends manually)
```

### Flow 4 — Payment timeout (auto-void)

```
RQ scheduled job runs every 60 sec:
    SELECT id FROM transactions
     WHERE status='pending'
       AND created_at < NOW() - INTERVAL '10 minutes'
    │
    ▼
For each: transaction.status='voided', voided_at=NOW(), voided_by=NULL (system)
    │
    ▼
Audit entry 'tx.auto_void'
    │
    ▼
WebSocket message to that cashier's socket → banner "TX GY20260420-0042 auto-voided"
```

### Flow 5 — Owner runs inventory cycle

```
Dashboard → "Low Stock" card (items where stock_qty ≤ reorder_point)
    │
    ▼
Click item → Item detail → "Create PO" button
    │
    ▼
PO form: supplier (dropdown or +New), line items, unit costs, expected date
Suggested quantity = EOQ calculation pre-filled
    │
    ▼
Save PO (status=draft) → "Send" (status=sent) → audit entry
    │
    ▼
Goods arrive; PO → "Receive" screen:
  - Partial receive allowed (enter received_qty per line)
  - status transitions: sent → partial → received
  - Each receive creates stock_movements rows, updates menu_items.stock_qty
  - avg_cost recomputed: (old_stock*old_avg + received_qty*unit_cost)/new_stock
```

### Flow 6 — Owner drills into a transaction

```
Dashboard → "Transactions" link → paginated table with filters (date, staff, status)
    │
    ▼
Click row → Transaction Detail screen shows:
  - Header: TX number (GY20260420-0042), date, staff, customer (if any), status badge
  - Line items: name | qty | unit_price | confidence | source (yolo/mediapipe/openai/manual)
  - Totals, payment block: method, Billplz bill_id, paid_at, raw webhook JSON collapsible
  - Actions: Email receipt, Download PDF, Void (only if still pending)
  - Audit trail filtered by entity='transaction', entity_id=this
```

---

## Landing Page Rule (Web-Only)

```
Flutter main.dart:
  if (kIsWeb)  → MaterialApp home: LandingScreen
  else         → MaterialApp home: LoginScreen

LandingScreen layout:
  ┌────────────────────────────────────────────────────────────────┐
  │  GEYAM logo (top-left)                    [Login] (top-right)  │
  ├────────────────────────────────────────────────────────────────┤
  │  HERO                                                          │
  │    "Smart POS for Packaged Food"                               │
  │    "Train it by filming. Sell by snapping."                    │
  │    [Request a demo] (mailto:brianchen.crisp@gmail.com)         │
  ├────────────────────────────────────────────────────────────────┤
  │  demo.mp4 (served from Hostinger, autoplay muted loop)         │
  ├────────────────────────────────────────────────────────────────┤
  │  FEATURES (grid of 4)                                          │
  │    📷 Camera scan   📦 Inventory   📊 Dashboards   🤖 AI Q&A    │
  ├────────────────────────────────────────────────────────────────┤
  │  Footer: © GEYAM 2026 · v2.0 · brianchen.crisp@gmail.com       │
  └────────────────────────────────────────────────────────────────┘
```

Mobile/Windows builds compile LandingScreen out; LoginScreen is the first screen.

---

## Folder Structure

```
geyam/
├── docker-compose.yml
├── .env                                   # GOOGLE_CLIENT_ID, OPENAI_API_KEY, RESEND_API_KEY,
│                                          # JWT_SECRET, ADMIN_EMAILS (comma-separated)
├── backend/
│   ├── Dockerfile
│   ├── requirements.txt
│   ├── main.py
│   ├── alembic.ini
│   ├── alembic/
│   │   └── versions/
│   │       ├── 0001_initial_schema.py             # tenants, users
│   │       ├── 0002_menu_and_training.py
│   │       ├── 0003_inventory_and_suppliers.py
│   │       ├── 0004_transactions_and_payments.py
│   │       ├── 0005_customers.py
│   │       ├── 0006_audit_and_openai_usage.py
│   │       └── 0007_settings_and_branding.py
│   ├── app/
│   │   ├── config.py
│   │   ├── database.py                    # SQLAlchemy + tenant filter event hook
│   │   ├── deps.py                        # get_tenant, get_current_user, require_role
│   │   ├── security.py                    # JWT, bcrypt (for reset only), Google verify, PIN hash
│   │   ├── websocket.py                   # per-tenant WS hub: cashier banners, low-conf alerts
│   │   ├── models/
│   │   │   ├── tenant.py
│   │   │   ├── tenant_settings.py         # Billplz creds, branding, thresholds
│   │   │   ├── user.py
│   │   │   ├── menu_item.py
│   │   │   ├── supplier.py
│   │   │   ├── purchase_order.py
│   │   │   ├── stock_movement.py
│   │   │   ├── transaction.py
│   │   │   ├── transaction_item.py
│   │   │   ├── payment.py
│   │   │   ├── receipt.py
│   │   │   ├── customer.py
│   │   │   ├── model_version.py
│   │   │   ├── training_job.py
│   │   │   ├── audit_log.py
│   │   │   └── openai_usage.py
│   │   ├── schemas/                       # Pydantic DTOs
│   │   ├── routers/
│   │   │   ├── auth.py                    # /auth/google, /auth/staff/login, /auth/logout
│   │   │   ├── admin.py                   # /admin/tenants (gated by ADMIN_EMAILS)
│   │   │   ├── users.py                   # owner manages cashiers (PINs)
│   │   │   ├── settings.py                # Billplz + branding + thresholds
│   │   │   ├── menu.py                    # CRUD + /menu/bulk CSV
│   │   │   ├── detect.py                  # cascade
│   │   │   ├── train.py                   # queue + "train now"
│   │   │   ├── transaction.py             # list + detail + void + qr request
│   │   │   ├── payment.py                 # /payments/webhook
│   │   │   ├── receipt.py                 # /receipts/{tx}/email + /receipts/{tx}/pdf
│   │   │   ├── inventory.py
│   │   │   ├── supplier.py
│   │   │   ├── purchase_order.py
│   │   │   ├── customer.py
│   │   │   ├── dashboard.py
│   │   │   ├── forecast.py
│   │   │   ├── reports.py
│   │   │   ├── ask.py
│   │   │   └── audit.py
│   │   └── services/
│   │       ├── detection/
│   │       │   ├── cascade.py             # orchestrator
│   │       │   ├── yolo_service.py
│   │       │   ├── mediapipe_service.py
│   │       │   ├── openai_service.py      # pHash cache + quota
│   │       │   └── fuzzy_match.py         # MediaPipe → menu shortlist
│   │       ├── training.py                # batched fine-tune job
│   │       ├── video_frame_extract.py     # ffmpeg + middle frame for product image
│   │       ├── billplz.py                 # per-tenant client
│   │       ├── resend_mailer.py
│   │       ├── receipt_pdf.py             # reportlab with logo + footer
│   │       ├── forecast.py                # EWMA + safety stock
│   │       ├── reorder.py                 # EOQ
│   │       ├── anomaly.py                 # z-score daily revenue
│   │       ├── audit.py
│   │       ├── autovoid_worker.py         # RQ scheduler every 60s
│   │       └── uploads.py                 # local disk handler
│   ├── ml_models/<tenant_id>/             # per-tenant YOLO weights
│   ├── training_data/<tenant_id>/         # per-tenant dataset
│   ├── uploads/<tenant_id>/
│   │   ├── logo.png
│   │   ├── products/<item_id>.jpg
│   │   └── videos/<job_id>.mp4
│   ├── backups/                           # pg_dump rotation
│   └── scripts/
│       ├── create_tenant.py
│       ├── seed_demo_tenant.py
│       └── run_backup.sh
├── frontend/
│   └── geyam_pos/
│       ├── lib/
│       │   ├── main.dart                  # kIsWeb switch → Landing or Login
│       │   ├── config/
│       │   │   ├── api_config.dart
│       │   │   └── theme.dart
│       │   ├── providers/
│       │   │   ├── auth_provider.dart
│       │   │   ├── theme_provider.dart
│       │   │   ├── connectivity_provider.dart   # offline banner
│       │   │   └── notification_provider.dart   # WebSocket listener
│       │   ├── services/
│       │   │   ├── api_service.dart
│       │   │   ├── google_auth_service.dart
│       │   │   ├── websocket_service.dart
│       │   │   └── receipt_service.dart
│       │   ├── screens/
│       │   │   ├── landing_screen.dart
│       │   │   ├── login_screen.dart              # Owner Google + Staff PIN tabs
│       │   │   ├── pos_screen.dart                # cashier
│       │   │   ├── menu_picker_screen.dart        # zero-detection fallback
│       │   │   ├── cart_detail_screen.dart
│       │   │   ├── dashboard_screen.dart
│       │   │   ├── mobile_owner_dashboard.dart
│       │   │   ├── transactions_list_screen.dart
│       │   │   ├── transaction_detail_screen.dart
│       │   │   ├── menu_manager_screen.dart       # CRUD + CSV
│       │   │   ├── csv_preview_screen.dart
│       │   │   ├── training_screen.dart           # queue + Train Now
│       │   │   ├── inventory_screen.dart
│       │   │   ├── purchase_order_screen.dart
│       │   │   ├── po_receive_screen.dart
│       │   │   ├── supplier_screen.dart
│       │   │   ├── customers_screen.dart
│       │   │   ├── staff_manager_screen.dart
│       │   │   ├── settings_screen.dart           # Billplz + branding + thresholds
│       │   │   ├── audit_log_screen.dart
│       │   │   └── reports_screen.dart
│       │   └── widgets/
│       │       ├── landing_hero.dart
│       │       ├── landing_nav.dart
│       │       ├── sales_chart.dart               # fl_chart
│       │       ├── kpi_card.dart
│       │       ├── low_stock_badge.dart
│       │       ├── confidence_badge.dart          # green / yellow
│       │       ├── offline_banner.dart
│       │       └── notification_banner.dart
│       └── pubspec.yaml
├── data/
│   ├── seed_demo_tenant.sql
│   └── sample_menu.csv
├── docs/
│   ├── ALGORITHMS.md
│   └── SETUP.md
└── hostinger/
    ├── index.html                         # Flutter web build output
    └── demo.mp4                           # landing demo
```

---

## Database Schema (PostgreSQL)

Every table except `tenants` carries `tenant_id`. Every query is filtered by tenant via FastAPI dependency + SQLAlchemy event hook.

```sql
-- ============ TENANTS + USERS ============

CREATE TABLE tenants (
    id           SERIAL PRIMARY KEY,
    handle       VARCHAR(50) UNIQUE NOT NULL,
    name         VARCHAR(100) NOT NULL,
    owner_email  VARCHAR(255) UNIQUE NOT NULL,
    is_active    BOOLEAN DEFAULT TRUE,
    created_at   TIMESTAMP DEFAULT NOW()
);

CREATE TABLE users (
    id            SERIAL PRIMARY KEY,
    tenant_id     INTEGER NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    username      VARCHAR(80) NOT NULL,
    email         VARCHAR(255),                    -- owner only (Google)
    google_sub    VARCHAR(255) UNIQUE,             -- owner only
    pin_hash      VARCHAR(255),                    -- cashier only (bcrypt of 6-digit PIN)
    role          VARCHAR(20) NOT NULL CHECK (role IN ('owner','cashier')),
    is_active     BOOLEAN DEFAULT TRUE,
    created_at    TIMESTAMP DEFAULT NOW(),
    UNIQUE (tenant_id, username)
);

CREATE INDEX idx_users_tenant ON users(tenant_id);

-- ============ TENANT SETTINGS ============

CREATE TABLE tenant_settings (
    tenant_id              INTEGER PRIMARY KEY REFERENCES tenants(id) ON DELETE CASCADE,
    billplz_api_key        VARCHAR(255),           -- encrypted at rest (Fernet)
    billplz_collection_id  VARCHAR(100),
    billplz_xsign_key      VARCHAR(255),           -- encrypted
    billplz_mode           VARCHAR(10) DEFAULT 'sandbox' CHECK (billplz_mode IN ('sandbox','production')),
    logo_path              TEXT,
    receipt_footer         TEXT DEFAULT 'Thank you! Goods sold are not refundable.',
    shop_contact_email     VARCHAR(255),
    shop_contact_phone     VARCHAR(30),
    yolo_conf_threshold    REAL DEFAULT 0.60,
    yolo_conf_minimum      REAL DEFAULT 0.40,      -- below this, fall through to MediaPipe
    openai_daily_limit     INTEGER DEFAULT 50,
    training_locked_at     TIMESTAMP,              -- non-null = training in progress; prevents concurrent Train Now
    updated_at             TIMESTAMP DEFAULT NOW()
);

-- ============ MENU ============

CREATE TABLE menu_items (
    id             SERIAL PRIMARY KEY,
    tenant_id      INTEGER NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    name           VARCHAR(100) NOT NULL,
    label          VARCHAR(80) NOT NULL,           -- YOLO class label
    price          DECIMAL(8,2) NOT NULL,
    category       VARCHAR(50),
    barcode        VARCHAR(64),
    stock_qty      INTEGER DEFAULT 0,
    reorder_point  INTEGER DEFAULT 5,
    avg_cost       DECIMAL(8,2) DEFAULT 0,
    image_path     TEXT,                           -- /uploads/<tenant>/products/<id>.jpg
    is_active      BOOLEAN DEFAULT TRUE,
    frame_count    INTEGER DEFAULT 0,
    created_at     TIMESTAMP DEFAULT NOW(),
    updated_at     TIMESTAMP DEFAULT NOW(),
    UNIQUE (tenant_id, label),
    UNIQUE (tenant_id, name)                       -- enforces CSV upsert by name
);

CREATE INDEX idx_menu_tenant_active ON menu_items(tenant_id, is_active);

-- ============ TRAINING JOBS ============

CREATE TABLE training_jobs (
    id             SERIAL PRIMARY KEY,
    tenant_id      INTEGER NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    menu_item_id   INTEGER REFERENCES menu_items(id),
    video_path     TEXT NOT NULL,
    status         VARCHAR(20) NOT NULL CHECK (status IN ('queued','training','done','failed')),
    frames_extracted INTEGER DEFAULT 0,
    error          TEXT,
    queued_at      TIMESTAMP DEFAULT NOW(),
    started_at     TIMESTAMP,
    finished_at    TIMESTAMP
);

-- ============ SUPPLIERS + PURCHASE ORDERS ============

CREATE TABLE suppliers (
    id          SERIAL PRIMARY KEY,
    tenant_id   INTEGER NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    name        VARCHAR(100) NOT NULL,
    contact     VARCHAR(100),
    email       VARCHAR(255),
    phone       VARCHAR(30),
    notes       TEXT,
    created_at  TIMESTAMP DEFAULT NOW()
);

CREATE TABLE purchase_orders (
    id           SERIAL PRIMARY KEY,
    tenant_id    INTEGER NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    supplier_id  INTEGER REFERENCES suppliers(id),
    status       VARCHAR(20) NOT NULL CHECK (status IN ('draft','sent','partial','received','cancelled')),
    expected_at  DATE,
    received_at  TIMESTAMP,
    created_by   INTEGER REFERENCES users(id),
    total_cost   DECIMAL(10,2) DEFAULT 0,
    created_at   TIMESTAMP DEFAULT NOW()
);

CREATE TABLE purchase_order_items (
    id                SERIAL PRIMARY KEY,
    po_id             INTEGER REFERENCES purchase_orders(id) ON DELETE CASCADE,
    menu_item_id      INTEGER REFERENCES menu_items(id),
    quantity_ordered  INTEGER NOT NULL,
    quantity_received INTEGER DEFAULT 0,
    unit_cost         DECIMAL(8,2) NOT NULL
);

-- ============ STOCK MOVEMENTS (ledger) ============

CREATE TABLE stock_movements (
    id            SERIAL PRIMARY KEY,
    tenant_id     INTEGER NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    menu_item_id  INTEGER REFERENCES menu_items(id),
    delta         INTEGER NOT NULL,
    reason        VARCHAR(40) NOT NULL CHECK (reason IN
                    ('sale','po_receive','adjust_damage','adjust_loss',
                     'adjust_theft','adjust_miscount','adjust_expired','adjust_other')),
    ref_type      VARCHAR(40),
    ref_id        INTEGER,
    note          TEXT,
    created_by    INTEGER REFERENCES users(id),
    created_at    TIMESTAMP DEFAULT NOW()
);

CREATE INDEX idx_stock_tenant_item ON stock_movements(tenant_id, menu_item_id);

-- ============ CUSTOMERS ============

CREATE TABLE customers (
    id           SERIAL PRIMARY KEY,
    tenant_id    INTEGER NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    name         VARCHAR(100),
    email        VARCHAR(255),
    phone        VARCHAR(30),
    notes        TEXT,
    created_at   TIMESTAMP DEFAULT NOW()
);

CREATE INDEX idx_customers_tenant_email ON customers(tenant_id, email);

-- ============ TRANSACTIONS ============

CREATE SEQUENCE IF NOT EXISTS tx_daily_seq;  -- daily counter, reset via app logic

CREATE TABLE transactions (
    id              SERIAL PRIMARY KEY,
    tenant_id       INTEGER NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    tx_number       VARCHAR(30) NOT NULL,             -- e.g. GY20260420-0042
    staff_id        INTEGER REFERENCES users(id),
    customer_id     INTEGER REFERENCES customers(id),
    total           DECIMAL(10,2) NOT NULL,
    payment_method  VARCHAR(20) NOT NULL DEFAULT 'qr',  -- 'cash' | 'qr'
    payment_ref     VARCHAR(100),
    status          VARCHAR(20) NOT NULL CHECK (status IN ('pending','paid','voided')),
    created_at      TIMESTAMP DEFAULT NOW(),
    paid_at         TIMESTAMP,
    voided_at       TIMESTAMP,
    voided_by       INTEGER REFERENCES users(id),      -- NULL when auto-voided
    UNIQUE (tenant_id, tx_number)
);

CREATE INDEX idx_tx_tenant_date ON transactions(tenant_id, created_at DESC);

CREATE TABLE transaction_items (
    id              SERIAL PRIMARY KEY,
    transaction_id  INTEGER REFERENCES transactions(id) ON DELETE CASCADE,
    menu_item_id    INTEGER REFERENCES menu_items(id),
    quantity        INTEGER DEFAULT 1,
    unit_price      DECIMAL(8,2) NOT NULL,
    confidence      REAL,
    source          VARCHAR(20) CHECK (source IN ('yolo','mediapipe','openai','manual'))
);

-- ============ PAYMENTS (Billplz per-tenant) ============

CREATE TABLE payments (
    id              SERIAL PRIMARY KEY,
    tenant_id       INTEGER NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    transaction_id  INTEGER REFERENCES transactions(id) ON DELETE CASCADE,
    provider        VARCHAR(20) NOT NULL DEFAULT 'billplz',
    bill_id         VARCHAR(100),
    bill_url        TEXT,
    amount          DECIMAL(10,2),
    state           VARCHAR(20),                     -- due / paid / deleted
    paid_at         TIMESTAMP,
    raw_payload     JSONB,
    created_at      TIMESTAMP DEFAULT NOW()
);

-- ============ RECEIPTS ============

CREATE TABLE receipts (
    id             SERIAL PRIMARY KEY,
    tenant_id      INTEGER NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    transaction_id INTEGER UNIQUE REFERENCES transactions(id) ON DELETE CASCADE,
    pdf_path       TEXT,
    emailed_to     VARCHAR(255),
    emailed_at     TIMESTAMP,
    resend_id      VARCHAR(100),
    created_at     TIMESTAMP DEFAULT NOW()
);

-- ============ MODEL VERSIONS ============

CREATE TABLE model_versions (
    id            SERIAL PRIMARY KEY,
    tenant_id     INTEGER NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    filename      VARCHAR(255) NOT NULL,
    num_classes   INTEGER NOT NULL,
    accuracy      REAL,
    is_active     BOOLEAN DEFAULT FALSE,
    trained_at    TIMESTAMP DEFAULT NOW(),
    notes         TEXT
);

-- ============ AUDIT LOG (indefinite retention) ============

CREATE TABLE audit_logs (
    id          BIGSERIAL PRIMARY KEY,
    tenant_id   INTEGER NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    user_id     INTEGER REFERENCES users(id),
    action      VARCHAR(80) NOT NULL,               -- see audit events list below
    entity      VARCHAR(40),
    entity_id   INTEGER,
    meta        JSONB,
    created_at  TIMESTAMP DEFAULT NOW()
);

CREATE INDEX idx_audit_tenant_date ON audit_logs(tenant_id, created_at DESC);

-- ============ OPENAI DAILY QUOTA ============

CREATE TABLE openai_usage (
    id          SERIAL PRIMARY KEY,
    tenant_id   INTEGER NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    day         DATE NOT NULL,
    calls       INTEGER DEFAULT 0,
    UNIQUE (tenant_id, day)
);
```

### Audited Actions (complete list)

```
auth.login_success     auth.login_fail       auth.logout
menu.create            menu.update           menu.delete        menu.restore   menu.bulk_upsert
inventory.adjust       stock.sale            stock.po_receive
po.create              po.send               po.receive         po.cancel
supplier.create        supplier.update       supplier.delete    supplier.restore
tx.create              tx.void               tx.auto_void       tx.pay         tx.override_void
customer.create        customer.update
settings.billplz       settings.branding     settings.thresholds   settings.billplz_mode
user.create            user.update           user.deactivate    user.reset_pin
training.queue         training.start        training.success   training.fail   training.blocked
report.export          ask.query             openai.call        openai.quota_exceeded
admin.impersonate      admin.tenant_create
```

### Transaction Number Generator

```python
# services/tx_numbering.py (pseudocode)
# Called inside the create-transaction transaction; uses SELECT FOR UPDATE.
def next_tx_number(session, tenant_id: int) -> str:
    today = date.today().strftime('%Y%m%d')
    # daily count per tenant
    count = session.execute(
        "SELECT COUNT(*) FROM transactions WHERE tenant_id=:t AND tx_number LIKE :p FOR UPDATE",
        {"t": tenant_id, "p": f"GY{today}-%"}
    ).scalar()
    return f"GY{today}-{count+1:04d}"
```

---

## docker-compose.yml

```yaml
version: "3.9"

services:
  db:
    image: postgres:16-alpine
    environment:
      POSTGRES_USER: pos_user
      POSTGRES_PASSWORD: pos_pass
      POSTGRES_DB: geyam
    ports:
      - "5432:5432"
    volumes:
      - pgdata:/var/lib/postgresql/data
      - ./backend/backups:/backups
    restart: unless-stopped

  redis:
    image: redis:7-alpine
    ports:
      - "6379:6379"
    restart: unless-stopped

  backend:
    build: ./backend
    ports:
      - "8000:8000"
    depends_on:
      - db
      - redis
    environment:
      DATABASE_URL: postgresql+asyncpg://pos_user:pos_pass@db:5432/geyam
      REDIS_URL: redis://redis:6379/0
      MODEL_DIR: /app/ml_models
      TRAINING_DATA_DIR: /app/training_data
      UPLOADS_DIR: /app/uploads
      GOOGLE_CLIENT_ID: ${GOOGLE_CLIENT_ID}
      GOOGLE_CLIENT_SECRET: ${GOOGLE_CLIENT_SECRET}
      JWT_SECRET: ${JWT_SECRET}
      FERNET_KEY: ${FERNET_KEY}             # for Billplz creds at rest
      RESEND_API_KEY: ${RESEND_API_KEY}
      OPENAI_API_KEY: ${OPENAI_API_KEY}
      OLLAMA_HOST: http://host.docker.internal:11434
      ADMIN_EMAILS: ${ADMIN_EMAILS}
    volumes:
      - ./backend:/app
      - ./backend/ml_models:/app/ml_models
      - ./backend/training_data:/app/training_data
      - ./backend/uploads:/app/uploads
      - ./backend/backups:/app/backups
    restart: unless-stopped

  worker:
    build: ./backend
    command: rq worker --url redis://redis:6379/0 geyam
    depends_on: [redis, db]
    environment:
      DATABASE_URL: postgresql+asyncpg://pos_user:pos_pass@db:5432/geyam
      REDIS_URL: redis://redis:6379/0
      MODEL_DIR: /app/ml_models
      UPLOADS_DIR: /app/uploads
    volumes:
      - ./backend:/app
      - ./backend/ml_models:/app/ml_models
      - ./backend/training_data:/app/training_data
      - ./backend/uploads:/app/uploads
    restart: unless-stopped

  scheduler:
    build: ./backend
    command: python -m app.services.autovoid_worker    # runs every 60s
    depends_on: [redis, db]
    environment:
      DATABASE_URL: postgresql+asyncpg://pos_user:pos_pass@db:5432/geyam
      REDIS_URL: redis://redis:6379/0
    volumes:
      - ./backend:/app
    restart: unless-stopped

  backup:
    image: postgres:16-alpine
    depends_on: [db]
    entrypoint: ["sh","-c"]
    command: >
      "while true; do
         pg_dump -h db -U pos_user geyam | gzip > /backups/geyam_$$(date +%Y%m%d_%H%M).sql.gz;
         find /backups -name 'geyam_*.sql.gz' -mtime +7 -delete;
         sleep 86400;
       done"
    environment:
      PGPASSWORD: pos_pass
    volumes:
      - ./backend/backups:/backups
    restart: unless-stopped

volumes:
  pgdata:
```

---

## API Endpoints

All except landing, `/health`, `/auth/*`, and `/payments/webhook` require JWT. JWT contains `tenant_id`, `user_id`, `role`. `get_tenant` filters every query.

| Method | Endpoint                         | Role    | What It Does |
|--------|----------------------------------|---------|--------------|
| GET    | `/health`                        | public  | Liveness |
| POST   | `/auth/google`                   | public  | Google id_token → JWT (must match a tenant owner) |
| POST   | `/auth/staff/login`              | public  | tenant_handle + username + PIN → JWT |
| POST   | `/auth/logout`                   | any     | Audit entry; invalidate client token |
| POST   | `/auth/refresh`                  | any     | Refresh token → new access token (owner 24h / cashier 12h) |
| GET    | `/me`                            | any     | Current user + tenant info + settings subset |
| POST   | `/admin/tenants`                 | admin   | Create tenant (gated by ADMIN_EMAILS) |
| GET    | `/admin/tenants`                 | admin   | List tenants |
| GET    | `/users`                         | owner   | List cashiers |
| POST   | `/users`                         | owner   | Create cashier (auto username staffN.<handle>) |
| PATCH  | `/users/{id}`                    | owner   | Reset PIN, deactivate |
| DELETE | `/users/{id}`                    | owner   | Soft-delete cashier |
| GET    | `/settings`                      | owner   | Get tenant settings |
| PATCH  | `/settings`                      | owner   | Update Billplz creds / branding / thresholds |
| POST   | `/settings/logo`                 | owner   | Upload shop logo (multipart) |
| GET    | `/menu`                          | any     | List active menu items |
| POST   | `/menu`                          | owner   | Create one menu item |
| POST   | `/menu/bulk`                     | owner   | CSV → preview+upsert by name |
| PATCH  | `/menu/{id}`                     | owner   | Edit |
| DELETE | `/menu/{id}`                     | owner   | Soft-delete (is_active=false) |
| POST   | `/menu/{id}/restore`             | owner   | Reactivate soft-deleted item |
| POST   | `/menu/{id}/image`               | owner   | Manual image upload (overrides video-extracted) |
| POST   | `/train/video`                   | owner   | Upload video → enqueue training_job (status=queued) |
| POST   | `/train/run`                     | owner   | Train Now → batch-process all queued jobs |
| GET    | `/train/jobs`                    | owner   | Queue + history |
| GET    | `/model/status`                  | owner   | Active model + version history |
| POST   | `/detect`                        | cashier | Image → cascade → items + confidence + source |
| POST   | `/transaction`                   | cashier | Create pending (returns tx_number GY...-NNNN) |
| POST   | `/transaction/{id}/qr`           | cashier | Request Billplz QR via tenant creds |
| POST   | `/transaction/{id}/void`         | cashier | Manual void (pending only) |
| POST   | `/transaction/{id}/override-void`| owner   | Void a PAID transaction with reason (restores stock) |
| GET    | `/transactions`                  | owner   | Paginated list with filters |
| GET    | `/transactions/{id}`             | any     | Full detail |
| POST   | `/payments/webhook`              | public  | Billplz callback (x-signature verified) |
| POST   | `/receipts/{tx_id}/email`        | any     | Send receipt email |
| GET    | `/receipts/{tx_id}/pdf`          | any     | Download PDF |
| GET    | `/inventory`                     | owner   | Stock status |
| POST   | `/inventory/adjust`              | owner   | Manual adjustment (reason dropdown) |
| GET    | `/suppliers`                     | owner   | List |
| POST   | `/suppliers`                     | owner   | Create |
| PATCH  | `/suppliers/{id}`                | owner   | Edit |
| DELETE | `/suppliers/{id}`                | owner   | Soft-delete |
| POST   | `/suppliers/{id}/restore`        | owner   | Reactivate soft-deleted supplier |
| GET    | `/purchase-orders`               | owner   | List |
| POST   | `/purchase-orders`               | owner   | Create (draft) |
| POST   | `/purchase-orders/{id}/send`     | owner   | Mark sent |
| POST   | `/purchase-orders/{id}/receive`  | owner   | Partial/full receive |
| POST   | `/purchase-orders/{id}/cancel`   | owner   | Cancel |
| GET    | `/customers`                     | any     | List |
| POST   | `/customers`                     | cashier | Create (from checkout dialog) |
| GET    | `/dashboard`                     | owner   | KPIs (today by default; range query) |
| GET    | `/dashboard/mobile`              | owner   | Slim version for mobile |
| GET    | `/forecast`                      | owner   | EWMA + safety stock |
| GET    | `/reports?format=csv\|xlsx\|pdf` | owner   | Sales + items + staff + valuation |
| POST   | `/ask`                           | owner   | Ollama phi3:mini Q&A |
| GET    | `/audit`                         | owner   | Paginated |
| WS     | `/ws`                            | any     | Authenticated WebSocket; tenant-scoped channel |

---

## Detection Cascade — Critical Feature Detail

```
Request:  tenant_id, image_bytes
Response: {
  items: [{menu_item_id, name, price, confidence, source, needs_confirm}],
  source_breakdown: {yolo: n, mediapipe: n, openai: n},
  errors: [...]
}

1. Preprocess
   - Resize longest edge → 1280px
   - CLAHE (contrast limited adaptive histogram equalization)
   - Compute pHash (perceptual hash)

2. Stage A — Tenant YOLO
   - Load ml_models/<tenant_id>/best.pt (LRU cache, last 3 tenants in memory)
   - Run inference; NMS iou=0.45
   - For each detection:
       conf ≥ settings.yolo_conf_threshold (default 0.60) → accept, source='yolo',
         needs_confirm=false
       settings.yolo_conf_minimum (0.40) ≤ conf < 0.60 → accept, source='yolo',
         needs_confirm=true  (yellow badge)
       conf < 0.40 → drop
   - If at least one accepted → done; otherwise fall through

3. Stage B — MediaPipe EfficientDet-Lite0
   - Run detector on same preprocessed image
   - For each MediaPipe detection label (e.g. 'bottle','cup','box'):
       Look up category alias table:
         bottle,cup,can → category='drink'
         box,bowl,package → category='snack'
       Find candidates = tenant's active menu_items in that category
       If 1 candidate → add with source='mediapipe', needs_confirm=true
       If >1 candidates → add placeholder {shortlist: [candidates]}; cashier picks
   - If still nothing → fall through

4. Stage C — OpenAI Vision (gated)
   - pHash cache check (Redis key cv:{tenant_id}:{phash}, 7-day TTL); if hit → return cached
   - Quota check: SELECT calls FROM openai_usage WHERE tenant_id=:t AND day=CURRENT_DATE
     If calls ≥ settings.openai_daily_limit (default 50) → emit audit 'openai.quota_exceeded',
       return empty with error flag
   - Call gpt-4o-mini with prompt:
       "You see packaged food/drink items on a tray. Return JSON array of items you are
        confident about: [{name, brand?, type}]. Only include items you can name clearly."
   - Fuzzy-match each name to tenant menu_items (rapidfuzz partial_ratio ≥ 80)
   - Cache result against pHash
   - Increment openai_usage.calls
   - All results marked source='openai', needs_confirm=true

5. Post-process
   - Deduplicate overlapping detections
   - Attach unit_price from menu_items
   - Return with source_breakdown
```

---

## Billplz QR Flow (per-tenant creds)

```
1. Cashier confirms cart → POST /transaction
   - Check: every line item quantity ≤ menu_items.stock_qty (block sale otherwise)
   - Generate tx_number = GY{YYYYMMDD}-{daily_seq}
   - Insert with status='pending'

2. POST /transaction/{id}/qr
   - Load tenant_settings.billplz_api_key (decrypt via Fernet)
   - POST https://www.billplz.com/api/v3/bills:
       collection_id: tenant_settings.billplz_collection_id
       email: tenant_settings.shop_contact_email
       name: tx_number
       amount: total*100 (sen)
       description: tx_number
       callback_url: https://api.geyam.com/payments/webhook
       reference_1: tenant_id
       reference_2: transaction_id
   - Insert payments row (bill_id, bill_url, state='due')
   - Return bill_url to client

3. POST /payments/webhook
   - Read x-signature header
   - Locate tenant via reference_1; look up xsign_key; verify HMAC-SHA256
   - Locate payments by bill_id → transaction
   - If webhook state='paid' AND transaction.status='pending':
       BEGIN TRANSACTION
         transaction.status='paid', paid_at=NOW(), payment_method='qr', payment_ref=bill_id
         For each line item: create stock_movements (delta=-qty, reason='sale')
                             menu_items.stock_qty -= qty
         audit: 'tx.pay'
         If transaction.customer_id is not NULL:
           enqueue receipt_email job
         Send WebSocket message to cashier: {type: 'tx_paid', tx_number}
       COMMIT
   - Return 200

4. Frontend: after QR shown, open WebSocket; on 'tx_paid' event → show success
   (polling fallback every 3s if WebSocket fails)
```

---

## Auto-Void Worker (10-min timeout)

```python
# services/autovoid_worker.py (pseudocode)
# Runs as its own scheduler container; 60-second loop.

while True:
    expired = session.query(Transaction)\
        .filter(Transaction.status == 'pending',
                Transaction.created_at < now() - timedelta(minutes=10))\
        .all()
    for tx in expired:
        tx.status = 'voided'
        tx.voided_at = now()
        tx.voided_by = None   # NULL = system
        audit_log('tx.auto_void', entity='transaction', entity_id=tx.id)
        ws_send(tenant_id=tx.tenant_id,
                payload={'type': 'tx_autovoid', 'tx_number': tx.tx_number, 'staff_id': tx.staff_id})
    sleep(60)
```

---

## Cashier Staff Naming + PIN

- Owner's handle derived from email local-part at tenant creation: `brianchenjunhao@gmail.com` → handle `brianchenjunhao`.
- Cashier usernames auto-generated: `staff1.brianchenjunhao`, `staff2.brianchenjunhao`, …
- Owner sets a 6-digit PIN per cashier. Stored as bcrypt hash.
- Login payload: `{tenant_handle, username, pin}` → backend resolves tenant → validates.
- PIN reset: owner opens Staff Manager → "Reset PIN" → sets new 6-digit value.
- No email, no password, no 2FA required for cashiers.

---

## Algorithmic Optimizations

```
1. Cascade detection ladder
   YOLO (conf ≥ 0.60)                       → green
   YOLO (0.40 ≤ conf < 0.60)                → yellow (confirm)
   MediaPipe category alias (single match)   → yellow
   MediaPipe category alias (shortlist)      → cashier picks
   OpenAI gpt-4o-mini (quota-capped, cached) → yellow always
   Manual menu grid                          → fallback

2. pHash cache for OpenAI (Redis, 7-day TTL)
   Prevents repeat charges on identical tray angles.

3. NMS iou=0.45 for overlapping detections
   Prevents double-counting same can.

4. Active-learning queue
   All non-YOLO detections saved to training_data/<tenant>/pending_review/
   Next Train Now batch can include them after owner confirmation.

5. EWMA forecast per item
   d̂_t = α · d_{t-1} + (1-α) · d̂_{t-1}, α=0.3

6. Safety stock
   ss = z · σ · √lead_time, z=1.65 (95% service level)

7. Reorder point (ROP)
   ROP = d̂ · lead_time + ss
   Powers the "Low Stock" dashboard card.

8. Economic Order Quantity (EOQ)
   EOQ = √(2 · annual_demand · order_cost / holding_cost)
   Pre-fills quantity on Create PO form.

9. Anomaly detection via z-score
   On daily revenue vs trailing 30 days.
   z > 2 or < -2 → dashboard flag + audit entry.

10. Frame deduplication during training
    Drop frames with Hamming distance of pHash < 4.
    Keeps training set diverse without bloat.

11. Model hot-reload LRU cache
    Keep last 3 tenants' active models warm; evict oldest.

12. Tenant-isolation SQLAlchemy event hook
    Every SELECT auto-appends WHERE tenant_id = :ctx_tenant.
    Integration test: Tenant A session querying Tenant B rows returns empty.

13. Index strategy
    (tenant_id, created_at DESC) on transactions, audit_logs, stock_movements.
    Every dashboard query uses the first column.

14. Offline-graceful client
    Flutter connectivity_plus watches the network; banner blocks POST while offline.
    GETs fall back to last-cached menu for read-only scanning demo.

15. Stretch (Phase 12 only): ONNX + INT8 YOLO quantization.
```

---

## Informative Dashboard

```
Header: Range chip (Today • 7d • 30d • Custom) · Anomaly badge · Tenant name

Row 1 — KPI cards:
  [ Revenue ]  [ Transactions ]  [ Avg basket ]  [ Top item ]

Row 2:
  [ Revenue bar chart (fl_chart) ]         [ Top 5 items horizontal bar chart ]

Row 3:
  [ Low-stock list (clickable → item) ]    [ Pending POs (clickable → PO) ]

Row 4:
  [ Detection source donut:                ][ Staff performance table:
    yolo / mediapipe / openai / manual ]     staff, tx count, revenue, avg conf ]

Row 5:
  [ Recent transactions (last 10) — click row → Transaction Detail ]

Row 6 (collapsible):
  [ Audit feed (last 20) ]
```

---

## Mobile Owner Light Dashboard

```
Screen 1: Today KPIs (revenue, tx count)
Screen 2: Low-stock alerts list (tap → item detail)
Screen 3: Recent transactions list (tap → transaction detail)
Screen 4: Ask AI text box (POST /ask → phi3:mini response)
```

---

## Transactions List → Detail

```
GET /transactions?from=YYYY-MM-DD&to=YYYY-MM-DD&staff_id=&status=&page=&page_size=

Columns: TX number | Date | Staff | Items | Total | Payment | Status

Click row → GET /transactions/{id}:
  Header: TX number (GY20260420-0042), date, staff, customer (or 'Walk-in'), status badge
  Line items: name | qty | unit_price | confidence badge | source badge
  Totals: subtotal, total
  Payment: method, Billplz bill_id (link opens bill_url), paid_at, raw payload (JSON collapse)
  Actions:
    - Email receipt (if customer attached or new email typed)
    - Download PDF
    - Void (only if status=pending; otherwise disabled)
  Audit trail: filtered by entity='transaction', entity_id=this
```

---

## Receipt PDF Layout

```
┌─────────────────────────────────────────┐
│  [Logo]                                 │
│  {shop_name}                            │
│  {shop_contact_email} · {shop_phone}    │
├─────────────────────────────────────────┤
│  TX GY20260420-0042                     │
│  Paid: 2026-04-20 14:35  (Asia/KL)      │
│  Cashier: staff1.brianchenjunhao         │
│  Customer: {name or 'Walk-in'}          │
├─────────────────────────────────────────┤
│  Item               Qty   Unit    Total │
│  Milo Can            2    2.50    5.00  │
│  Chipster            1    3.00    3.00  │
├─────────────────────────────────────────┤
│  TOTAL                        RM 8.00   │
│  Payment: DuitNow QR (Billplz)          │
├─────────────────────────────────────────┤
│  {receipt_footer}                       │
└─────────────────────────────────────────┘
```

Generated with ReportLab; stored under `uploads/<tenant>/receipts/<tx_id>.pdf`; linked from `receipts.pdf_path`.

---

## Demo Tenant Seed (static, never resets)

Run once via `python scripts/seed_demo_tenant.py`:

```
tenants:
  handle='demo', name='Demo Shop', owner_email='demo@geyam.com'
users:
  username='demo' (role=owner; google_sub=NULL; direct login disabled)
  staff1.demo, staff2.demo (cashiers, PIN=123456 each)

Impersonation flow for demo owner view:
  - Any Gmail in ADMIN_EMAILS (default: brianchen.crisp@gmail.com) can hit
    POST /admin/tenants/{id}/impersonate → returns a JWT with role='owner'
    scoped to that tenant.
  - Audit entry 'admin.impersonate' recorded every time.
  - Use case: screencasts, debugging, demo walkthroughs.
tenant_settings:
  Billplz sandbox creds; logo = assets/demo_logo.png; footer = default
menu_items: 15 packaged items with stock + reorder_points
suppliers: 3
purchase_orders: 2 received + 1 pending
customers: 10 (names + emails generated)
transactions: 500 across last 60 days
  - Random cashier, random items, random day
  - ~70% 'cash' 30% 'qr' for variety
  - Generate stock_movements and matching audit entries
  - Inject 2 anomaly days (revenue z-score > 2)
model_versions: one row referencing yolov8n.pt baseline
```

---

## Migration Strategy (fresh start)

No Stage 1 backfill. Alembic still owns the schema so future migrations are clean.

```
alembic/versions/
  0001_initial_schema.py           tenants, users
  0002_menu_and_training.py        menu_items, training_jobs, model_versions
  0003_inventory_and_suppliers.py  suppliers, purchase_orders, po_items, stock_movements
  0004_transactions_and_payments.py transactions, transaction_items, payments, receipts
  0005_customers.py                customers + transaction FK
  0006_audit_and_openai_usage.py   audit_logs, openai_usage
  0007_settings_and_branding.py    tenant_settings
```

Command: `alembic upgrade head` runs on backend container startup.

---

## Build Order

```
PHASE 0 — Pre-deployment external setup (do this first, offline from code)
──────────────────────────────────────────────
  A. Google Cloud Console: add redirect URIs
     - https://geyam.com/auth/callback
     - http://localhost:XXXX/auth/callback (Flutter dev)
     Save GOOGLE_CLIENT_ID + GOOGLE_CLIENT_SECRET to .env
  B. Cloudflare DNS for geyam.com (Cloudflare is the active nameserver):
     - Add SPF TXT record (Resend will provide)
     - Add DKIM TXT/CNAME records (Resend will provide)
     - Set the Resend records to DNS-only (grey cloud), NOT proxied (orange cloud) — Cloudflare will rewrite proxied email records and break verification
     - Keep existing A / CNAME that point geyam.com to Hostinger static hosting
  C. Resend dashboard:
     - Verify geyam.com domain (takes 5-30 min after DNS)
     - Create noreply@geyam.com sender
     - Save RESEND_API_KEY to .env
  D. Billplz sandbox:
     - Create sandbox account + sandbox collection
     - Save SANDBOX creds for demo tenant seed
  E. Ollama on your laptop:
     - ollama pull phi3:mini
     - verify: ollama run phi3:mini
  F. Generate FERNET_KEY for Billplz cred encryption:
     - python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
     → save to .env as FERNET_KEY
  G. Put brianchen.crisp@gmail.com in ADMIN_EMAILS

PHASE 1 — Stage 2 skeleton boots
──────────────────────────────────────────────
  1. docker-compose up -d db redis                → ping both
  2. Scaffold alembic + 0001_initial_schema         → alembic upgrade head clean
  3. FastAPI /health + CORS + StaticFiles on /uploads → curl /health = 200
  4. RQ worker container boots                      → logs "waiting for jobs"
  5. Auto-void scheduler container boots             → logs "heartbeat"
  6. .env + Fernet key generation script             → secrets loaded, no crashes

PHASE 2 — Multi-tenancy foundation (HIGHEST RISK, FIRST)
──────────────────────────────────────────────
  7. Apply 0002+0007 migrations                     → all tables + settings
  8. SQLAlchemy event hook: filter every SELECT by tenant_id
  9. get_tenant() dep + JWT claims                  → 401 without token; 403 across tenants
  10. Integration test: Tenant A session querying Tenant B data returns empty → MUST PASS
  11. scripts/create_tenant.py CLI                  → inserts tenant + owner row
  12. /admin/tenants gated by ADMIN_EMAILS          → only your Gmail can access

PHASE 3 — Auth: Google OAuth + Cashier PIN
──────────────────────────────────────────────
  13. POST /auth/google verifies id_token           → matches tenants.owner_email → JWT
  14. POST /auth/staff/login (handle+username+PIN)  → bcrypt check → JWT
  15. POST /users auto-username 'staffN.<handle>'   → create cashier + bcrypt PIN
  16. PATCH /users/{id} reset_pin                    → audit entry
  17. require_role('owner') / ('cashier')            → 403 otherwise
  18. Audit login success/fail/logout                → rows appear

PHASE 4 — Settings + branding
──────────────────────────────────────────────
  19. 0007 settings table exists                    → GET /settings returns defaults
  20. PATCH /settings with Billplz creds (Fernet encrypted) → decrypt roundtrip
  21. POST /settings/logo multipart                 → file saved to uploads/<tenant>/logo.png
  22. Receipt footer / shop contact fields          → UI round-trip via Flutter web

PHASE 5 — Menu CRUD + CSV bulk + images
──────────────────────────────────────────────
  23. Apply 0002 + menu_items indexes               → CRUD all 4 verbs
  24. POST /menu/bulk CSV (upsert by name)          → sample_menu.csv imports 15 items
  25. Manual image upload POST /menu/{id}/image     → stored locally, image_path set
  26. Video upload queues training_job + extracts middle-frame image
      ffmpeg -i video.mp4 -vf "select=eq(n\,$((N/2)))" -frames:v 1 middle.jpg
  27. Menu Manager + CSV Preview Flutter screens     → live editing works

PHASE 6 — Training (batched, Train Now)
──────────────────────────────────────────────
  28. POST /train/video saves video, enqueues job    → training_jobs row status=queued
  29. Video limits enforced (≤30 sec, ≤100 MB)        → rejected with clean error
  30. POST /train/run acquires per-tenant lock        → 409 if training_locked_at not null
  31. ffmpeg fps=2 + auto label (centered 0.8x0.8)   → frames saved
  32. YOLO fine-tune, save ml_models/<tenant>/best.pt → accuracy recorded
  33. Release training lock on success AND on failure → second run works next time
  34. On failure: job status='failed', old model stays active, WebSocket banner to owner
  35. Hot-reload model in-memory LRU                  → next /detect uses new weights

PHASE 7 — Detection cascade
──────────────────────────────────────────────
  34. yolo_service returns raw detections with confidence
  35. mediapipe_service + category alias table + shortlist builder
  36. openai_service with pHash cache + quota check
  37. cascade.py orchestrates; returns source + needs_confirm per item
  38. Unit tests per stage in isolation                → each stage testable alone
  39. POST /detect returns combined response           → Postman test with 3 fixture images

PHASE 8 — Transactions + Billplz + webhook + auto-void
──────────────────────────────────────────────
  40. Apply 0004 + 0005 migrations
  41. tx_number generator (GY{YYYYMMDD}-{N})          → concurrent test: 2 parallel creates → unique
  42. POST /transaction with stock-check guard        → rejects insufficient stock
  43. Reject /transaction/{id}/qr if Billplz creds missing → clear error to cashier
  44. POST /transaction/{id}/qr (per-tenant creds, Fernet decrypt, sandbox/prod URL switch)
  45. POST /payments/webhook (x-signature verify)     → manual replay of sandbox webhook → 200
  46. Stock decrement inside webhook TX               → stock_movements + menu_items.stock_qty
  47. autovoid_worker loop every 60s                   → stale pending TX voided + ws notify
  48. Cashier void endpoint (pending only)            → audit 'tx.void'
  49. Owner override-void (paid TX) with reason       → restores stock, audit 'tx.override_void'
  50. "Re-check Billplz" button on transaction detail → polls Billplz for a missed webhook

PHASE 9 — Receipts (PDF + email)
──────────────────────────────────────────────
  48. receipt_pdf.py renders with logo + footer + itemized
  49. On webhook success + customer attached → enqueue email via Resend
  50. POST /receipts/{tx_id}/email manual button     → retries possible
  51. GET /receipts/{tx_id}/pdf returns file

PHASE 10 — Inventory + POs + suppliers + customers
──────────────────────────────────────────────
  52. Suppliers CRUD                                  → /suppliers works
  53. PO draft → sent → partial → received flow      → stock_movements created
  54. Weighted-avg cost recomputation on receive      → menu_items.avg_cost updated
  55. Low-stock endpoint (stock_qty ≤ reorder_point)  → returns items
  56. /inventory/adjust with reason dropdown          → stock_movements written
  57. Customers CRUD; attach to TX at checkout

PHASE 11 — Dashboard + algorithms + reports + LLM
──────────────────────────────────────────────
  58. forecast.py EWMA + safety_stock                 → /forecast returns per-item
  59. reorder.py EOQ                                  → Create PO pre-fills quantity
  60. anomaly.py z-score                              → flag appears on dashboard
  61. GET /dashboard aggregate query                  → < 200ms on demo seed
  62. GET /reports CSV/XLSX/PDF (all 4 sections)      → files downloadable
  63. POST /ask → Ollama phi3:mini with KPI context   → answers cite real numbers

PHASE 12 — Audit + WebSocket + offline
──────────────────────────────────────────────
  64. Audit service hooks on every mutation          → all 40+ action types emit rows
  65. GET /audit paginated                            → renders on web
  66. WebSocket /ws with per-tenant channels          → tx_paid, tx_autovoid, low_conf alerts
  67. Flutter notification_provider listens + banner
  68. connectivity_provider blocks mutations offline → tested in airplane mode

PHASE 13 — Frontend (Flutter web + mobile)
──────────────────────────────────────────────
  69. Landing screen (kIsWeb) with demo.mp4 autoplay muted loop
  70. Login screen with Owner (Google) / Cashier (PIN) tabs
  71. Manager dashboard with all widgets + fl_chart   → charts render on live data
  72. Transactions list + drill-down detail
  73. Menu Manager + CSV preview + image upload
  74. Training screen with queue + Train Now button
  75. Inventory / POs / Suppliers / Customers screens
  76. Settings (Billplz + branding + thresholds) with logo upload
  77. Cashier POS with confidence badges + low-stock badge + menu-picker fallback
  78. Shortlist picker dialog for MediaPipe ambiguous matches
  79. Customer attach dialog at checkout
  80. Receipt email manual button + PDF download
  81. Audit log screen + Reports screen
  82. Mobile owner light dashboard (4 cards + ask input)

PHASE 14 — Demo seed + deploy
──────────────────────────────────────────────
  83. scripts/seed_demo_tenant.py populates demo tenant
  84. Build Flutter web → upload to Hostinger (geyam.com)
  85. Upload demo.mp4 next to index.html
  86. Cloudflare Tunnel to localhost:8000 as api.geyam.com
  87. Register Billplz sandbox callback URL
  88. Sleep-prevention + systemd/launchd service for backend auto-restart
  89. End-to-end on phone: scan → QR → webhook → email receipt arrives

PHASE 15 — Only if time
──────────────────────────────────────────────
  90. ONNX + INT8 quantization for YOLO
  91. Telegram bot for owner quick queries
  92. Scheduled daily email summary
```

---

## Minimum Viable Demo (Stage 2)

If everything else fails, these six things working is a pass:

1. You create Tenant B via CLI → owner (Brian) logs in via Google (2FA via Google) → lands on empty dashboard
2. Owner adds menu via CSV + creates 2 cashiers with PINs → cashier logs in with tenant_handle + username + PIN
3. Owner uploads 2 product videos, hits Train Now → new model recognizes both items
4. Cashier scans tray → YOLO detects item A high-conf, MediaPipe shortlist picks item B, OpenAI finds item C (all sources visible) → pending TX created
5. DuitNow QR via Billplz → sandbox webhook → status=paid, stock decremented, email receipt (with logo + footer) delivered
6. Low-stock alert appears on dashboard → owner creates + receives a PO → stock recovered; audit log shows every step; Tenant B's data is invisible to Tenant A

---

## Anti-Mistake Habits

- Git branch per phase; commit after every ticked step
- Run tenant-isolation integration test after every query-level change
- Test each endpoint with curl/Postman before touching Flutter
- Webhook FIRST, UI later — Billplz webhook is the highest-risk integration
- Keep OpenAI quota visible on dashboard every day; watch for abuse
- Hardcode your own tenant handle (`brianchenjunhao`) during dev; generalize only after Phase 2 is green
- Write Alembic migrations forward-only; test each upgrade on a throwaway DB copy first
- One terminal per service (backend, worker, scheduler, db logs, cloudflared)
- If stuck more than 10 minutes, stub the dependency and move on

---

## Theme & Design Continuity (carried from Stage 1)

```
LIGHT MODE
  Background : #FFFFFF
  Surface    : #F5F5F5
  Text       : #1A1A1A
  Primary    : #000080  (Navy Blue)
  Accent     : #1E90FF

DARK MODE  (default)
  Background : #000080  (Navy Blue)
  Surface    : #000066
  Text       : #F0F0F0
  Primary    : #4DA6FF
  Accent     : #1E90FF
  Card BG    : #00004D

Additions for Stage 2:
  Success (green badge, high-confidence detection)   : #2ECC71
  Warning (yellow badge, low-confidence / confirm)   : #F1C40F
  Error   (red banner, stock block / webhook fail)   : #E74C3C
  Info    (blue banner, auto-void / offline)         : #3498DB
```

Toggle stored in local state. Default: dark mode on every build (web, mobile). Language: English only for Stage 2.

---

## Step Numbering Note

Step numbers in the Build Order are guides, not strict sequences. Phases 6 and 8 were expanded during scope-locking; later phases keep their original numbering but you may see small overlaps. The phase structure and the ordering of steps within each phase are what matter; renumber as you implement.

---

## Key Risks

- **Scope vs deadline**: 2–4 weeks for all of this on laptop is tight. Expect Phase 15 skipped and some of Phase 12 thinned. If slipping, drop WebSocket (fall back to polling) and drop OpenAI stage (show "quota exceeded" permanently).
- **Tenant isolation bugs** are the worst class. Land the event hook + integration test in Phase 2. Do not proceed to Phase 3 until that test is green.
- **Billplz webhook reachability**: Cloudflare Tunnel must stay up; laptop must not sleep. Add a "Re-check Billplz" button on transaction detail so a missed webhook can be reconciled manually.
- **Per-tenant Billplz creds** means encryption at rest. Use `cryptography.fernet` with `FERNET_KEY` env var. Losing the key means all Billplz creds must be re-entered.
- **OpenAI cost runaway**: default cap is 50/day/tenant (~$1.50/month max per tenant). Owner can raise it in Settings — watch for misconfigurations.
- **MediaPipe → menu mapping is heuristic**: category alias table is hand-curated. If it returns bad shortlists, tweak aliases in `fuzzy_match.py` or let cashier override via manual grid.
- **Concurrent tx_number collisions**: use `SELECT ... FOR UPDATE` inside the creating transaction to serialize. Avoids duplicates under racy cashier taps.
- **Fresh-start choice**: no Stage 1 data is preserved. Make sure the FYP demo you already have is screencast-captured before wiping.