"""Append more transactions (+stock movements +audit logs) to an existing tenant.

Non-destructive: only INSERTs. Uses existing menu_items and cashiers.
Continues each day's tx_number sequence from whatever is already in the table.

Usage (inside backend container):
    docker compose run --rm backend python scripts/append_seed_tenant.py \
        --tenant-id 3 --count 300 --days 30
"""
import argparse
import asyncio
import random
import sys
from datetime import datetime, timedelta
from decimal import Decimal
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dotenv import load_dotenv
load_dotenv(Path(__file__).resolve().parent.parent / ".env")

from sqlalchemy import func, select  # noqa: E402

from app.database import SessionLocal  # noqa: E402
from app.deps import bypass_tenant_scope  # noqa: E402
from app.models.audit_log import AuditLog  # noqa: E402
from app.models.menu_item import MenuItem  # noqa: E402
from app.models.stock_movement import StockMovement  # noqa: E402
from app.models.tenant import Tenant  # noqa: E402
from app.models.transaction import Transaction, TransactionItem  # noqa: E402
from app.models.user import User  # noqa: E402


# Rotated through transactions.receipt_email for ~30% of appended TX.
RECEIPT_EMAILS = [
    "brian@test.com", "aisha@test.com", "kumar@test.com", "mei@test.com",
    "hakim@test.com", "wei@test.com", "nur@test.com", "tan@test.com",
    "siti.c@test.com", "lee@test.com",
]


async def append_seed(tenant_id: int, count: int, days: int, seed: int) -> int:
    async with SessionLocal() as session, bypass_tenant_scope():
        tenant = (await session.execute(
            select(Tenant).where(Tenant.id == tenant_id)
        )).scalars().first()
        if tenant is None:
            print(f"tenant id={tenant_id} not found", file=sys.stderr)
            return 2
        print(f"target: #{tenant.id} {tenant.handle} ({tenant.name})")

        items = (await session.execute(
            select(MenuItem).where(MenuItem.tenant_id == tenant_id)
        )).scalars().all()
        if not items:
            print("no menu_items — nothing to sell", file=sys.stderr)
            return 2

        cashiers = (await session.execute(
            select(User).where(
                User.tenant_id == tenant_id,
                User.role == "cashier",
                User.is_active.is_(True),
            )
        )).scalars().all()
        if not cashiers:
            cashiers = (await session.execute(
                select(User).where(User.tenant_id == tenant_id, User.is_active.is_(True))
            )).scalars().all()
        if not cashiers:
            print("no active users to attribute sales to", file=sys.stderr)
            return 2

        print(f"using {len(items)} menu items, {len(cashiers)} cashiers")

        # Per-day max tx sequence already in DB (keep new ones unique).
        seq_cache: dict[str, int] = {}

        rng = random.Random(seed)
        now = datetime.utcnow()
        anomaly_days = {int(days * 0.3), int(days * 0.7)}  # 2 spike days in window

        created = 0
        for _ in range(count):
            days_ago = rng.randint(0, max(0, days - 1))
            spike = days_ago in anomaly_days
            base = now - timedelta(
                days=days_ago,
                hours=rng.randint(8, 20),
                minutes=rng.randint(0, 59),
            )
            day_key = base.strftime("%Y%m%d")

            if day_key not in seq_cache:
                # Find the highest existing sequence number for this day in this tenant.
                like_pat = f"GY{day_key}-%"
                max_seq = (await session.execute(
                    select(func.max(Transaction.tx_number)).where(
                        Transaction.tenant_id == tenant_id,
                        Transaction.tx_number.like(like_pat),
                    )
                )).scalar()
                if max_seq:
                    try:
                        seq_cache[day_key] = int(max_seq.split("-")[-1])
                    except (ValueError, AttributeError):
                        seq_cache[day_key] = 0
                else:
                    seq_cache[day_key] = 0

            seq_cache[day_key] += 1
            tx_num = f"GY{day_key}-{seq_cache[day_key]:04d}"

            staff = rng.choice(cashiers)
            n_items = rng.randint(1, 3) * (3 if spike else 1)
            picks = rng.sample(items, min(n_items, len(items)))

            total = Decimal("0")
            lines: list[tuple[MenuItem, int]] = []
            for m in picks:
                qty = rng.randint(1, 3)
                lines.append((m, qty))
                total += m.price * qty

            method = "cash" if rng.random() < 0.7 else "qr"
            receipt_email = rng.choice(RECEIPT_EMAILS) if rng.random() < 0.3 else None

            tx = Transaction(
                tenant_id=tenant_id, tx_number=tx_num,
                staff_id=staff.id, receipt_email=receipt_email,
                total=total, payment_method=method, payment_ref=None, status="paid",
                created_at=base, paid_at=base,
            )
            session.add(tx)
            await session.flush()

            for m, q in lines:
                src = rng.choices(
                    ["yolo", "mediapipe", "openai", "manual"],
                    weights=[0.65, 0.10, 0.10, 0.15], k=1,
                )[0]
                session.add(TransactionItem(
                    transaction_id=tx.id, menu_item_id=m.id, quantity=q,
                    unit_price=m.price, confidence=round(rng.uniform(0.55, 0.98), 2),
                    source=src,
                ))
                session.add(StockMovement(
                    tenant_id=tenant_id, menu_item_id=m.id, delta=-q, reason="sale",
                    ref_type="transaction", ref_id=tx.id,
                    created_by=staff.id, created_at=base,
                ))

            session.add(AuditLog(
                tenant_id=tenant_id, user_id=staff.id, action="tx.pay",
                entity="transaction", entity_id=tx.id,
                meta={"tx_number": tx_num, "method": method, "via": "append_seed"},
                created_at=base,
            ))
            created += 1

        await session.commit()
        print(f"appended {created} transactions to tenant {tenant_id} across last {days} days")
        return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--tenant-id", type=int, required=True)
    ap.add_argument("--count", type=int, default=300)
    ap.add_argument("--days", type=int, default=30)
    ap.add_argument("--seed", type=int, default=0)
    args = ap.parse_args()
    return asyncio.run(append_seed(args.tenant_id, args.count, args.days, args.seed))


if __name__ == "__main__":
    sys.exit(main())
