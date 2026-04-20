"""Phase 8 gate: webhook signature accept/reject."""
import hashlib
import hmac
import os
import sys
from pathlib import Path
from unittest.mock import MagicMock

from cryptography.fernet import Fernet

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
os.environ.setdefault("FERNET_KEY", Fernet.generate_key().decode())

from app.services import billplz, crypto  # noqa: E402


def _sign(secret: str, form: dict[str, str]) -> str:
    src = "|".join(f"{k}{v}" for k, v in sorted(form.items()) if k != "x_signature")
    return hmac.new(secret.encode(), src.encode(), hashlib.sha256).hexdigest()


def _settings(xsign_plain: str):
    s = MagicMock()
    s.billplz_xsign_key = crypto.encrypt(xsign_plain)
    return s


def test_webhook_accepts_valid_signature():
    secret = "my-xsign-key"
    form = {"id": "BP1", "paid": "true", "amount": "100", "state": "paid"}
    form["x_signature"] = _sign(secret, form)
    assert billplz.verify_webhook(_settings(secret), form) is True


def test_webhook_rejects_tampered_amount():
    secret = "my-xsign-key"
    form = {"id": "BP1", "paid": "true", "amount": "100"}
    sig = _sign(secret, form)
    form["amount"] = "1"  # attacker tampers
    form["x_signature"] = sig
    assert billplz.verify_webhook(_settings(secret), form) is False


def test_webhook_rejects_missing_sig():
    form = {"id": "BP1", "paid": "true"}
    assert billplz.verify_webhook(_settings("k"), form) is False


def test_verify_returns_false_when_key_missing():
    s = MagicMock()
    s.billplz_xsign_key = None
    assert billplz.verify_webhook(s, {"id": "x", "x_signature": "y"}) is False
