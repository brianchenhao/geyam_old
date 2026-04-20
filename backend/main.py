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
from app.routers import detect as detect_router  # noqa: E402
from app.routers import menu as menu_router  # noqa: E402
from app.routers import customer as customer_router  # noqa: E402
from app.routers import inventory as inventory_router  # noqa: E402
from app.routers import payment as payment_router  # noqa: E402
from app.routers import purchase_order as po_router  # noqa: E402
from app.routers import receipt as receipt_router  # noqa: E402
from app.routers import settings as settings_router  # noqa: E402
from app.routers import supplier as supplier_router  # noqa: E402
from app.routers import train as train_router  # noqa: E402
from app.routers import transaction as transaction_router  # noqa: E402
from app.routers import users as users_router  # noqa: E402
app.include_router(admin_router.router)
app.include_router(auth_router.router)
app.include_router(users_router.router)
app.include_router(settings_router.router)
app.include_router(menu_router.router)
app.include_router(train_router.router)
app.include_router(detect_router.router)
app.include_router(transaction_router.router)
app.include_router(payment_router.router)
app.include_router(receipt_router.router)
app.include_router(supplier_router.router)
app.include_router(po_router.router)
app.include_router(inventory_router.router)
app.include_router(customer_router.router)


@app.get("/health")
def health():
    return {"status": "ok", "phase": "10", "stage": 2}
