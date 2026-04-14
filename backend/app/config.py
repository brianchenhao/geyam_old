import os

DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql+asyncpg://pos_user:pos_pass@localhost:5432/geyam",
)
