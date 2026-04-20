"""Stage 2 initial schema: tenants + users

Revision ID: 0001
Revises:
Create Date: 2026-04-20
"""
from alembic import op

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
    CREATE TABLE tenants (
        id           SERIAL PRIMARY KEY,
        handle       VARCHAR(50) UNIQUE NOT NULL,
        name         VARCHAR(100) NOT NULL,
        owner_email  VARCHAR(255) UNIQUE NOT NULL,
        is_active    BOOLEAN DEFAULT TRUE,
        created_at   TIMESTAMP DEFAULT NOW()
    );
    """)

    op.execute("""
    CREATE TABLE users (
        id            SERIAL PRIMARY KEY,
        tenant_id     INTEGER NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
        username      VARCHAR(80) NOT NULL,
        email         VARCHAR(255),
        google_sub    VARCHAR(255) UNIQUE,
        pin_hash      VARCHAR(255),
        role          VARCHAR(20) NOT NULL CHECK (role IN ('owner','cashier')),
        is_active     BOOLEAN DEFAULT TRUE,
        created_at    TIMESTAMP DEFAULT NOW(),
        UNIQUE (tenant_id, username)
    );
    """)
    op.execute("CREATE INDEX idx_users_tenant ON users(tenant_id);")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS users;")
    op.execute("DROP TABLE IF EXISTS tenants;")
