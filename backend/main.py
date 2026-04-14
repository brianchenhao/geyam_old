from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.database import init_db
from app.routers import detect, menu, train, transaction
from app.services import yolo_service


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    # Warm up YOLO cache so first /detect request is fast.
    try:
        yolo_service.get_model()
    except Exception:
        pass
    yield


app = FastAPI(title="GEYAM API", lifespan=lifespan)
app.include_router(train.router)
app.include_router(menu.router)
app.include_router(detect.router)
app.include_router(transaction.router)


@app.get("/health")
def health():
    return {"status": "ok"}
