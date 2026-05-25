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
GOOGLE_CLIENT_ID = os.getenv("GOOGLE_CLIENT_ID", "")
GOOGLE_CLIENT_SECRET = os.getenv("GOOGLE_CLIENT_SECRET", "")
RESEND_API_KEY = os.getenv("RESEND_API_KEY", "")
RESEND_FROM = os.getenv("RESEND_FROM", "noreply@geyam.com")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")

# Ensure dirs exist (safe on every boot)
for _d in (MODEL_DIR, TRAINING_DATA_DIR, UPLOADS_DIR):
    _d.mkdir(parents=True, exist_ok=True)
