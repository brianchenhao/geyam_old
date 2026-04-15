from contextlib import asynccontextmanager

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

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
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
