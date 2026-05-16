"""Stage 3 Phase 2: admin_audit_log — non-repudiation log of admin actions.

Distinct from antsilk_events:
  Antsilk answers  "did anyone TRY to attack me?"
  admin_audit_log answers "who did what, when, on whose behalf?"

Used for SOC2/PDPA audit trails and to resolve "you cancelled my subscription
without asking" disputes. Append-only by convention (no UPDATE/DELETE from app);
retention indefinite (rows are small).

Populated by the @audited decorator in services/audit.py — added Phase 9 step 0b.

Adaptations vs PLAN-stage3-Geyam.md:
- tenant_id: INTEGER (tenants.id is SERIAL).

Revision ID: 0015
Revises: 0014
Create Date: 2026-05-16
"""
from alembic import op


revision = "0015"
down_revision = "0014"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
    CREATE TABLE admin_audit_log (
        id           BIGSERIAL PRIMARY KEY,
        ts           TIMESTAMPTZ NOT NULL DEFAULT now(),
        actor_email  TEXT NOT NULL,
        actor_ip     INET,
        tenant_id    INTEGER REFERENCES tenants(id) ON DELETE SET NULL,
        action       TEXT NOT NULL,
        before_data  JSONB,
        after_data   JSONB,
        request_id   TEXT,
        success      BOOLEAN NOT NULL DEFAULT true
    );
    """)
    op.execute("CREATE INDEX idx_admin_audit_ts ON admin_audit_log(ts DESC);")
    op.execute("CREATE INDEX idx_admin_audit_actor ON admin_audit_log(actor_email);")
    op.execute("CREATE INDEX idx_admin_audit_action ON admin_audit_log(action);")
    op.execute(
        "CREATE INDEX idx_admin_audit_tenant ON admin_audit_log(tenant_id) "
        "WHERE tenant_id IS NOT NULL;"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_admin_audit_tenant;")
    op.execute("DROP INDEX IF EXISTS idx_admin_audit_action;")
    op.execute("DROP INDEX IF EXISTS idx_admin_audit_actor;")
    op.execute("DROP INDEX IF EXISTS idx_admin_audit_ts;")
    op.execute("DROP TABLE IF EXISTS admin_audit_log;")
