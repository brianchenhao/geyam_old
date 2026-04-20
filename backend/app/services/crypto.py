"""Fernet encryption for sensitive per-tenant secrets (Billplz credentials).

The FERNET_KEY env var is the only thing that can decrypt stored ciphertext.
If the key is lost, every tenant must re-enter their Billplz credentials.
"""
from cryptography.fernet import Fernet, InvalidToken

from app.config import FERNET_KEY

_cipher: Fernet | None = None


def _get_cipher() -> Fernet:
    global _cipher
    if _cipher is None:
        if not FERNET_KEY:
            raise RuntimeError("FERNET_KEY not configured")
        _cipher = Fernet(FERNET_KEY.encode())
    return _cipher


def encrypt_secret(plain: str | None) -> str | None:
    if plain is None or plain == "":
        return None
    return _get_cipher().encrypt(plain.encode()).decode()


def decrypt_secret(token: str | None) -> str | None:
    if token is None or token == "":
        return None
    try:
        return _get_cipher().decrypt(token.encode()).decode()
    except InvalidToken:
        # Row was written with a different key (or corrupted). Surface as None
        # so callers can prompt the owner to re-enter creds.
        return None
