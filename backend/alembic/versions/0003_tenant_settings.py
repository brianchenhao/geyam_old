"""Per-tenant settings: Billplz credentials (encrypted), branding, thresholds.

Revision ID: 0003
Revises: 0002
Create Date: 2026-04-20
"""
from alembic import op

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
    CREATE TABLE tenant_settings (
        tenant_id              INTEGER PRIMARY KEY REFERENCES tenants(id) ON DELETE CASCADE,
        billplz_api_key        VARCHAR(512),
        billplz_collection_id  VARCHAR(100),
        billplz_xsign_key      VARCHAR(512),
        billplz_mode           VARCHAR(10) NOT NULL DEFAULT 'sandbox'
                               CHECK (billplz_mode IN ('sandbox','production')),
        logo_path              TEXT,
        receipt_footer         TEXT DEFAULT 'Thank you! Goods sold are not refundable.',
        shop_contact_email     VARCHAR(255),
        shop_contact_phone     VARCHAR(30),
        yolo_conf_threshold    REAL NOT NULL DEFAULT 0.60,
        yolo_conf_minimum      REAL NOT NULL DEFAULT 0.40,
        openai_daily_limit     INTEGER NOT NULL DEFAULT 50,
        training_locked_at     TIMESTAMP,
        updated_at             TIMESTAMP NOT NULL DEFAULT NOW()
    );
    """)


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS tenant_settings;")
