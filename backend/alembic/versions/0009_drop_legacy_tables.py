"""Drop legacy PO / supplier / customer tables; add transactions.receipt_email.

Data-preserving rewrite:
  1. ADD transactions.receipt_email VARCHAR(255)
  2. COPY customers.email → transactions.receipt_email WHERE customer_id IS NOT NULL
  3. DROP FK transactions.customer_id (column) + index
  4. DROP TABLE purchase_order_items, purchase_orders, suppliers, customers

Customers/suppliers/POs are out of scope for Stage 2. The 352 existing transactions
that have customer_id set get their attached customer's email copied into the new
receipt_email column so past receipts remain addressable.

Revision ID: 0009
Revises: 0008
Create Date: 2026-04-22
"""
from alembic import op


revision = "0009"
down_revision = "0008"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 1. Add the new column nullable (typed-at-checkout email, no FK).
    op.execute("ALTER TABLE transactions ADD COLUMN receipt_email VARCHAR(255)")

    # 2. Preserve any existing customer email into the new column.
    op.execute("""
        UPDATE transactions t
           SET receipt_email = c.email
          FROM customers c
         WHERE t.customer_id = c.id
           AND c.email IS NOT NULL
    """)

    # 3. Drop the FK column on transactions.
    op.execute("ALTER TABLE transactions DROP COLUMN customer_id")

    # 4. Drop dependent tables in FK-safe order.
    #    (purchase_order_items → purchase_orders → suppliers; customers is independent.)
    op.execute("DROP INDEX IF EXISTS idx_suppliers_tenant_active")
    op.execute("DROP INDEX IF EXISTS idx_customers_tenant_email")
    op.execute("DROP TABLE IF EXISTS purchase_order_items CASCADE")
    op.execute("DROP TABLE IF EXISTS purchase_orders CASCADE")
    op.execute("DROP TABLE IF EXISTS suppliers CASCADE")
    op.execute("DROP TABLE IF EXISTS customers CASCADE")


def downgrade() -> None:
    # Reverse order: recreate customers + suppliers + POs, re-add customer_id column.
    # NOTE: downgrade cannot recover customer data that has already been dropped;
    #       receipt_email is left as-is on transactions.
    op.execute("""
    CREATE TABLE customers (
        id           SERIAL PRIMARY KEY,
        tenant_id    INTEGER NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
        name         VARCHAR(100),
        email        VARCHAR(255),
        phone        VARCHAR(30),
        notes        TEXT,
        created_at   TIMESTAMP DEFAULT NOW()
    );
    """)
    op.execute("CREATE INDEX idx_customers_tenant_email ON customers(tenant_id, email);")

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
        status       VARCHAR(20) NOT NULL CHECK (status IN ('draft','sent','partial','received','cancelled')),
        expected_at  DATE,
        received_at  TIMESTAMP,
        created_by   INTEGER REFERENCES users(id),
        total_cost   DECIMAL(10,2) DEFAULT 0,
        created_at   TIMESTAMP DEFAULT NOW()
    );
    """)

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

    op.execute("ALTER TABLE transactions ADD COLUMN customer_id INTEGER REFERENCES customers(id)")
    op.execute("ALTER TABLE transactions DROP COLUMN receipt_email")
