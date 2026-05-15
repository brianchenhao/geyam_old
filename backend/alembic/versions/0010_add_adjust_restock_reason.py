"""Add 'adjust_restock' to stock_movements.reason CHECK constraint.

PLAN flow #5 ("Owner tops up stock manually -> reason=restock") was unrepresentable
because the original inline CHECK in 0007 omitted 'adjust_restock'. Owners had to
mislabel restocks as 'adjust_other'. This migration drops the existing reason CHECK
(auto-named by Postgres when 0007 declared it inline) and recreates it as a named
constraint that includes the missing value.

Revision ID: 0010
Revises: 0009
Create Date: 2026-05-15
"""
from alembic import op


revision = "0010"
down_revision = "0009"
branch_labels = None
depends_on = None


_NEW_REASONS = (
    "'sale','po_receive','adjust_restock','adjust_damage','adjust_loss',"
    "'adjust_theft','adjust_miscount','adjust_expired','adjust_other','void_restore'"
)

_OLD_REASONS = (
    "'sale','po_receive','adjust_damage','adjust_loss',"
    "'adjust_theft','adjust_miscount','adjust_expired','adjust_other','void_restore'"
)


def upgrade() -> None:
    op.execute("""
    DO $$
    DECLARE cname text;
    BEGIN
        SELECT conname INTO cname
        FROM pg_constraint
        WHERE conrelid = 'stock_movements'::regclass
          AND contype = 'c'
          AND pg_get_constraintdef(oid) ILIKE '%reason%';
        IF cname IS NOT NULL THEN
            EXECUTE format('ALTER TABLE stock_movements DROP CONSTRAINT %I', cname);
        END IF;
    END $$;
    """)
    op.execute(
        "ALTER TABLE stock_movements "
        "ADD CONSTRAINT stock_movements_reason_check "
        f"CHECK (reason IN ({_NEW_REASONS}))"
    )


def downgrade() -> None:
    op.execute("ALTER TABLE stock_movements DROP CONSTRAINT IF EXISTS stock_movements_reason_check")
    op.execute(
        "ALTER TABLE stock_movements "
        "ADD CONSTRAINT stock_movements_reason_check "
        f"CHECK (reason IN ({_OLD_REASONS}))"
    )
