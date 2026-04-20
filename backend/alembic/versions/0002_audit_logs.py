"""Audit logs (indefinite retention).

Revision ID: 0002
Revises: 0001
Create Date: 2026-04-20
"""
from alembic import op

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
    CREATE TABLE audit_logs (
        id          BIGSERIAL PRIMARY KEY,
        tenant_id   INTEGER REFERENCES tenants(id) ON DELETE CASCADE,
        user_id     INTEGER REFERENCES users(id),
        action      VARCHAR(80) NOT NULL,
        entity      VARCHAR(40),
        entity_id   INTEGER,
        meta        JSONB,
        created_at  TIMESTAMP DEFAULT NOW()
    );
    """)
    op.execute("CREATE INDEX idx_audit_tenant_date ON audit_logs(tenant_id, created_at DESC);")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS audit_logs;")
