from contextlib import asynccontextmanager

from pathlib import Path

from dotenv import load_dotenv

# Load backend/.env first (if present), then geyam/.env as fallback.
# Must run before app.* modules read env.
load_dotenv()
load_dotenv(Path(__file__).resolve().parent.parent / ".env")

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.config import UPLOADS_DIR
from app.database import init_db


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    yield


app = FastAPI(title="GEYAM API", lifespan=lifespan)

# Per-tenant uploads served at /uploads/<tenant_id>/... (logos, product images, receipts).
app.mount("/uploads", StaticFiles(directory=str(UPLOADS_DIR)), name="uploads")

# This laptop serves both the public site (geyam.com via Cloudflare tunnel)
# and local dev (Flutter web on any localhost port), so allow both at once.
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "https://geyam.com",
        "https://www.geyam.com",
    ],
    allow_origin_regex=r"http://(localhost|127\.0\.0\.1):\d+",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

from app.routers import admin as admin_router  # noqa: E402
from app.routers import auth as auth_router  # noqa: E402
from app.routers import settings as settings_router  # noqa: E402
from app.routers import users as users_router  # noqa: E402
app.include_router(admin_router.router)
app.include_router(auth_router.router)
app.include_router(users_router.router)
app.include_router(settings_router.router)


@app.get("/health")
def health():
    return {"status": "ok", "phase": "4", "stage": 2}
