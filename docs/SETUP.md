# GEYAM Stage 2 — Setup + Deploy

This is the operational runbook for starting GEYAM from scratch on your laptop, seeding the demo shop, building the Flutter web bundle, and exposing the backend through Cloudflare Tunnel so `api.geyam.com` resolves to `localhost:9000`.

---

## 1. Prerequisites (one-time, per-machine)

1. **Docker Desktop** running (verify with `docker ps`).
2. **Flutter SDK** on PATH (`flutter --version`).
3. **Ollama** running locally with `phi3:mini` pulled (`ollama list`).
4. **Cloudflare Tunnel** `cloudflared` installed and already authenticated to the `geyam.com` zone.
5. **`backend/.env`** populated (see `.env.example` for the full key list):
   - `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET`
   - `RESEND_API_KEY`, `RESEND_FROM=noreply@geyam.com`
   - `BILLPLZ_SANDBOX_API_KEY`, `BILLPLZ_SANDBOX_COLLECTION_ID`, `BILLPLZ_SANDBOX_X_SIGNATURE`
   - `OPENAI_API_KEY`
   - `JWT_SECRET`, `FERNET_KEY`, `ADMIN_EMAILS`
   - `DATABASE_URL`, `REDIS_URL`

---

## 2. Boot the backend stack

```
cd "C:/Programming (Local)/FYP Claude/geyam"
docker compose up -d
curl http://localhost:9000/health
```

The first boot builds the `geyam-backend` image (6–7 min on a cold cache); later boots are near-instant. Alembic runs on every backend startup and migrates to the latest revision.

Verify all six services are healthy:

```
docker compose ps
```

You should see `db`, `redis`, `backend`, `worker`, `scheduler`, `backup` all up.

---

## 3. Create a real tenant

### Option A — CLI

```
docker compose exec backend python scripts/create_tenant.py \
  --email you@gmail.com --handle myshop --name "My Shop"
```

### Option B — Admin API

```
# 1. admin token
TOKEN=$(curl -s -X POST http://localhost:9000/admin/dev-login \
  -H "Content-Type: application/json" \
  -d '{"email":"brianchen.crisp@gmail.com"}' | jq -r .token)

# 2. create tenant
curl -X POST http://localhost:9000/admin/tenants \
  -H "Content-Type: application/json" -H "Authorization: Bearer $TOKEN" \
  -d '{"handle":"myshop","name":"My Shop","owner_email":"you@gmail.com"}'
```

The owner can now log in via Google OAuth using that email.

---

## 4. Seed the demo tenant

Populates a stable fixture that the landing page screencast uses. Idempotent — safe to re-run; pass `--wipe` to recreate from scratch.

```
docker compose exec backend python scripts/seed_demo_tenant.py
# or to reset:
docker compose exec backend python scripts/seed_demo_tenant.py --wipe
```

Creates:
- Tenant `demo` (owner `demo@geyam.com`)
- Settings with Billplz sandbox creds (encrypted)
- Two cashiers `staff1.demo`, `staff2.demo` (PIN `876543`)
- 15 menu items + initial stock
- 500 paid transactions across 60 days (with 2 anomaly days)
- 1 active `model_versions` row

---

## 5. Expose the backend as `api.geyam.com`

Cloudflare Tunnel should already point `api.geyam.com` → `localhost:9000`. To start the tunnel:

```
cloudflared tunnel --url http://localhost:9000 run geyam
```

On first setup only, make sure the tunnel config (`~/.cloudflared/config.yml`) maps the hostname:

```yaml
tunnel: <your-tunnel-id>
credentials-file: ~/.cloudflared/<your-tunnel-id>.json
ingress:
  - hostname: api.geyam.com
    service: http://localhost:9000
  - service: http_status:404
```

Verify externally:

```
curl https://api.geyam.com/health
```

---

## 6. Build + upload the Flutter web app

```
cd frontend/geyam_pos
flutter build web --release --dart-define=API_BASE_URL=https://api.geyam.com
```

The build lands in `build/web/`. Upload the contents to Hostinger `public_html/` (root of `geyam.com`) along with the demo video:

```
# from repo root:
cp hostinger/demo.mp4 frontend/geyam_pos/build/web/
# upload frontend/geyam_pos/build/web/* to Hostinger via File Manager or FTP
```

Visit `https://geyam.com` — the landing page (dark-mode hero) should load; clicking Login goes to the Owner/Cashier tab screen.

---

## 7. Android APK (sideload)

```
cd frontend/geyam_pos
flutter build apk --release --dart-define=API_BASE_URL=https://api.geyam.com
```

APK is at `build/app/outputs/flutter-apk/app-release.apk` — send it to the cashier's phone and install (allow unknown sources). Mobile build skips the landing page and opens the login screen directly.

---

## 8. Sleep prevention + auto-restart

For the laptop acting as the production server:

- **Windows**: run `powercfg /change standby-timeout-ac 0` to prevent sleep on AC power. Register the Docker Compose stack as a startup task via Task Scheduler.
- **macOS**: `caffeinate -d -i` in a terminal window that stays open, or register `cloudflared` + `docker compose up` as `launchd` services.

---

## 9. Healthcheck commands (copy-paste)

```
# backend
curl -s http://localhost:9000/health | jq

# tenant isolation pytest
docker compose exec backend pytest -xvs tests/test_tenant_isolation.py

# alembic revision
docker compose exec backend alembic current

# scheduler heartbeat
docker compose logs scheduler --tail=5

# worker listening
docker compose logs worker --tail=5

# backup files
ls backend/backups/
```
