from contextlib import asynccontextmanager

from pathlib import Path

from dotenv import load_dotenv

# Load backend/.env first (if present), then geyam/.env as fallback.
# Must run before app.* modules read env.
load_dotenv()
load_dotenv(Path(__file__).resolve().parent.parent / ".env")

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.database import init_db
from app.routers import ask, auth, detect, forecast, menu, train, transaction
from app.services import yolo_service


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    try:
        yolo_service.get_model()
    except Exception:
        pass
    yield


app = FastAPI(title="GEYAM API", lifespan=lifespan)

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

app.include_router(auth.router)
app.include_router(train.router)
app.include_router(menu.router)
app.include_router(detect.router)
app.include_router(transaction.router)
app.include_router(forecast.router)
app.include_router(ask.router)


@app.get("/health")
def health():
    return {"status": "ok"}
