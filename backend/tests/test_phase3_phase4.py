"""Phase 3 (Auth) + Phase 4 (Settings) comprehensive validation.

Runs against the docker stack's Postgres via the app's own SessionLocal/ASGI app.
    docker compose exec backend pytest -xvs tests/test_phase3_phase4.py
"""
import io
import sys
from pathlib import Path
from unittest.mock import patch

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from PIL import Image
from sqlalchemy import delete, select

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dotenv import load_dotenv
load_dotenv(Path(__file__).resolve().parent.parent / ".env")

from app import tenant_context  # noqa: E402
from app.database import SessionLocal, engine  # noqa: E402


@pytest_asyncio.fixture(autouse=True)
async def _dispose_engine_between_tests():
    yield
    await engine.dispose()
from app.deps import bypass_tenant_scope  # noqa: E402
from app.models.audit_log import AuditLog  # noqa: E402
from app.models.tenant import Tenant  # noqa: E402
from app.models.tenant_settings import TenantSettings  # noqa: E402
from app.models.user import User  # noqa: E402
from app.security import hash_pin, issue_access_token, issue_signup_token  # noqa: E402
from app.services.crypto import decrypt_secret  # noqa: E402
from main import app  # noqa: E402

HANDLE_A = "p34a"
HANDLE_B = "p34b"


@pytest.fixture
def anyio_backend():
    return "asyncio"


async def _cleanup():
    tenant_context.set_current_tenant_id(None)
    async with SessionLocal() as s:
        async with bypass_tenant_scope():
            tids = (await s.execute(
                select(Tenant.id).where(Tenant.handle.in_([HANDLE_A, HANDLE_B, "newshop"]))
            )).scalars().all()
            if tids:
                await s.execute(delete(AuditLog).where(AuditLog.tenant_id.in_(tids)))
                await s.execute(delete(User).where(User.tenant_id.in_(tids)))
                await s.execute(delete(TenantSettings).where(TenantSettings.tenant_id.in_(tids)))
                await s.execute(delete(Tenant).where(Tenant.id.in_(tids)))
            await s.commit()


async def _seed():
    """Create tenant A with owner + 1 cashier, tenant B with owner."""
    await _cleanup()
    async with SessionLocal() as s:
        async with bypass_tenant_scope():
            tA = Tenant(handle=HANDLE_A, name="A Shop", owner_email="a@p34.test")
            tB = Tenant(handle=HANDLE_B, name="B Shop", owner_email="b@p34.test")
            s.add_all([tA, tB]); await s.flush()
            ownerA = User(tenant_id=tA.id, username=HANDLE_A, email="a@p34.test",
                          role="owner", is_active=True, google_sub="sub-a")
            ownerB = User(tenant_id=tB.id, username=HANDLE_B, email="b@p34.test",
                          role="owner", is_active=True, google_sub="sub-b")
            cashA = User(tenant_id=tA.id, username=f"staff1.{HANDLE_A}",
                         role="cashier", is_active=True, pin_hash=hash_pin("482913"))
            s.add_all([ownerA, ownerB, cashA]); await s.commit()
            return {
                "tA_id": tA.id, "tB_id": tB.id,
                "ownerA_id": ownerA.id, "ownerB_id": ownerB.id, "cashA_id": cashA.id,
            }


def _client() -> AsyncClient:
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


# ========== PHASE 3: AUTH ==========

@pytest.mark.asyncio
async def test_phase3_google_login_invalid_token():
    await _seed()
    try:
        with patch("app.routers.auth.verify_google_id_token", side_effect=ValueError("bad")):
            async with _client() as c:
                r = await c.post("/auth/google", json={"id_token": "xxx"})
        assert r.status_code == 401, r.text
    finally:
        await _cleanup()


@pytest.mark.asyncio
async def test_phase3_google_login_existing_owner():
    ids = await _seed()
    try:
        with patch("app.routers.auth.verify_google_id_token",
                   return_value={"email": "a@p34.test", "sub": "sub-a"}):
            async with _client() as c:
                r = await c.post("/auth/google", json={"id_token": "ok"})
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["role"] == "owner"
        assert body["tenant_id"] == ids["tA_id"]
        assert body["access_token"] and body["refresh_token"]
    finally:
        await _cleanup()


@pytest.mark.asyncio
async def test_phase3_google_login_needs_onboarding():
    await _seed()
    try:
        with patch("app.routers.auth.verify_google_id_token",
                   return_value={"email": "brand-new@p34.test", "sub": "sub-new"}):
            async with _client() as c:
                r = await c.post("/auth/google", json={"id_token": "ok"})
        assert r.status_code == 200
        body = r.json()
        assert body["needs_onboarding"] is True
        assert body["signup_token"]
    finally:
        await _cleanup()


@pytest.mark.asyncio
async def test_phase3_google_signup_creates_tenant():
    await _seed()
    try:
        signup = issue_signup_token(email="new@p34.test", sub="sub-new")
        async with _client() as c:
            r = await c.post("/auth/google/signup", json={
                "signup_token": signup, "shop_name": "New Shop", "handle": "newshop"
            })
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["role"] == "owner"
        async with SessionLocal() as s:
            async with bypass_tenant_scope():
                t = (await s.execute(select(Tenant).where(Tenant.handle == "newshop"))).scalars().first()
                assert t and t.owner_email == "new@p34.test"
    finally:
        await _cleanup()


@pytest.mark.asyncio
async def test_phase3_google_signup_duplicate_handle():
    await _seed()
    try:
        signup = issue_signup_token(email="other@p34.test", sub="sub-o")
        async with _client() as c:
            r = await c.post("/auth/google/signup", json={
                "signup_token": signup, "shop_name": "XYZ", "handle": HANDLE_A
            })
        assert r.status_code == 409
    finally:
        await _cleanup()


@pytest.mark.asyncio
async def test_phase3_staff_login_success():
    ids = await _seed()
    try:
        async with _client() as c:
            r = await c.post("/auth/staff/login", json={
                "tenant_handle": HANDLE_A, "username": f"staff1.{HANDLE_A}", "pin": "482913"
            })
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["role"] == "cashier" and body["tenant_id"] == ids["tA_id"]
    finally:
        await _cleanup()


@pytest.mark.asyncio
async def test_phase3_staff_login_bad_pin():
    await _seed()
    try:
        async with _client() as c:
            r = await c.post("/auth/staff/login", json={
                "tenant_handle": HANDLE_A, "username": f"staff1.{HANDLE_A}", "pin": "000001"
            })
        assert r.status_code == 401
    finally:
        await _cleanup()


@pytest.mark.asyncio
async def test_phase3_staff_login_bad_tenant():
    await _seed()
    try:
        async with _client() as c:
            r = await c.post("/auth/staff/login", json={
                "tenant_handle": "nope", "username": "xx", "pin": "482913"
            })
        assert r.status_code == 401
    finally:
        await _cleanup()


@pytest.mark.asyncio
async def test_phase3_create_cashier_auto_username():
    ids = await _seed()
    try:
        owner_tok = issue_access_token(tenant_id=ids["tA_id"], user_id=ids["ownerA_id"], role="owner")
        async with _client() as c:
            r = await c.post("/users", json={"pin": "739184"},
                             headers={"Authorization": f"Bearer {owner_tok}"})
        assert r.status_code == 200, r.text
        body = r.json()
        # A already has staff1, so new should be staff2.<handle>
        assert body["username"] == f"staff2.{HANDLE_A}"
        assert body["role"] == "cashier"
    finally:
        await _cleanup()


@pytest.mark.asyncio
async def test_phase3_create_cashier_trivial_pin_rejected():
    ids = await _seed()
    try:
        owner_tok = issue_access_token(tenant_id=ids["tA_id"], user_id=ids["ownerA_id"], role="owner")
        async with _client() as c:
            r = await c.post("/users", json={"pin": "123456"},
                             headers={"Authorization": f"Bearer {owner_tok}"})
        assert r.status_code == 400
    finally:
        await _cleanup()


@pytest.mark.asyncio
async def test_phase3_cashier_cannot_create_users():
    ids = await _seed()
    try:
        cash_tok = issue_access_token(tenant_id=ids["tA_id"], user_id=ids["cashA_id"], role="cashier")
        async with _client() as c:
            r = await c.post("/users", json={"pin": "739184"},
                             headers={"Authorization": f"Bearer {cash_tok}"})
        assert r.status_code == 403
    finally:
        await _cleanup()


@pytest.mark.asyncio
async def test_phase3_reset_pin_audit():
    ids = await _seed()
    try:
        owner_tok = issue_access_token(tenant_id=ids["tA_id"], user_id=ids["ownerA_id"], role="owner")
        async with _client() as c:
            r = await c.patch(f"/users/{ids['cashA_id']}", json={"pin": "739184"},
                              headers={"Authorization": f"Bearer {owner_tok}"})
        assert r.status_code == 200, r.text
        # Now login with new PIN
        async with _client() as c:
            r2 = await c.post("/auth/staff/login", json={
                "tenant_handle": HANDLE_A, "username": f"staff1.{HANDLE_A}", "pin": "739184"
            })
        assert r2.status_code == 200
        # Audit row present
        async with SessionLocal() as s:
            async with bypass_tenant_scope():
                rows = (await s.execute(
                    select(AuditLog).where(
                        AuditLog.tenant_id == ids["tA_id"],
                        AuditLog.action == "user.reset_pin",
                    )
                )).scalars().all()
                assert len(rows) >= 1
    finally:
        await _cleanup()


@pytest.mark.asyncio
async def test_phase3_cross_tenant_user_access_blocked():
    ids = await _seed()
    try:
        # Owner of tenant B tries to patch cashier of tenant A → should 404 (scoped away).
        tokB = issue_access_token(tenant_id=ids["tB_id"], user_id=ids["ownerB_id"], role="owner")
        async with _client() as c:
            r = await c.patch(f"/users/{ids['cashA_id']}", json={"is_active": False},
                              headers={"Authorization": f"Bearer {tokB}"})
        assert r.status_code == 404
    finally:
        await _cleanup()


@pytest.mark.asyncio
async def test_phase3_refresh_token_flow():
    ids = await _seed()
    try:
        with patch("app.routers.auth.verify_google_id_token",
                   return_value={"email": "a@p34.test", "sub": "sub-a"}):
            async with _client() as c:
                r = await c.post("/auth/google", json={"id_token": "ok"})
        refresh = r.json()["refresh_token"]
        async with _client() as c:
            r2 = await c.post("/auth/refresh", json={"refresh_token": refresh})
        assert r2.status_code == 200
        assert r2.json()["access_token"]
    finally:
        await _cleanup()


@pytest.mark.asyncio
async def test_phase3_missing_bearer_401():
    async with _client() as c:
        r = await c.get("/users")
    assert r.status_code == 401


@pytest.mark.asyncio
async def test_phase3_logout_audits():
    ids = await _seed()
    try:
        tok = issue_access_token(tenant_id=ids["tA_id"], user_id=ids["ownerA_id"], role="owner")
        async with _client() as c:
            r = await c.post("/auth/logout", headers={"Authorization": f"Bearer {tok}"})
        assert r.status_code == 200
        async with SessionLocal() as s:
            async with bypass_tenant_scope():
                n = (await s.execute(
                    select(AuditLog).where(
                        AuditLog.tenant_id == ids["tA_id"], AuditLog.action == "auth.logout"
                    )
                )).scalars().all()
                assert len(n) >= 1
    finally:
        await _cleanup()


# ========== PHASE 4: SETTINGS ==========

@pytest.mark.asyncio
async def test_phase4_get_settings_returns_defaults():
    ids = await _seed()
    try:
        tok = issue_access_token(tenant_id=ids["tA_id"], user_id=ids["ownerA_id"], role="owner")
        async with _client() as c:
            r = await c.get("/settings", headers={"Authorization": f"Bearer {tok}"})
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["tenant_id"] == ids["tA_id"]
        assert body["billplz_mode"] == "sandbox"
        assert body["billplz_configured"] is False
        assert body["logo_path"] is None
        assert "yolo_conf_threshold" in body
    finally:
        await _cleanup()


@pytest.mark.asyncio
async def test_phase4_cashier_blocked_from_settings():
    ids = await _seed()
    try:
        cash = issue_access_token(tenant_id=ids["tA_id"], user_id=ids["cashA_id"], role="cashier")
        async with _client() as c:
            r = await c.get("/settings", headers={"Authorization": f"Bearer {cash}"})
        assert r.status_code == 403
    finally:
        await _cleanup()


@pytest.mark.asyncio
async def test_phase4_patch_billplz_roundtrip_encrypted():
    ids = await _seed()
    try:
        tok = issue_access_token(tenant_id=ids["tA_id"], user_id=ids["ownerA_id"], role="owner")
        async with _client() as c:
            r = await c.patch("/settings", json={
                "billplz_api_key": "secret-api-key-xyz",
                "billplz_collection_id": "coll-123",
                "billplz_xsign_key": "xsign-secret",
                "billplz_mode": "sandbox",
            }, headers={"Authorization": f"Bearer {tok}"})
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["billplz_configured"] is True
        assert body["billplz_collection_id"] == "coll-123"
        # API key never returned
        assert "billplz_api_key" not in body
        # Decryption roundtrip via DB
        async with SessionLocal() as s:
            async with bypass_tenant_scope():
                row = (await s.execute(
                    select(TenantSettings).where(TenantSettings.tenant_id == ids["tA_id"])
                )).scalars().first()
                assert decrypt_secret(row.billplz_api_key) == "secret-api-key-xyz"
                assert decrypt_secret(row.billplz_xsign_key) == "xsign-secret"
                # Ciphertext differs from plaintext in DB
                assert row.billplz_api_key != "secret-api-key-xyz"
    finally:
        await _cleanup()


@pytest.mark.asyncio
async def test_phase4_patch_branding_fields():
    ids = await _seed()
    try:
        tok = issue_access_token(tenant_id=ids["tA_id"], user_id=ids["ownerA_id"], role="owner")
        async with _client() as c:
            r = await c.patch("/settings", json={
                "receipt_footer": "Thank you!",
                "shop_contact_email": "shop@example.com",
                "shop_contact_phone": "+60123456789",
            }, headers={"Authorization": f"Bearer {tok}"})
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["receipt_footer"] == "Thank you!"
        assert body["shop_contact_email"] == "shop@example.com"
    finally:
        await _cleanup()


@pytest.mark.asyncio
async def test_phase4_logo_upload_saves_and_resizes():
    ids = await _seed()
    try:
        tok = issue_access_token(tenant_id=ids["tA_id"], user_id=ids["ownerA_id"], role="owner")
        # Build a PNG 2000x2000 to test thumbnail clamp
        buf = io.BytesIO()
        Image.new("RGBA", (2000, 2000), (255, 0, 0, 255)).save(buf, format="PNG")
        buf.seek(0)
        async with _client() as c:
            r = await c.post("/settings/logo",
                             files={"file": ("logo.png", buf.getvalue(), "image/png")},
                             headers={"Authorization": f"Bearer {tok}"})
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["logo_path"] == f"/uploads/{ids['tA_id']}/logo.png"
        from app.config import UPLOADS_DIR
        saved = UPLOADS_DIR / str(ids["tA_id"]) / "logo.png"
        assert saved.exists()
        with Image.open(saved) as im:
            w, h = im.size
            assert max(w, h) <= 1024
    finally:
        await _cleanup()


@pytest.mark.asyncio
async def test_phase4_logo_upload_rejects_bad_mime():
    ids = await _seed()
    try:
        tok = issue_access_token(tenant_id=ids["tA_id"], user_id=ids["ownerA_id"], role="owner")
        async with _client() as c:
            r = await c.post("/settings/logo",
                             files={"file": ("logo.txt", b"not an image", "text/plain")},
                             headers={"Authorization": f"Bearer {tok}"})
        assert r.status_code == 400
    finally:
        await _cleanup()


@pytest.mark.asyncio
async def test_phase4_settings_tenant_isolated():
    ids = await _seed()
    try:
        tokA = issue_access_token(tenant_id=ids["tA_id"], user_id=ids["ownerA_id"], role="owner")
        tokB = issue_access_token(tenant_id=ids["tB_id"], user_id=ids["ownerB_id"], role="owner")
        async with _client() as c:
            await c.patch("/settings", json={"receipt_footer": "A-footer"},
                          headers={"Authorization": f"Bearer {tokA}"})
            rB = await c.get("/settings", headers={"Authorization": f"Bearer {tokB}"})
        assert rB.status_code == 200
        body = rB.json()
        assert body["tenant_id"] == ids["tB_id"]
        assert body["receipt_footer"] != "A-footer"
    finally:
        await _cleanup()
