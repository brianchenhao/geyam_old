from fastapi import FastAPI

app = FastAPI(title="GEYAM API")


@app.get("/health")
def health():
    return {"status": "ok"}
