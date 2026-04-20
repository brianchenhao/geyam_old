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

# Stage 2 routers land phase-by-phase starting in Phase 2 (auth, admin).
# Stage 1 routers are parked in app/routers/ for reference; do not import until
# they are rewritten to be tenant-scoped.


@app.get("/health")
def health():
    return {"status": "ok", "phase": "1", "stage": 2}
