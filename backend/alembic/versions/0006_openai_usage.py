"""Per-tenant OpenAI daily quota tracking.

Revision ID: 0006
Revises: 0005
Create Date: 2026-04-20
"""
from alembic import op

revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
    CREATE TABLE openai_usage (
        id          SERIAL PRIMARY KEY,
        tenant_id   INTEGER NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
        day         DATE NOT NULL,
        calls       INTEGER NOT NULL DEFAULT 0,
        UNIQUE (tenant_id, day)
    );
    """)


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS openai_usage;")
