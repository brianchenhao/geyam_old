"""Phase 4 gate: Billplz creds round-trip through Fernet cleanly."""
import os
import sys
from pathlib import Path

from cryptography.fernet import Fernet

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
os.environ.setdefault("FERNET_KEY", Fernet.generate_key().decode())

from app.services import crypto  # noqa: E402


def test_roundtrip_ok():
    plain = "sk_test_abc123xyz_whatever_very_secret"
    cipher = crypto.encrypt(plain)
    assert cipher is not None and cipher != plain
    assert crypto.decrypt(cipher) == plain


def test_none_passthrough():
    assert crypto.encrypt(None) is None
    assert crypto.encrypt("") is None
    assert crypto.decrypt(None) is None
    assert crypto.decrypt("") is None


def test_bad_cipher_returns_none():
    assert crypto.decrypt("not-a-real-fernet-token") is None
