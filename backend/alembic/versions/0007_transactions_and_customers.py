"""Transactions + line items + payments + receipts + customers.

Revision ID: 0007
Revises: 0006
Create Date: 2026-04-20
"""
from alembic import op

revision = "0007"
down_revision = "0006"
branch_labels = None
depends_on = None


def upgrade() -> None:
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
    CREATE TABLE transactions (
        id              SERIAL PRIMARY KEY,
        tenant_id       INTEGER NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
        tx_number       VARCHAR(30) NOT NULL,
        staff_id        INTEGER REFERENCES users(id),
        customer_id     INTEGER REFERENCES customers(id),
        total           DECIMAL(10,2) NOT NULL,
        payment_method  VARCHAR(20) NOT NULL DEFAULT 'qr',
        payment_ref     VARCHAR(100),
        status          VARCHAR(20) NOT NULL CHECK (status IN ('pending','paid','voided')),
        created_at      TIMESTAMP DEFAULT NOW(),
        paid_at         TIMESTAMP,
        voided_at       TIMESTAMP,
        voided_by       INTEGER REFERENCES users(id),
        UNIQUE (tenant_id, tx_number)
    );
    """)
    op.execute("CREATE INDEX idx_tx_tenant_date ON transactions(tenant_id, created_at DESC);")
    op.execute("CREATE INDEX idx_tx_tenant_status ON transactions(tenant_id, status);")

    op.execute("""
    CREATE TABLE transaction_items (
        id              SERIAL PRIMARY KEY,
        transaction_id  INTEGER REFERENCES transactions(id) ON DELETE CASCADE,
        menu_item_id    INTEGER REFERENCES menu_items(id),
        quantity        INTEGER DEFAULT 1,
        unit_price      DECIMAL(8,2) NOT NULL,
        confidence      REAL,
        source          VARCHAR(20) CHECK (source IN ('yolo','mediapipe','openai','manual'))
    );
    """)

    op.execute("""
    CREATE TABLE payments (
        id              SERIAL PRIMARY KEY,
        tenant_id       INTEGER NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
        transaction_id  INTEGER REFERENCES transactions(id) ON DELETE CASCADE,
        provider        VARCHAR(20) NOT NULL DEFAULT 'billplz',
        bill_id         VARCHAR(100),
        bill_url        TEXT,
        amount          DECIMAL(10,2),
        state           VARCHAR(20),
        paid_at         TIMESTAMP,
        raw_payload     JSONB,
        created_at      TIMESTAMP DEFAULT NOW()
    );
    """)
    op.execute("CREATE INDEX idx_payments_bill_id ON payments(bill_id);")

    op.execute("""
    CREATE TABLE receipts (
        id             SERIAL PRIMARY KEY,
        tenant_id      INTEGER NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
        transaction_id INTEGER UNIQUE REFERENCES transactions(id) ON DELETE CASCADE,
        pdf_path       TEXT,
        emailed_to     VARCHAR(255),
        emailed_at     TIMESTAMP,
        resend_id      VARCHAR(100),
        created_at     TIMESTAMP DEFAULT NOW()
    );
    """)

    op.execute("""
    CREATE TABLE stock_movements (
        id            SERIAL PRIMARY KEY,
        tenant_id     INTEGER NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
        menu_item_id  INTEGER REFERENCES menu_items(id),
        delta         INTEGER NOT NULL,
        reason        VARCHAR(40) NOT NULL CHECK (reason IN
                        ('sale','po_receive','adjust_damage','adjust_loss',
                         'adjust_theft','adjust_miscount','adjust_expired','adjust_other','void_restore')),
        ref_type      VARCHAR(40),
        ref_id        INTEGER,
        note          TEXT,
        created_by    INTEGER REFERENCES users(id),
        created_at    TIMESTAMP DEFAULT NOW()
    );
    """)
    op.execute("CREATE INDEX idx_stock_tenant_item ON stock_movements(tenant_id, menu_item_id);")


def downgrade() -> None:
    for t in ["stock_movements", "receipts", "payments", "transaction_items", "transactions", "customers"]:
        op.execute(f"DROP TABLE IF EXISTS {t};")
