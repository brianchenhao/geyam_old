"""Verify a Google ID token and return the claims we care about (sub + email)."""
from typing import Any

from google.auth.transport import requests as g_requests
from google.oauth2 import id_token as google_id_token

from app.config import GOOGLE_CLIENT_ID


def verify_google_id_token(raw_token: str) -> dict[str, Any]:
    """Raises ValueError on any problem (expired, bad audience, wrong signer)."""
    if not GOOGLE_CLIENT_ID:
        raise ValueError("GOOGLE_CLIENT_ID not configured")
    claims = google_id_token.verify_oauth2_token(
        raw_token, g_requests.Request(), GOOGLE_CLIENT_ID
    )
    if claims.get("iss") not in ("accounts.google.com", "https://accounts.google.com"):
        raise ValueError("bad token issuer")
    if "sub" not in claims or "email" not in claims:
        raise ValueError("token missing sub or email")
    return claims
