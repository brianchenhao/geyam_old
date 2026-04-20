"""Fernet helpers for encrypting per-tenant Billplz credentials at rest.
Key comes from FERNET_KEY env; generated once via scripts/gen_fernet.py."""
import os

from cryptography.fernet import Fernet, InvalidToken

_KEY = os.getenv("FERNET_KEY")
if not _KEY:
    raise RuntimeError("FERNET_KEY not set; run backend/scripts/gen_fernet.py")

_fernet = Fernet(_KEY.encode())


def encrypt(plain: str | None) -> str | None:
    if not plain:
        return None
    return _fernet.encrypt(plain.encode("utf-8")).decode("utf-8")


def decrypt(cipher: str | None) -> str | None:
    if not cipher:
        return None
    try:
        return _fernet.decrypt(cipher.encode("utf-8")).decode("utf-8")
    except InvalidToken:
        return None
