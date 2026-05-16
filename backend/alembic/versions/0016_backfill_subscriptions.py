"""Stage 3 Phase 2: backfill a subscriptions row for every existing tenant.

Plan §"Build Order" Phase 2 step 7. Every Stage 2 tenant predates Stripe
integration (Phase 9), so they all start on the Free plan with no Stripe customer
or subscription IDs. Phase 9 will create real Stripe customers and update these
rows; then Phase 9 step 12 will ALTER stripe_customer_id back to NOT NULL.

Idempotent: INSERT … SELECT … WHERE NOT EXISTS so re-running on a partially
populated DB (e.g. one created via signup AFTER Phase 10 ships) is a no-op.

Revision ID: 0016
Revises: 0015
Create Date: 2026-05-16
"""
from alembic import op


revision = "0016"
down_revision = "0015"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
    INSERT INTO subscriptions (tenant_id, plan, status)
    SELECT t.id, 'free', 'active'
    FROM tenants t
    WHERE NOT EXISTS (
        SELECT 1 FROM subscriptions s WHERE s.tenant_id = t.id
    );
    """)


def downgrade() -> None:
    op.execute("""
    DELETE FROM subscriptions
    WHERE plan = 'free'
      AND status = 'active'
      AND stripe_customer_id IS NULL
      AND stripe_subscription_id IS NULL;
    """)
