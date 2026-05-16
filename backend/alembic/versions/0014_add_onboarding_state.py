"""Stage 3 Phase 2: onboarding_state table for the 4-step signup wizard.

Phase 10 (self-serve signup) writes here as the new tenant advances through
shop info / first cashier / sample items / billing intro. Lets the UI resume
if the user drops off mid-flow.

step values: 1=shop+logo, 2=first cashier, 3=sample items, 4=billing intro, 5=done.

Adaptations vs PLAN-stage3-Geyam.md:
- tenant_id: INTEGER PK (tenants.id is SERIAL).

Revision ID: 0014
Revises: 0013
Create Date: 2026-05-16
"""
from alembic import op


revision = "0014"
down_revision = "0013"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
    CREATE TABLE onboarding_state (
        tenant_id      INTEGER PRIMARY KEY REFERENCES tenants(id) ON DELETE CASCADE,
        step           INTEGER NOT NULL DEFAULT 1 CHECK (step BETWEEN 1 AND 5),
        shop_info_done BOOLEAN NOT NULL DEFAULT false,
        cashier_done   BOOLEAN NOT NULL DEFAULT false,
        items_done     BOOLEAN NOT NULL DEFAULT false,
        billing_seen   BOOLEAN NOT NULL DEFAULT false,
        completed_at   TIMESTAMPTZ
    );
    """)


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS onboarding_state;")
