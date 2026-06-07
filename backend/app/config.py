import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent  # backend/

DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql+asyncpg://pos_user:pos_pass@localhost:5433/geyam",
)
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6380/0")

MODEL_DIR = Path(os.getenv("MODEL_DIR", str(BASE_DIR / "ml_models")))
TRAINING_DATA_DIR = Path(os.getenv("TRAINING_DATA_DIR", str(BASE_DIR / "training_data")))
UPLOADS_DIR = Path(os.getenv("UPLOADS_DIR", str(BASE_DIR / "uploads")))

# Stage 2 secrets (loaded from backend/.env via load_dotenv in main.py)
JWT_SECRET = os.getenv("JWT_SECRET", "change-me")
JWT_ALGORITHM = os.getenv("JWT_ALGORITHM", "HS256")
FERNET_KEY = os.getenv("FERNET_KEY", "")
ADMIN_EMAILS = [e.strip() for e in os.getenv("ADMIN_EMAILS", "").split(",") if e.strip()]
# Phase 10: admins can only impersonate this single demo tenant. Paying tenants
# are off-limits to mitigate "support session" being a back door into customer
# data. Override per env for local dev; defaults to the seed shop.
DEMO_TENANT_HANDLE = os.getenv("DEMO_TENANT_HANDLE", "brianmart")
GOOGLE_CLIENT_ID = os.getenv("GOOGLE_CLIENT_ID", "")
GOOGLE_CLIENT_SECRET = os.getenv("GOOGLE_CLIENT_SECRET", "")
RESEND_API_KEY = os.getenv("RESEND_API_KEY", "")
RESEND_FROM = os.getenv("RESEND_FROM", "noreply@geyam.com")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")

# Stage 3 Phase 9 — Stripe billing.
# Test-mode keys begin with sk_test_ / pk_test_ / whsec_; live-mode swap is the
# Phase 9 step 11 cutover (one env var change + restart, no code change).
STRIPE_API_KEY = os.getenv("STRIPE_API_KEY", "")
STRIPE_PUBLISHABLE_KEY = os.getenv("STRIPE_PUBLISHABLE_KEY", "")
STRIPE_WEBHOOK_SECRET = os.getenv("STRIPE_WEBHOOK_SECRET", "")
STRIPE_PRICE_PRO = os.getenv("STRIPE_PRICE_PRO", "")
STRIPE_PRICE_BUSINESS = os.getenv("STRIPE_PRICE_BUSINESS", "")
# Where Stripe sends the user back after Checkout / Portal sessions.
# Defaults are dev-friendly; ops override to https://app.geyam.com/... in prod.
STRIPE_CHECKOUT_SUCCESS_URL = os.getenv(
    "STRIPE_CHECKOUT_SUCCESS_URL", "http://localhost:8080/billing/success",
)
STRIPE_CHECKOUT_CANCEL_URL = os.getenv(
    "STRIPE_CHECKOUT_CANCEL_URL", "http://localhost:8080/billing/cancel",
)
STRIPE_PORTAL_RETURN_URL = os.getenv(
    "STRIPE_PORTAL_RETURN_URL", "http://localhost:8080/billing",
)

# Ensure dirs exist (safe on every boot)
for _d in (MODEL_DIR, TRAINING_DATA_DIR, UPLOADS_DIR):
    _d.mkdir(parents=True, exist_ok=True)
