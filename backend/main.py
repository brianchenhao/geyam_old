from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.database import init_db


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    yield


app = FastAPI(title="GEYAM API", lifespan=lifespan)


@app.get("/health")
def health():
    return {"status": "ok"}
