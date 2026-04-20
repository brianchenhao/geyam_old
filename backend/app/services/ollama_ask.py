"""Tiny wrapper around the local Ollama HTTP API for /ask."""
import os
import httpx

DEFAULT_MODEL = os.environ.get("OLLAMA_MODEL", "phi3:mini")
DEFAULT_HOST = os.environ.get("OLLAMA_HOST", "http://localhost:11434")


def ask(prompt: str, *, context: str = "", model: str | None = None) -> str:
    full = f"{context}\n\nQuestion: {prompt}\nAnswer concisely."
    payload = {"model": model or DEFAULT_MODEL, "prompt": full, "stream": False}
    try:
        r = httpx.post(f"{DEFAULT_HOST}/api/generate", json=payload, timeout=60)
        r.raise_for_status()
        data = r.json()
        return data.get("response", "").strip()
    except Exception as e:
        return f"(ollama unavailable: {type(e).__name__})"
