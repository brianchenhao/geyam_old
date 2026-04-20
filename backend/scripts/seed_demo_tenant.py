"""Phase 14: populate a demo tenant with menu + 14 days of sales + stock movements.

Idempotent on the `handle`. Re-running won't duplicate data.

Example:
    python scripts/seed_demo_tenant.py --handle demo-shop \
        --email brianchen.crisp@gmail.com --name "Demo Sari Sari"
"""
import argparse
import asyncio
import csv
import random
import sys
from datetime import datetime, timedelta
from decimal import Decimal
from pathlib import Path

from dotenv import load_dotenv

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
load_dotenv(Path(__file__).resolve().parent.parent / ".env")

from sqlalchemy import select  # noqa: E402
from sqlalchemy.exc import IntegrityError  # noqa: E402

from app.database import SessionLocal, current_tenant_id  # noqa: E402
from app.models import (  # noqa: E402
    Customer, MenuItem, StockMovement, Tenant, TenantSettings,
    Transaction, TransactionItem, User,
)
from app.security import hash_pin  # noqa: E402

SAMPLE_MENU = Path(__file__).resolve().parent.parent / "sample_menu.csv"


async def _seed(handle: str, email: str, name: str) -> None:
    async with SessionLocal() as s:
        tenant = await s.scalar(select(Tenant).where(Tenant.handle == handle))
        if tenant is None:
            tenant = Tenant(handle=handle, name=name, owner_email=email.lower())
            s.add(tenant)
            try:
                await s.flush()
            except IntegrityError as e:
                print(f"! failed to create tenant: {e.orig}")
                return
            s.add(TenantSettings(tenant_id=tenant.id))
            s.add(User(
                tenant_id=tenant.id, username=f"owner.{handle}",
                email=email.lower(), role="owner",
            ))
            s.add(User(
                tenant_id=tenant.id, username=f"staff1.{handle}",
                pin_hash=hash_pin("123456"), role="cashier",
            ))
            await s.commit()
            print(f"+ tenant id={tenant.id} handle={handle}")
        else:
            print(f"= tenant {handle} exists (id={tenant.id})")

        tok = current_tenant_id.set(tenant.id)
        try:
            await _seed_menu(s, tenant.id)
            await _seed_customers(s, tenant.id)
            await _seed_sales(s, tenant.id)
        finally:
            current_tenant_id.reset(tok)


async def _seed_menu(s, tenant_id: int) -> None:
    n_before = len((await s.scalars(select(MenuItem))).all())
    if n_before >= 15:
        print(f"= menu already has {n_before} items, skipping")
        return
    with SAMPLE_MENU.open(encoding="utf-8-sig") as f:
        rows = list(csv.DictReader(f))
    from app.routers.menu import _slugify, _unique_label
    for r in rows:
        exists = await s.scalar(select(MenuItem).where(MenuItem.name == r["name"]))
        if exists:
            continue
        label = await _unique_label(s, tenant_id, r["name"])
        s.add(MenuItem(
            tenant_id=tenant_id, name=r["name"], label=label,
            price=Decimal(r["price"]),
            category=r.get("category") or None,
            barcode=r.get("barcode") or None,
            stock_qty=int(r.get("stock_qty") or 50),
            reorder_point=int(r.get("reorder_point") or 10),
        ))
    await s.commit()
    print(f"+ menu seeded ({len(rows)} items)")


async def _seed_customers(s, tenant_id: int) -> None:
    have = await s.scalar(select(Customer).limit(1))
    if have:
        print("= customers already seeded, skipping")
        return
    s.add_all([
        Customer(tenant_id=tenant_id, name="Ali",
                 email="ali@example.my", phone="+60123456001"),
        Customer(tenant_id=tenant_id, name="Siti",
                 email="siti@example.my", phone="+60123456002"),
        Customer(tenant_id=tenant_id, name="Rajesh",
                 email="rajesh@example.my", phone="+60123456003"),
    ])
    await s.commit()
    print("+ 3 customers seeded")


async def _seed_sales(s, tenant_id: int) -> None:
    """Create ~4 sales per day for the last 14 days, each 1-3 items, all paid."""
    already = await s.scalar(
        select(Transaction).where(Transaction.tx_number.like("GY%"))
    )
    if already:
        print("= paid demo sales already exist, skipping")
        return

    items = (await s.scalars(
        select(MenuItem).where(MenuItem.is_active == True)  # noqa: E712
    )).all()
    if len(items) < 3:
        print("! need ≥3 menu items to seed sales, aborting sales seed")
        return

    customers = (await s.scalars(select(Customer))).all()
    staff = await s.scalar(
        select(User).where(User.role == "cashier").execution_options(skip_tenant_filter=True)
    )
    staff_id = staff.id if staff else None

    rng = random.Random(42)
    day_counter = 0
    tx_counter = 0
    for days_ago in range(14, 0, -1):
        day = datetime.utcnow() - timedelta(days=days_ago)
        for _ in range(rng.randint(3, 6)):
            tx_counter += 1
            line_count = rng.randint(1, 3)
            chosen = rng.sample(items, line_count)
            total = Decimal("0")
            tx_num = f"GY{day.strftime('%Y%m%d')}-{tx_counter:04d}"
            tx = Transaction(
                tenant_id=tenant_id, tx_number=tx_num,
                staff_id=staff_id,
                customer_id=(rng.choice(customers).id if customers and rng.random() < 0.3 else None),
                total=Decimal("0"), status="paid",
                payment_method="qr",
                created_at=day, paid_at=day + timedelta(minutes=1),
            )
            s.add(tx)
            await s.flush()
            for m in chosen:
                qty = rng.randint(1, 2)
                total += Decimal(str(m.price)) * qty
                s.add(TransactionItem(
                    transaction_id=tx.id, menu_item_id=m.id,
                    quantity=qty, unit_price=m.price,
                    source="yolo",
                ))
                s.add(StockMovement(
                    tenant_id=tenant_id, menu_item_id=m.id,
                    delta=-qty, reason="sale",
                    ref_type="transaction", ref_id=tx.id,
                    created_at=day + timedelta(minutes=1),
                ))
                # keep stock non-negative
                m.stock_qty = max(0, m.stock_qty - qty)
            tx.total = total
        day_counter += 1
        # reset tx_counter daily
        tx_counter = 0
    await s.commit()
    print(f"+ {day_counter} days of sales seeded")


async def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--handle", default="demo-shop")
    ap.add_argument("--email", default="brianchen.crisp@gmail.com")
    ap.add_argument("--name", default="GEYAM Demo Shop")
    args = ap.parse_args()
    await _seed(args.handle, args.email, args.name)


if __name__ == "__main__":
    asyncio.run(main())
