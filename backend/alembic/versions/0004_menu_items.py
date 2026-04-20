"""Menu items (tenant-scoped catalog).

Revision ID: 0004
Revises: 0003
Create Date: 2026-04-20
"""
from alembic import op

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
    CREATE TABLE menu_items (
        id             SERIAL PRIMARY KEY,
        tenant_id      INTEGER NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
        name           VARCHAR(100) NOT NULL,
        label          VARCHAR(80) NOT NULL,
        price          DECIMAL(8,2) NOT NULL,
        category       VARCHAR(50),
        barcode        VARCHAR(64),
        stock_qty      INTEGER DEFAULT 0,
        reorder_point  INTEGER DEFAULT 5,
        avg_cost       DECIMAL(8,2) DEFAULT 0,
        image_path     TEXT,
        is_active      BOOLEAN DEFAULT TRUE,
        frame_count    INTEGER DEFAULT 0,
        created_at     TIMESTAMP DEFAULT NOW(),
        updated_at     TIMESTAMP DEFAULT NOW(),
        UNIQUE (tenant_id, label),
        UNIQUE (tenant_id, name)
    );
    """)
    op.execute("CREATE INDEX idx_menu_tenant_active ON menu_items(tenant_id, is_active);")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS menu_items;")
