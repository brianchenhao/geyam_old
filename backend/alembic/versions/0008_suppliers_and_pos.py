"""Suppliers + purchase orders + purchase_order_items.

Revision ID: 0008
Revises: 0007
Create Date: 2026-04-20
"""
from alembic import op

revision = "0008"
down_revision = "0007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
    CREATE TABLE suppliers (
        id          SERIAL PRIMARY KEY,
        tenant_id   INTEGER NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
        name        VARCHAR(100) NOT NULL,
        contact     VARCHAR(100),
        email       VARCHAR(255),
        phone       VARCHAR(30),
        notes       TEXT,
        is_active   BOOLEAN DEFAULT TRUE,
        created_at  TIMESTAMP DEFAULT NOW()
    );
    """)
    op.execute("CREATE INDEX idx_suppliers_tenant_active ON suppliers(tenant_id, is_active);")

    op.execute("""
    CREATE TABLE purchase_orders (
        id           SERIAL PRIMARY KEY,
        tenant_id    INTEGER NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
        supplier_id  INTEGER REFERENCES suppliers(id),
        status       VARCHAR(20) NOT NULL
                     CHECK (status IN ('draft','sent','partial','received','cancelled')),
        expected_at  DATE,
        received_at  TIMESTAMP,
        created_by   INTEGER REFERENCES users(id),
        total_cost   DECIMAL(10,2) DEFAULT 0,
        created_at   TIMESTAMP DEFAULT NOW()
    );
    """)
    op.execute("CREATE INDEX idx_po_tenant_status ON purchase_orders(tenant_id, status);")

    op.execute("""
    CREATE TABLE purchase_order_items (
        id                SERIAL PRIMARY KEY,
        po_id             INTEGER REFERENCES purchase_orders(id) ON DELETE CASCADE,
        menu_item_id      INTEGER REFERENCES menu_items(id),
        quantity_ordered  INTEGER NOT NULL,
        quantity_received INTEGER DEFAULT 0,
        unit_cost         DECIMAL(8,2) NOT NULL
    );
    """)


def downgrade() -> None:
    for t in ["purchase_order_items", "purchase_orders", "suppliers"]:
        op.execute(f"DROP TABLE IF EXISTS {t};")
