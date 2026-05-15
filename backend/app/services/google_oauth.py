"""Verify a Google ID token OR access token and return the claims we care about (sub + email)."""
from typing import Any

import httpx
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


def verify_google_access_token(access_token: str) -> dict[str, Any]:
    """Verify a Google OAuth2 access token via tokeninfo, then fetch userinfo for sub+email.

    Used on Flutter web where google_sign_in 6.x returns access_token but not id_token.
    Trust boundary: we only trust Google's response, not the raw token.
    """
    if not GOOGLE_CLIENT_ID:
        raise ValueError("GOOGLE_CLIENT_ID not configured")
    # tokeninfo validates the token is live and audience-matches our client id
    r = httpx.get(
        "https://oauth2.googleapis.com/tokeninfo",
        params={"access_token": access_token},
        timeout=10,
    )
    if r.status_code != 200:
        raise ValueError(f"tokeninfo rejected access_token: {r.status_code}")
    info = r.json()
    if info.get("aud") != GOOGLE_CLIENT_ID and info.get("azp") != GOOGLE_CLIENT_ID:
        raise ValueError("access_token audience mismatch")
    # userinfo gives us sub + email with email_verified
    u = httpx.get(
        "https://openidconnect.googleapis.com/v1/userinfo",
        headers={"Authorization": f"Bearer {access_token}"},
        timeout=10,
    )
    if u.status_code != 200:
        raise ValueError(f"userinfo rejected access_token: {u.status_code}")
    claims = u.json()
    if "sub" not in claims or "email" not in claims:
        raise ValueError("userinfo missing sub or email")
    return claims
