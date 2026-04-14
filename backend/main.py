from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.database import init_db
from app.routers import menu, train


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    yield


app = FastAPI(title="GEYAM API", lifespan=lifespan)
app.include_router(train.router)
app.include_router(menu.router)


@app.get("/health")
def health():
    return {"status": "ok"}
