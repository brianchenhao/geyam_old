"""Stage 3 Phase 2: antsilk_events table for WAF event log.

Populated by AntsilkPostgresSink (a custom antsilk.EventSink) once Phase 7 wires
the middleware. Table exists from Phase 2 so the migration order is stable —
Phase 7 only adds the code that writes rows.

Schema mirrors antsilk's events.db SQLite schema for parity. NOT subject to
tenant RLS (none in this codebase anyway — see RLS audit notes); access is
restricted at route level to ADMIN_EMAILS.

Adaptations vs PLAN-stage3-Geyam.md:
- tenant_id: INTEGER (tenants.id is SERIAL, not UUID).

Revision ID: 0012
Revises: 0011
Create Date: 2026-05-16
"""
from alembic import op


revision = "0012"
down_revision = "0011"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
    CREATE TABLE antsilk_events (
        id              BIGSERIAL PRIMARY KEY,
        timestamp       TIMESTAMPTZ NOT NULL DEFAULT now(),
        tenant_id       INTEGER REFERENCES tenants(id) ON DELETE SET NULL,
        ip_address      INET NOT NULL,
        method          TEXT NOT NULL,
        path            TEXT NOT NULL,
        rule_triggered  TEXT NOT NULL,
        severity        TEXT NOT NULL CHECK (severity IN ('low','medium','high')),
        response_code   INTEGER NOT NULL,
        user_agent      TEXT,
        event_data      JSONB NOT NULL DEFAULT '{}'::jsonb
    );
    """)
    op.execute("CREATE INDEX idx_antsilk_events_timestamp ON antsilk_events(timestamp DESC);")
    op.execute("CREATE INDEX idx_antsilk_events_ip ON antsilk_events(ip_address);")
    op.execute("CREATE INDEX idx_antsilk_events_rule ON antsilk_events(rule_triggered);")
    op.execute(
        "CREATE INDEX idx_antsilk_events_tenant ON antsilk_events(tenant_id) "
        "WHERE tenant_id IS NOT NULL;"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_antsilk_events_tenant;")
    op.execute("DROP INDEX IF EXISTS idx_antsilk_events_rule;")
    op.execute("DROP INDEX IF EXISTS idx_antsilk_events_ip;")
    op.execute("DROP INDEX IF EXISTS idx_antsilk_events_timestamp;")
    op.execute("DROP TABLE IF EXISTS antsilk_events;")
