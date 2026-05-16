"""Stage 3 Phase 2: subscriptions table + tenants.plan / tenants.status columns.

Local cache + audit trail of Stripe subscription state. Source of truth is Stripe;
this table is read by quota enforcement (plan_enforcement.py, Phase 9) and updated
by the Stripe webhook handler.

Schema adaptations vs PLAN-stage3-Geyam.md §"New Database Migrations":
- id: BIGSERIAL, not UUID — Stage 2 tenants/users use SERIAL PKs, stay consistent.
- tenant_id: INTEGER (tenants.id is SERIAL).
- stripe_customer_id: NULL-allowed (plan said NOT NULL). The Phase 2 backfill runs
  before Phase 9 wires Stripe, so existing tenants have no customer ID yet. Phase 9
  will create Stripe customers for every tenant and tighten this to NOT NULL.

Revision ID: 0011
Revises: 0010
Create Date: 2026-05-16
"""
from alembic import op


revision = "0011"
down_revision = "0010"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
    CREATE TABLE subscriptions (
        id                     BIGSERIAL PRIMARY KEY,
        tenant_id              INTEGER NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
        stripe_customer_id     TEXT,
        stripe_subscription_id TEXT UNIQUE,
        plan                   TEXT NOT NULL CHECK (plan IN ('free','pro','business')),
        status                 TEXT NOT NULL CHECK (status IN
                                ('active','past_due','suspended','canceled')),
        current_period_end     TIMESTAMPTZ,
        past_due_since         TIMESTAMPTZ,
        suspended_at           TIMESTAMPTZ,
        created_at             TIMESTAMPTZ NOT NULL DEFAULT now(),
        updated_at             TIMESTAMPTZ NOT NULL DEFAULT now()
    );
    """)
    op.execute("CREATE INDEX idx_subscriptions_tenant ON subscriptions(tenant_id);")
    op.execute("CREATE INDEX idx_subscriptions_status ON subscriptions(status);")

    op.execute("""
    ALTER TABLE tenants
        ADD COLUMN plan TEXT NOT NULL DEFAULT 'free'
            CHECK (plan IN ('free','pro','business')),
        ADD COLUMN status TEXT NOT NULL DEFAULT 'active'
            CHECK (status IN ('active','suspended'));
    """)


def downgrade() -> None:
    op.execute("ALTER TABLE tenants DROP COLUMN IF EXISTS status;")
    op.execute("ALTER TABLE tenants DROP COLUMN IF EXISTS plan;")
    op.execute("DROP INDEX IF EXISTS idx_subscriptions_status;")
    op.execute("DROP INDEX IF EXISTS idx_subscriptions_tenant;")
    op.execute("DROP TABLE IF EXISTS subscriptions;")
