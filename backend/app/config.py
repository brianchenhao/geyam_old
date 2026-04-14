import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent  # backend/

DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql+asyncpg://pos_user:pos_pass@localhost:5432/geyam",
)

MODEL_DIR = Path(os.getenv("MODEL_DIR", str(BASE_DIR / "ml_models")))
TRAINING_DATA_DIR = Path(
    os.getenv("TRAINING_DATA_DIR", str(BASE_DIR / "training_data"))
)
