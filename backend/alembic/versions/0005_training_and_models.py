"""Training jobs + model versions (per-tenant YOLO).

Revision ID: 0005
Revises: 0004
Create Date: 2026-04-20
"""
from alembic import op

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
    CREATE TABLE training_jobs (
        id               SERIAL PRIMARY KEY,
        tenant_id        INTEGER NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
        menu_item_id     INTEGER REFERENCES menu_items(id) ON DELETE SET NULL,
        video_path       TEXT NOT NULL,
        status           VARCHAR(20) NOT NULL
                         CHECK (status IN ('queued','training','done','failed')),
        frames_extracted INTEGER DEFAULT 0,
        error            TEXT,
        queued_at        TIMESTAMP DEFAULT NOW(),
        started_at       TIMESTAMP,
        finished_at      TIMESTAMP
    );
    """)
    op.execute("CREATE INDEX idx_training_jobs_tenant_status ON training_jobs(tenant_id, status);")

    # Old model_versions table (Stage 1) existed before; drop to re-create with tenant_id.
    op.execute("DROP TABLE IF EXISTS model_versions;")
    op.execute("""
    CREATE TABLE model_versions (
        id           SERIAL PRIMARY KEY,
        tenant_id    INTEGER NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
        filename     VARCHAR(255) NOT NULL,
        num_classes  INTEGER NOT NULL,
        accuracy     REAL,
        is_active    BOOLEAN DEFAULT FALSE,
        trained_at   TIMESTAMP DEFAULT NOW(),
        notes        TEXT
    );
    """)
    op.execute("CREATE INDEX idx_model_versions_tenant_active ON model_versions(tenant_id, is_active);")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS training_jobs;")
    op.execute("DROP TABLE IF EXISTS model_versions;")
