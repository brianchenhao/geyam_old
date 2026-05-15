"""Seed the 'demo' tenant — stable demo fixture per plan §Demo Tenant Seed.

Usage (from repo root with venv or inside backend container):
    python scripts/seed_demo_tenant.py            # idempotent; creates if missing
    python scripts/seed_demo_tenant.py --wipe     # delete existing 'demo' first

Creates:
  - tenants row handle='demo', name='Demo Shop', owner_email='demo@geyam.com'
  - tenant_settings with sandbox Billplz creds from backend/.env
  - users: 2 cashiers (staff1.demo / staff2.demo) with PIN='876543' (bcrypt hashed)
  - 15 menu_items from data/sample_menu.csv
  - 500 transactions spread across last 60 days (paid status)
    - random cashier + random 1-3 items per tx
    - ~30% have a receipt_email populated (no persistent customer record)
    - 2 injected anomaly days (revenue z > 2)
  - stock_movements rows for each 'sale' and for the initial stocking
  - model_versions row pointing at yolov8n.pt baseline (notes='seed baseline')
"""
import argparse
import asyncio
import csv
import random
import sys
from datetime import date, datetime, timedelta
from decimal import Decimal
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dotenv import load_dotenv
load_dotenv(Path(__file__).resolve().parent.parent / ".env")

from sqlalchemy import delete, select  # noqa: E402

from app.database import SessionLocal  # noqa: E402
from app.deps import bypass_tenant_scope  # noqa: E402
from app.models.audit_log import AuditLog  # noqa: E402
from app.models.menu_item import MenuItem  # noqa: E402
from app.models.model_version import ModelVersion  # noqa: E402
from app.models.stock_movement import StockMovement  # noqa: E402
from app.models.tenant import Tenant  # noqa: E402
from app.models.tenant_settings import TenantSettings  # noqa: E402
from app.models.transaction import Transaction, TransactionItem  # noqa: E402
from app.models.user import User  # noqa: E402
from app.security import hash_pin  # noqa: E402
from app.services.crypto import encrypt_secret  # noqa: E402

import os  # noqa: E402


DEMO_HANDLE = "demo"
DEMO_EMAIL = "demo@geyam.com"
DEMO_NAME = "Demo Shop"
CASHIER_PIN = "876543"  # plan spec says 123456 but that's blocklisted by API; using a safer value
CSV_PATH = Path(__file__).resolve().parent.parent.parent / "data" / "sample_menu.csv"


# Emails rotated through transactions.receipt_email for ~30% of seeded TX — the
# plan no longer tracks a persistent customers table.
RECEIPT_EMAILS = [
    "brian@test.com", "aisha@test.com", "kumar@test.com", "mei@test.com",
    "hakim@test.com", "wei@test.com", "nur@test.com", "tan@test.com",
    "siti.c@test.com", "lee@test.com",
]


async def wipe_demo(session) -> None:
    async with bypass_tenant_scope():
        t = (await session.execute(select(Tenant).where(Tenant.handle == DEMO_HANDLE))).scalars().first()
        if t is None:
            return
        # Cascade deletes will handle most child rows; clear audit manually since
        # we don't want orphaned logs keeping references alive on re-seed.
        await session.execute(delete(AuditLog).where(AuditLog.tenant_id == t.id))
        await session.execute(delete(ModelVersion).where(ModelVersion.tenant_id == t.id))
        # Then delete the tenant (cascade wipes the rest)
        await session.delete(t)
        await session.commit()
        print(f"wiped demo tenant id={t.id}")


async def seed() -> int:
    async with SessionLocal() as session, bypass_tenant_scope():
        # Tenant
        t = (await session.execute(select(Tenant).where(Tenant.handle == DEMO_HANDLE))).scalars().first()
        if t is not None:
            print(f"demo tenant already exists (id={t.id}) — skipping. Pass --wipe to recreate.")
            return 0
        t = Tenant(handle=DEMO_HANDLE, name=DEMO_NAME, owner_email=DEMO_EMAIL)
        session.add(t); await session.flush()
        print(f"created tenant id={t.id}")

        # Settings with Billplz sandbox creds (encrypted)
        ts = TenantSettings(
            tenant_id=t.id,
            billplz_mode="sandbox",
            billplz_api_key=encrypt_secret(os.environ.get("BILLPLZ_SANDBOX_API_KEY")),
            billplz_collection_id=os.environ.get("BILLPLZ_SANDBOX_COLLECTION_ID"),
            billplz_xsign_key=encrypt_secret(os.environ.get("BILLPLZ_SANDBOX_X_SIGNATURE")),
            receipt_footer="Thank you for visiting Demo Shop — come again!",
            shop_contact_email=DEMO_EMAIL,
            shop_contact_phone="+60355551234",
            yolo_conf_threshold=0.60,
            yolo_conf_minimum=0.40,
            openai_daily_limit=50,
        )
        session.add(ts)

        # Owner user row (Google login pre-registered; direct login disabled)
        session.add(User(tenant_id=t.id, username=DEMO_HANDLE, email=DEMO_EMAIL, role="owner"))

        # Two cashiers
        cashiers = []
        for i in (1, 2):
            c = User(tenant_id=t.id, username=f"staff{i}.{DEMO_HANDLE}", role="cashier",
                     pin_hash=hash_pin(CASHIER_PIN), is_active=True)
            session.add(c); cashiers.append(c)
        await session.flush()
        print(f"users: owner + staff1.demo + staff2.demo (PIN={CASHIER_PIN})")

        # Menu items from CSV
        import re
        def _label(name: str) -> str:
            s = name.strip().lower().replace(" ", "_")
            s = re.sub(r"[^a-z0-9_-]+", "", s)
            return s[:80] or "item"

        items: list[MenuItem] = []
        with open(CSV_PATH, encoding="utf-8-sig") as f:
            reader = csv.DictReader(f)
            for row in reader:
                m = MenuItem(
                    tenant_id=t.id,
                    name=row["name"],
                    label=_label(row["name"]),
                    price=Decimal(row["price"]),
                    category=row.get("category") or None,
                    barcode=row.get("barcode") or None,
                    stock_qty=int(row.get("stock_qty") or 0),
                    reorder_point=int(row.get("reorder_point") or 5),
                    avg_cost=Decimal(row["price"]) * Decimal("0.6"),  # assume 60% cost margin
                )
                session.add(m); items.append(m)
        await session.flush()
        print(f"menu: {len(items)} items")

        # Initial stock movements for each item (one-off manual restock on day 0)
        for m in items:
            session.add(StockMovement(
                tenant_id=t.id, menu_item_id=m.id, delta=m.stock_qty or 0,
                reason="adjust_restock", ref_type="seed", note="initial stock",
            ))

        # 500 transactions across 60 days. Two injected anomaly days (heavy revenue).
        rng = random.Random(42)
        today = datetime.utcnow()
        anomaly_days = {20, 45}  # days-ago indices to spike
        tx_counter: dict[str, int] = {}

        for _ in range(500):
            days_ago = rng.randint(0, 59)
            spike = days_ago in anomaly_days
            # base date at random time that day
            base = today - timedelta(days=days_ago, hours=rng.randint(8, 20), minutes=rng.randint(0, 59))

            # tx_number per day/tenant
            day_key = base.strftime("%Y%m%d")
            tx_counter[day_key] = tx_counter.get(day_key, 0) + 1
            tx_num = f"GY{day_key}-{tx_counter[day_key]:04d}"

            staff = rng.choice(cashiers)
            n_items = rng.randint(1, 3) * (3 if spike else 1)
            picks = rng.sample(items, min(n_items, len(items)))

            total = Decimal("0")
            lines = []
            for m in picks:
                qty = rng.randint(1, 3)
                lines.append((m, qty))
                total += m.price * qty

            # ~70% cash, 30% qr
            method = "cash" if rng.random() < 0.7 else "qr"
            receipt_email = rng.choice(RECEIPT_EMAILS) if rng.random() < 0.3 else None

            tx = Transaction(
                tenant_id=t.id, tx_number=tx_num,
                staff_id=staff.id, receipt_email=receipt_email,
                total=total, payment_method=method, payment_ref=None, status="paid",
                created_at=base, paid_at=base,
            )
            session.add(tx); await session.flush()

            for m, q in lines:
                sources = ["yolo", "mediapipe", "openai", "manual"]
                weights = [0.65, 0.10, 0.10, 0.15]
                src = rng.choices(sources, weights=weights, k=1)[0]
                session.add(TransactionItem(
                    transaction_id=tx.id, menu_item_id=m.id, quantity=q,
                    unit_price=m.price, confidence=round(rng.uniform(0.55, 0.98), 2), source=src,
                ))
                session.add(StockMovement(
                    tenant_id=t.id, menu_item_id=m.id, delta=-q, reason="sale",
                    ref_type="transaction", ref_id=tx.id, created_by=staff.id, created_at=base,
                ))

            session.add(AuditLog(
                tenant_id=t.id, user_id=staff.id, action="tx.pay",
                entity="transaction", entity_id=tx.id,
                meta={"tx_number": tx_num, "method": method}, created_at=base,
            ))
        print(f"transactions: 500 rows, 2 anomaly spikes")

        # Single seed model_versions row pointing at baseline
        session.add(ModelVersion(
            tenant_id=t.id, filename="best.pt", num_classes=len(items),
            accuracy=None, is_active=True, notes="seed baseline (yolov8n)",
        ))

        await session.commit()
        print(f"seed complete for tenant id={t.id} '{DEMO_HANDLE}'")
        return 0


async def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--wipe", action="store_true", help="delete existing demo tenant first")
    args = ap.parse_args()
    async with SessionLocal() as session:
        if args.wipe:
            await wipe_demo(session)
    return await seed()


if __name__ == "__main__":
    rc = asyncio.run(main())
    sys.exit(rc)
