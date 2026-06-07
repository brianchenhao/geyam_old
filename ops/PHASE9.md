# Phase 9 manual setup — Stripe billing

All the code is in place (`routers/subscriptions.py`, `services/stripe_service.py`,
`services/audit.py @audited`, `services/plan_enforcement.py`, `routers/admin_audit.py`,
`scripts/sweep_past_due.py`, Flutter `billing_screen.dart` + `suspended_banner.dart`).
This document is the human-only steps that depend on the Stripe Dashboard.

Time estimate: ~60 minutes total (45 min Dashboard setup + 15 min testing).

---

## Step A — Stripe account (10 min)

Where this happens: **stripe.com in a browser** (you, not Claude).

1. Go to https://dashboard.stripe.com/register.
2. Sign up with `brianchen.crisp@gmail.com` (same as Resend, for inbox consolidation).
3. When asked for **business country**, pick **Singapore**.
   - Why Singapore not Malaysia: Stripe supports MYR settlement out of Singapore;
     it does not have a full Malaysia entity yet. The plan locks this on line 596:
     "Singapore as primary jurisdiction".
4. Complete the "Tell us about your business" form (you can use placeholder values
   for now — verification can come later once revenue is real).
5. **Stay in test mode.** The toggle is in the top-right of the dashboard. Live
   mode requires identity verification + a real bank account — leave that to
   Phase 9 step 11 (the cutover).

After this you should see `Test mode` in the top-right and have access to
**Developers → API keys**.

---

## Step B — Create 3 products (10 min)

Where: **Stripe Dashboard → Product catalog → Add product**.

Create **two** products (Free is not a Stripe product — it's the absence of a
subscription, tracked locally):

| Product name | Price        | Billing period | Currency |
|--------------|--------------|----------------|----------|
| Geyam Pro    | RM 99.00     | Monthly        | MYR      |
| Geyam Business | RM 299.00  | Monthly        | MYR      |

For each:

1. Click **Add product**.
2. **Name**: `Geyam Pro` (or `Geyam Business`).
3. **Description**: anything — shown on the Stripe Checkout page. Suggested:
   `Geyam POS — Pro plan: 5 cashiers, 500 menu items, 500 AI vision calls/mo, 5 training videos/wk.`
4. Under **Pricing**:
   - **Price**: `99.00` (or `299.00`)
   - **Currency**: `Malaysian Ringgit (MYR)`
   - **Billing period**: `Monthly`
   - **Type**: `Recurring`
5. Click **Add product**.
6. On the product page, **copy the Price ID** (starts with `price_...`). You
   will need both in step D below.

> If MYR is not selectable: check Settings → Account details → confirm the
> account country is Singapore. Stripe SG accounts can transact in MYR.

---

## Step C — Webhook endpoint (10 min)

Where: **Stripe Dashboard → Developers → Webhooks → Add endpoint**.

1. **Endpoint URL**:
   - Production: `https://api.geyam.com/subscriptions/webhook`
   - Local testing: install the Stripe CLI (`stripe listen --forward-to localhost:9000/subscriptions/webhook`) — it issues a temporary `whsec_...` you can paste into `backend/.env`.
2. **Description**: `Geyam subscription state sync (Phase 9)`.
3. **Events to listen for** — pick these five (and only these):
   - `customer.subscription.created`
   - `customer.subscription.updated`
   - `customer.subscription.deleted`
   - `invoice.payment_failed`
   - `invoice.payment_succeeded`
4. Click **Add endpoint**.
5. On the endpoint detail page, click **Signing secret → Reveal**. Copy the
   value starting with `whsec_...` — this is `STRIPE_WEBHOOK_SECRET`.

---

## Step D — Populate `.env` (5 min)

Where: **your laptop** for local, **VPS** (`/opt/geyam/.env.production`) for production.

From the Stripe Dashboard, copy these values:

| Where to find it                                | env var name              |
|-------------------------------------------------|---------------------------|
| Developers → API keys → Secret key (test mode)  | `STRIPE_API_KEY`          |
| Developers → API keys → Publishable key         | `STRIPE_PUBLISHABLE_KEY`  |
| Webhooks → \<your endpoint\> → Signing secret   | `STRIPE_WEBHOOK_SECRET`   |
| Products → Geyam Pro → Price ID                 | `STRIPE_PRICE_PRO`        |
| Products → Geyam Business → Price ID            | `STRIPE_PRICE_BUSINESS`   |

### LOCAL — laptop dev (Windows)

Edit `C:\Programming_Local\geyam\geyam\backend\.env`, append:

```
STRIPE_API_KEY=sk_test_...
STRIPE_PUBLISHABLE_KEY=pk_test_...
STRIPE_WEBHOOK_SECRET=whsec_...
STRIPE_PRICE_PRO=price_...
STRIPE_PRICE_BUSINESS=price_...
STRIPE_CHECKOUT_SUCCESS_URL=http://localhost:8080/billing/success
STRIPE_CHECKOUT_CANCEL_URL=http://localhost:8080/billing/cancel
STRIPE_PORTAL_RETURN_URL=http://localhost:8080/billing
```

Then in PowerShell:

```powershell
cd C:\Programming_Local\geyam\geyam
docker compose build backend
docker compose up -d
```

`pip install -r requirements.txt` runs as part of the image build, so `stripe==11.5.0` lands the first time you rebuild.

### VPS — production

```bash
# On the VPS:
ssh deploy@api.geyam.com
nano /opt/geyam/.env.production
# Append the same five vars + the *.geyam.com URLs (already in ops/.env.production.example).
exit

# On your laptop:
./ops/deploy.sh
```

---

## Step E — Verify end-to-end (15 min)

LOCAL — laptop dev:

```powershell
# 1. Sign in as an owner in the Flutter app.
flutter run -d chrome -t lib/main.dart
# Open the drawer → "Billing". Should show "Current plan: FREE".

# 2. Click "Upgrade to Pro" → Stripe Checkout opens.
# Use Stripe's test card: 4242 4242 4242 4242, any future expiry, any CVC.

# 3. Complete payment. Stripe sends customer.subscription.created → /subscriptions/webhook.
# In a second PowerShell window, follow logs:
docker logs -f geyam-backend-1 | Select-String -Pattern "webhook"
# Expect: "received": true, "event_id": "evt_...", "outcome": {"plan": "pro", ...}

# 4. Refresh the Billing screen — should now say "Current plan: PRO".

# 5. Verify admin audit row was written:
docker exec geyam-db-1 psql -U pos_user -d geyam -c \
  "SELECT ts, actor_email, action, success FROM admin_audit_log ORDER BY id DESC LIMIT 5;"
# Expect a row with action=webhook.customer.subscription.created, success=t.

# 6. Cancel via Portal:
# In the app → Billing → "Manage payment / cancel in billing portal".
# Cancel the subscription in Stripe-hosted Portal.
# Stripe sends customer.subscription.deleted → status flips to canceled,
# next month's renewal won't fire.
```

If you do NOT use the Stripe CLI for local webhooks, you can still test the
checkout flow but will see "Current plan: FREE" until you manually trigger the
webhook via the Dashboard (`Webhooks → endpoint → Send test webhook`).

---

## Step F — Test mode → live mode cutover (Phase 9 step 11)

Don't do this until you are ready to take real money.

LOCAL:

1. In Stripe Dashboard, complete identity verification (Settings → Business
   settings → Verify your account). Bank account details for MYR payouts.
2. Toggle Dashboard from **Test mode** to **Live mode** (top-right).
3. Re-create the two products and webhook endpoint in live mode (test-mode
   resources are not copied).
4. Copy the live-mode keys + price IDs + webhook secret.

VPS:

```bash
ssh deploy@api.geyam.com
nano /opt/geyam/.env.production
# Replace sk_test_/pk_test_/whsec_ values with the live equivalents.
exit

# On your laptop:
./ops/deploy.sh
```

The plan acceptance test is "ONE real RM99 charge succeeds" — sign yourself up
as a fake tenant and pay yourself RM99 with a real card. Refund immediately via
Dashboard. That counts as Phase 9 step 11 done.

---

## Step G — Past-due sweeper cron (already in `ops/cron.geyam.example`)

```bash
ssh deploy@api.geyam.com
sudo crontab -e
# Append this line if it's not already there (it's also in ops/cron.geyam.example):
0 4 * * * docker exec geyam-backend-1 python -m scripts.sweep_past_due
```

Verify after the next 04:00:

```bash
docker exec geyam-db-1 psql -U pos_user -d geyam -c \
  "SELECT action, success, ts FROM admin_audit_log WHERE actor_email='system.sweeper' ORDER BY id DESC LIMIT 5;"
```

---

## What I still need from you (summary)

In order:

1. **Stripe account** (Step A) — your signup, your bank details for live mode.
2. **2 products + webhook endpoint** (Steps B–C) — Dashboard clicks; copy 5 IDs.
3. **Paste 5 env vars** (Step D) — into `backend/.env` and `/opt/geyam/.env.production`.
4. **Rebuild container** — `docker compose build backend && docker compose up -d` LOCAL, `./ops/deploy.sh` VPS.
5. **End-to-end smoke test** (Step E) — sign up, pay with test card, verify audit row.
6. **(Later) live-mode cutover** (Step F) — once you want real money.
7. **Cron entry** (Step G) — VPS only; one line in crontab.
