"""Stage 3 Phase 2: processed_stripe_events idempotency table.

Stripe retries webhooks aggressively. Webhook receiver (Phase 9, routers/
subscriptions.py) checks this table before acting on any event_id and inserts
on success. Duplicate retries become no-ops.

Cleanup: ops/backup.sh or a separate cron deletes rows older than 90 days
monthly (not enforced at DB level — that's an ops concern).

Revision ID: 0013
Revises: 0012
Create Date: 2026-05-16
"""
from alembic import op


revision = "0013"
down_revision = "0012"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
    CREATE TABLE processed_stripe_events (
        event_id     TEXT PRIMARY KEY,
        event_type   TEXT NOT NULL,
        processed_at TIMESTAMPTZ NOT NULL DEFAULT now()
    );
    """)
    op.execute(
        "CREATE INDEX idx_processed_stripe_events_processed "
        "ON processed_stripe_events(processed_at);"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_processed_stripe_events_processed;")
    op.execute("DROP TABLE IF EXISTS processed_stripe_events;")
