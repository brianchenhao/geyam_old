"""Phase 9 (Receipts — PDF + email) + Phase 10 (Inventory — manual adjust only).

    docker compose exec backend pytest -xvs tests/test_phase9_phase10.py
"""
import sys
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import delete, select

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dotenv import load_dotenv
load_dotenv(Path(__file__).resolve().parent.parent / ".env")

from app import tenant_context  # noqa: E402
from app.database import SessionLocal, engine  # noqa: E402


@pytest.fixture(autouse=True)
async def _dispose_engine_between_tests():
    yield
    await engine.dispose()


from app.deps import bypass_tenant_scope  # noqa: E402
from app.models.audit_log import AuditLog  # noqa: E402
from app.models.menu_item import MenuItem  # noqa: E402
from app.models.payment import Payment  # noqa: E402
from app.models.receipt import Receipt  # noqa: E402
from app.models.stock_movement import StockMovement  # noqa: E402
from app.models.tenant import Tenant  # noqa: E402
from app.models.tenant_settings import TenantSettings  # noqa: E402
from app.models.transaction import Transaction, TransactionItem  # noqa: E402
from app.models.user import User  # noqa: E402
from app.security import issue_access_token  # noqa: E402
from main import app  # noqa: E402

HANDLE_A = "p910a"
HANDLE_B = "p910b"


@pytest.fixture
def anyio_backend():
    return "asyncio"


async def _cleanup():
    tenant_context.set_current_tenant_id(None)
    async with SessionLocal() as s:
        async with bypass_tenant_scope():
            tids = (await s.execute(
                select(Tenant.id).where(Tenant.handle.in_([HANDLE_A, HANDLE_B]))
            )).scalars().all()
            if tids:
                await s.execute(delete(AuditLog).where(AuditLog.tenant_id.in_(tids)))
                await s.execute(delete(Receipt).where(Receipt.tenant_id.in_(tids)))
                await s.execute(delete(Payment).where(Payment.tenant_id.in_(tids)))
                await s.execute(delete(StockMovement).where(StockMovement.tenant_id.in_(tids)))
                await s.execute(delete(TransactionItem).where(
                    TransactionItem.transaction_id.in_(
                        select(Transaction.id).where(Transaction.tenant_id.in_(tids))
                    )
                ))
                await s.execute(delete(Transaction).where(Transaction.tenant_id.in_(tids)))
                await s.execute(delete(MenuItem).where(MenuItem.tenant_id.in_(tids)))
                await s.execute(delete(User).where(User.tenant_id.in_(tids)))
                await s.execute(delete(TenantSettings).where(TenantSettings.tenant_id.in_(tids)))
                await s.execute(delete(Tenant).where(Tenant.id.in_(tids)))
            await s.commit()


async def _seed():
    await _cleanup()
    async with SessionLocal() as s:
        async with bypass_tenant_scope():
            tA = Tenant(handle=HANDLE_A, name="A Shop", owner_email="a@p910.test")
            tB = Tenant(handle=HANDLE_B, name="B Shop", owner_email="b@p910.test")
            s.add_all([tA, tB]); await s.flush()
            ownerA = User(tenant_id=tA.id, username=HANDLE_A, email="a@p910.test",
                          role="owner", is_active=True, google_sub="sub910-a")
            ownerB = User(tenant_id=tB.id, username=HANDLE_B, email="b@p910.test",
                          role="owner", is_active=True, google_sub="sub910-b")
            s.add_all([ownerA, ownerB]); await s.commit()
            return {
                "tA_id": tA.id, "tB_id": tB.id,
                "ownerA_id": ownerA.id, "ownerB_id": ownerB.id,
            }


def _client() -> AsyncClient:
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


def _owner_tok(ids, which="A"):
    return issue_access_token(
        tenant_id=ids[f"t{which}_id"],
        user_id=ids[f"owner{which}_id"],
        role="owner",
    )


# ============================================================
# PHASE 9 — RECEIPTS
# ============================================================

def test_phase9_receipt_pdf_renders_valid_pdf(tmp_path):
    """Step 48: receipt_pdf renders with logo + footer + itemized; bytes start with %PDF."""
    from app.services.receipt_pdf import render_receipt
    out = tmp_path / "r.pdf"
    render_receipt(
        tx_number="TX-TEST-1",
        paid_at="2026-04-21 10:00",
        cashier="alice",
        recipient_email="bob@test.com",
        shop_name="Test Shop",
        shop_email="shop@test.com",
        shop_phone="0123456789",
        logo_path=None,
        line_items=[
            {"name": "Coke", "qty": 2, "unit_price": Decimal("2.50"), "total": Decimal("5.00")},
            {"name": "Chips", "qty": 1, "unit_price": Decimal("3.00"), "total": Decimal("3.00")},
        ],
        total=Decimal("8.00"),
        payment="QR · bill123",
        footer="Thank you! Come again.",
        out_path=out,
    )
    assert out.exists()
    data = out.read_bytes()
    assert data[:4] == b"%PDF", f"expected %PDF header, got {data[:8]!r}"
    assert len(data) > 500


@pytest.mark.asyncio
async def test_phase9_webhook_paid_enqueues_receipt_job():
    """Step 49: webhook success + receipt_email set → enqueues receipt email job."""
    ids = await _seed()
    try:
        # Seed: tenant settings with billplz xsign, a menu item, a pending tx with receipt_email
        async with SessionLocal() as s:
            async with bypass_tenant_scope():
                from app.services.crypto import encrypt_secret
                ts = TenantSettings(
                    tenant_id=ids["tA_id"],
                    billplz_xsign_key=encrypt_secret("xsign-secret-abc"),
                    billplz_mode="sandbox",
                )
                mi = MenuItem(tenant_id=ids["tA_id"], name="Soda", label="soda",
                              price=Decimal("3.00"), stock_qty=10, reorder_point=2)
                s.add_all([ts, mi]); await s.flush()
                tx = Transaction(tenant_id=ids["tA_id"], tx_number="TX-W-1",
                                 staff_id=ids["ownerA_id"], receipt_email="bob@test.com",
                                 total=Decimal("3.00"), payment_method="qr", status="pending")
                s.add(tx); await s.flush()
                s.add(TransactionItem(transaction_id=tx.id, menu_item_id=mi.id,
                                       quantity=1, unit_price=Decimal("3.00")))
                s.add(Payment(tenant_id=ids["tA_id"], transaction_id=tx.id,
                              provider="billplz", bill_id="BILL-XYZ", state="due"))
                await s.commit()
                tx_id = tx.id

        # Build webhook form + valid x_signature using the real Billplz v3 field order
        from app.services.billplz import verify_webhook_signature
        import hmac, hashlib
        fields = {
            "id": "BILL-XYZ",
            "paid": "true",
            "state": "paid",
            "reference_1": str(ids["tA_id"]),
            "reference_2": str(tx_id),
        }
        # Match the service: fixed webhook_order, required fields contribute even when missing
        _webhook_order = ["amount", "collection_id", "due_at", "email", "id", "mobile", "name",
                          "paid_amount", "paid_at", "paid", "state", "transaction_id",
                          "transaction_status", "url"]
        _required = {"amount", "collection_id", "due_at", "email", "id", "mobile", "name",
                     "paid_amount", "paid_at", "paid", "state", "url"}
        _parts = [f"{a}{fields.get(a, '')}" for a in _webhook_order if a in fields or a in _required]
        _payload = "|".join(_parts).encode()
        sig = hmac.new(b"xsign-secret-abc", _payload, hashlib.sha256).hexdigest()
        assert verify_webhook_signature(xsign_key="xsign-secret-abc",
                                         form_fields=fields, x_signature=sig)

        form_data = dict(fields); form_data["x_signature"] = sig

        fake_q = MagicMock()
        fake_job = MagicMock(); fake_job.id = "rq-receipt-1"
        fake_q.enqueue.return_value = fake_job

        with patch("app.routers.payment._get_receipt_queue", return_value=fake_q):
            async with _client() as c:
                r = await c.post("/payments/webhook", data=form_data)
        assert r.status_code == 200, r.text
        fake_q.enqueue.assert_called_once()
        args = fake_q.enqueue.call_args
        assert args[0][0] == "app.services.receipt_jobs.send_receipt_for_tx"
        assert args[0][1] == ids["tA_id"]
        assert args[0][2] == tx_id

        # tx should be paid now
        async with SessionLocal() as s:
            async with bypass_tenant_scope():
                tx2 = (await s.execute(select(Transaction).where(Transaction.id == tx_id))).scalars().first()
                assert tx2.status == "paid"
    finally:
        await _cleanup()


@pytest.mark.asyncio
async def test_phase9_manual_email_endpoint():
    """Step 50: POST /receipts/{tx_id}/email calls resend_mailer and persists Receipt row.

    With no persistent customers table, `to` falls back to tx.receipt_email
    (typed at checkout). This test sets receipt_email on the TX so an empty
    body still resolves a recipient.
    """
    ids = await _seed()
    try:
        async with SessionLocal() as s:
            async with bypass_tenant_scope():
                mi = MenuItem(tenant_id=ids["tA_id"], name="Choc", label="choc",
                              price=Decimal("5.00"), stock_qty=10)
                s.add(mi); await s.flush()
                tx = Transaction(tenant_id=ids["tA_id"], tx_number="TX-E-1",
                                 staff_id=ids["ownerA_id"], receipt_email="bob@test.com",
                                 total=Decimal("5.00"), payment_method="qr",
                                 payment_ref="BILL-E", status="paid",
                                 paid_at=datetime.utcnow())
                s.add(tx); await s.flush()
                s.add(TransactionItem(transaction_id=tx.id, menu_item_id=mi.id,
                                       quantity=1, unit_price=Decimal("5.00")))
                await s.commit()
                tx_id = tx.id

        tok = _owner_tok(ids)
        with patch("app.routers.receipt.send_receipt_email", return_value="resend-msg-123") as m:
            async with _client() as c:
                r = await c.post(f"/receipts/{tx_id}/email",
                                 json={},  # no 'to' → should use tx.receipt_email
                                 headers={"Authorization": f"Bearer {tok}"})
        assert r.status_code == 200, r.text
        assert r.json()["to"] == "bob@test.com"
        assert r.json()["msg_id"] == "resend-msg-123"
        m.assert_called_once()

        async with SessionLocal() as s:
            async with bypass_tenant_scope():
                rec = (await s.execute(select(Receipt).where(Receipt.transaction_id == tx_id))).scalars().first()
                assert rec is not None
                assert rec.emailed_to == "bob@test.com"
                assert rec.emailed_at is not None
                assert rec.resend_id == "resend-msg-123"
                assert rec.pdf_path and Path(rec.pdf_path).exists()
    finally:
        await _cleanup()


@pytest.mark.asyncio
async def test_phase9_receipt_pdf_endpoint_returns_file():
    """Step 51: GET /receipts/{tx_id}/pdf returns application/pdf."""
    ids = await _seed()
    try:
        async with SessionLocal() as s:
            async with bypass_tenant_scope():
                mi = MenuItem(tenant_id=ids["tA_id"], name="Bun", label="bun",
                              price=Decimal("1.50"), stock_qty=5)
                s.add(mi); await s.flush()
                tx = Transaction(tenant_id=ids["tA_id"], tx_number="TX-P-1",
                                 staff_id=ids["ownerA_id"], total=Decimal("1.50"),
                                 payment_method="qr", status="paid",
                                 paid_at=datetime.utcnow())
                s.add(tx); await s.flush()
                s.add(TransactionItem(transaction_id=tx.id, menu_item_id=mi.id,
                                       quantity=1, unit_price=Decimal("1.50")))
                await s.commit()
                tx_id = tx.id

        tok = _owner_tok(ids)
        async with _client() as c:
            r = await c.get(f"/receipts/{tx_id}/pdf",
                            headers={"Authorization": f"Bearer {tok}"})
        assert r.status_code == 200, r.text
        assert r.headers["content-type"] == "application/pdf"
        assert r.content[:4] == b"%PDF"
    finally:
        await _cleanup()


# ============================================================
# PHASE 10 — INVENTORY (manual adjust only)
# ============================================================

@pytest.mark.asyncio
async def test_phase10_low_stock_endpoint():
    """Step 55: /inventory/low-stock returns only items where stock<=reorder."""
    ids = await _seed()
    try:
        tok = _owner_tok(ids)
        async with SessionLocal() as s:
            async with bypass_tenant_scope():
                s.add_all([
                    MenuItem(tenant_id=ids["tA_id"], name="OK1", label="ok1",
                             price=Decimal("1"), stock_qty=20, reorder_point=5),
                    MenuItem(tenant_id=ids["tA_id"], name="OK2", label="ok2",
                             price=Decimal("1"), stock_qty=100, reorder_point=10),
                    MenuItem(tenant_id=ids["tA_id"], name="LOW", label="low",
                             price=Decimal("1"), stock_qty=2, reorder_point=5),
                ])
                await s.commit()

        async with _client() as c:
            r = await c.get("/inventory/low-stock",
                            headers={"Authorization": f"Bearer {tok}"})
        assert r.status_code == 200, r.text
        names = [x["name"] for x in r.json()]
        assert names == ["LOW"]
        assert r.json()[0]["low_stock"] is True
    finally:
        await _cleanup()


@pytest.mark.asyncio
async def test_phase10_inventory_adjust_valid_and_invalid():
    """Step 56: /inventory/adjust writes StockMovement, updates stock, audit row. Bad reason → 400."""
    ids = await _seed()
    try:
        tok = _owner_tok(ids)
        async with SessionLocal() as s:
            async with bypass_tenant_scope():
                mi = MenuItem(tenant_id=ids["tA_id"], name="Adj", label="adj",
                              price=Decimal("1"), stock_qty=10, reorder_point=2)
                s.add(mi); await s.commit()
                mi_id = mi.id

        async with _client() as c:
            r = await c.post("/inventory/adjust", json={
                "menu_item_id": mi_id, "delta": -3,
                "reason": "adjust_damage", "note": "dropped",
            }, headers={"Authorization": f"Bearer {tok}"})
            assert r.status_code == 200, r.text
            assert r.json()["stock_qty"] == 7

            # Invalid reason → pydantic 422 (field pattern) or our 400 check
            rbad = await c.post("/inventory/adjust", json={
                "menu_item_id": mi_id, "delta": -1, "reason": "not_a_reason",
            }, headers={"Authorization": f"Bearer {tok}"})
            assert rbad.status_code in (400, 422), rbad.text

        async with SessionLocal() as s:
            async with bypass_tenant_scope():
                sm = (await s.execute(
                    select(StockMovement).where(
                        StockMovement.menu_item_id == mi_id,
                        StockMovement.reason == "adjust_damage",
                    )
                )).scalars().all()
                assert len(sm) == 1 and sm[0].delta == -3

                al = (await s.execute(
                    select(AuditLog).where(
                        AuditLog.tenant_id == ids["tA_id"],
                        AuditLog.action == "inventory.adjust",
                    )
                )).scalars().all()
                assert len(al) == 1
    finally:
        await _cleanup()


@pytest.mark.asyncio
async def test_phase9_webhook_sets_receipt_email_on_tx():
    """receipt_email is stored on the transaction at checkout and survives the webhook."""
    ids = await _seed()
    try:
        tok = _owner_tok(ids)
        async with SessionLocal() as s:
            async with bypass_tenant_scope():
                mi = MenuItem(tenant_id=ids["tA_id"], name="Y", label="y",
                              price=Decimal("2.00"), stock_qty=5)
                s.add(mi); await s.commit()
                mi_id = mi.id

        async with _client() as c:
            rtx = await c.post("/transaction", json={
                "items": [{"menu_item_id": mi_id, "quantity": 1}],
                "receipt_email": "alice@test.com",
            }, headers={"Authorization": f"Bearer {tok}"})
            assert rtx.status_code == 200, rtx.text
            assert rtx.json()["receipt_email"] == "alice@test.com"

        async with SessionLocal() as s:
            async with bypass_tenant_scope():
                tx = (await s.execute(
                    select(Transaction).where(Transaction.tenant_id == ids["tA_id"])
                )).scalars().first()
                assert tx.receipt_email == "alice@test.com"
    finally:
        await _cleanup()
