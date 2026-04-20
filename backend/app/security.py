"""JWT encode/decode + password/PIN hashing helpers."""
from datetime import datetime, timedelta, timezone
from typing import Any

import bcrypt
import jwt

from app.config import JWT_ALGORITHM, JWT_SECRET

OWNER_TOKEN_HOURS = 24
CASHIER_TOKEN_HOURS = 12
REFRESH_TOKEN_DAYS = 30


def issue_access_token(*, tenant_id: int, user_id: int, role: str) -> str:
    if role not in ("owner", "cashier"):
        raise ValueError(f"bad role {role!r}")
    hours = OWNER_TOKEN_HOURS if role == "owner" else CASHIER_TOKEN_HOURS
    payload = {
        "tenant_id": tenant_id,
        "user_id": user_id,
        "role": role,
        "exp": datetime.now(timezone.utc) + timedelta(hours=hours),
        "iat": datetime.now(timezone.utc),
        "type": "access",
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)


def issue_admin_token(*, email: str) -> str:
    """Admin tokens are NOT tenant-scoped — they can hit /admin/* only."""
    payload = {
        "email": email,
        "role": "admin",
        "exp": datetime.now(timezone.utc) + timedelta(hours=OWNER_TOKEN_HOURS),
        "type": "admin",
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)


def decode_token(token: str) -> dict[str, Any]:
    return jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])


def hash_pin(pin: str) -> str:
    if not (pin.isdigit() and len(pin) == 6):
        raise ValueError("PIN must be exactly 6 digits")
    return bcrypt.hashpw(pin.encode(), bcrypt.gensalt()).decode()


def verify_pin(pin: str, pin_hash: str) -> bool:
    return bcrypt.checkpw(pin.encode(), pin_hash.encode())
