from contextlib import asynccontextmanager

from pathlib import Path

from dotenv import load_dotenv

# Load backend/.env first (if present), then geyam/.env as fallback.
# Must run before app.* modules read env.
load_dotenv()
load_dotenv(Path(__file__).resolve().parent.parent / ".env")

from antsilk import AntsilkMiddleware
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

import asyncio

from app.config import UPLOADS_DIR
from app.database import init_db
from app.middleware.antsilk_setup import (
    RealClientIPMiddleware,
    antsilk_enabled,
    build_antsilk_config,
)
from app.services.chenki_menu_ask import warmup as chenki_warmup
from app.services.ws_broker import run_subscriber
from app.websocket import hub


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    broker_task = asyncio.create_task(run_subscriber(hub))
    # Fire chenki warmup as a detached task. HF Space cold-start is ~60s; we
    # must not block FastAPI boot on it. If the warmup fails, /menu/ask still
    # works once the Space wakes on the next real request.
    asyncio.create_task(chenki_warmup())
    try:
        yield
    finally:
        broker_task.cancel()
        try:
            await broker_task
        except Exception:
            pass


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

# Antsilk WAF + the CF-Connecting-IP shim. Starlette's add_middleware
# prepends to user_middleware and the stack is built reversed, so the LAST
# add_middleware call ends up OUTERMOST at request time. Calling
# RealClientIPMiddleware last means it rewrites scope["client"] before
# AntsilkMiddleware inspects it. ANTSILK_ENABLED=false flips the kill
# switch for emergency rollback without redeploying.
if antsilk_enabled():
    app.add_middleware(AntsilkMiddleware, config=build_antsilk_config())
    app.add_middleware(RealClientIPMiddleware)

from app.routers import admin as admin_router  # noqa: E402
from app.routers import admin_audit as admin_audit_router  # noqa: E402
from app.routers import alerts as alerts_router  # noqa: E402
from app.routers import antsilk_admin as antsilk_admin_router  # noqa: E402
from app.routers import auth as auth_router  # noqa: E402
from app.routers import detect as detect_router  # noqa: E402
from app.routers import health as health_router  # noqa: E402
from app.routers import menu as menu_router  # noqa: E402
from app.routers import onboarding as onboarding_router  # noqa: E402
from app.routers import audit as audit_router  # noqa: E402
from app.routers import dashboard as dashboard_router  # noqa: E402
from app.routers import inventory as inventory_router  # noqa: E402
from app.routers import payment as payment_router  # noqa: E402
from app.routers import receipt as receipt_router  # noqa: E402
from app.routers import settings as settings_router  # noqa: E402
from app.routers import subscriptions as subscriptions_router  # noqa: E402
from app.routers import train as train_router  # noqa: E402
from app.routers import transaction as transaction_router  # noqa: E402
from app.routers import users as users_router  # noqa: E402
from app.routers import ws as ws_router  # noqa: E402
app.include_router(admin_router.router)
app.include_router(admin_audit_router.router)
app.include_router(auth_router.router)
app.include_router(users_router.router)
app.include_router(settings_router.router)
app.include_router(menu_router.router)
app.include_router(train_router.router)
app.include_router(detect_router.router)
app.include_router(transaction_router.router)
app.include_router(payment_router.router)
app.include_router(receipt_router.router)
app.include_router(inventory_router.router)
app.include_router(dashboard_router.router)
app.include_router(audit_router.router)
app.include_router(subscriptions_router.router)
app.include_router(onboarding_router.router)
app.include_router(ws_router.router)
app.include_router(health_router.router)
app.include_router(alerts_router.router)
app.include_router(antsilk_admin_router.router)


@app.get("/health")
def health():
    return {"status": "ok", "phase": "13", "stage": 3}
