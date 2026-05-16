#!/usr/bin/env bash
# Run alembic upgrade head against the VPS postgres container.
#
# Runs on the VPS as the deploy user, from /opt/geyam:
#   ./ops/run-migrations.sh
#
# Prereqs:
#   1. ops/docker-compose.yml is `up -d db` and the geyam-db container is healthy.
#   2. /opt/geyam/backend/ exists with alembic.ini + alembic/versions/ (rsynced from
#      laptop for Phase 2; replaced by GHCR image pull at Phase 4).
#   3. /opt/geyam/.env.production exists with POSTGRES_* secrets.
#
# Idempotent: alembic skips revisions already applied. Safe to re-run.
#
# Optional first arg: alembic target (default: head). Use a specific revision
# (e.g. "0010") to stop short — Phase 2 step 2 uses this to apply only the
# Stage 2 migrations before the laptop dump is restored.

set -euo pipefail

TARGET="${1:-head}"

cd "$(dirname "$0")/.."

if [[ ! -f .env.production ]]; then
    echo "FATAL: /opt/geyam/.env.production missing — copy from ops/.env.production.example and edit." >&2
    exit 1
fi

set -a
# shellcheck disable=SC1091
source .env.production
set +a

NETWORK="geyam_default"

if ! docker network inspect "$NETWORK" >/dev/null 2>&1; then
    echo "FATAL: docker network '$NETWORK' missing — run 'docker compose -p geyam -f ops/docker-compose.yml up -d db' first." >&2
    exit 1
fi

echo "Waiting for geyam-db to be healthy..."
for _ in $(seq 1 30); do
    status="$(docker inspect --format '{{.State.Health.Status}}' geyam-db 2>/dev/null || echo missing)"
    if [[ "$status" == "healthy" ]]; then
        break
    fi
    sleep 2
done
if [[ "$status" != "healthy" ]]; then
    echo "FATAL: geyam-db did not reach healthy state (status=$status)." >&2
    exit 1
fi
echo "geyam-db healthy."

echo "Running alembic upgrade $TARGET..."
docker run --rm \
    --network "$NETWORK" \
    -v "$(pwd)/backend:/app" \
    -w /app \
    -e ALEMBIC_DATABASE_URL="postgresql+psycopg://${POSTGRES_USER}:${POSTGRES_PASSWORD}@geyam-db:5432/${POSTGRES_DB}" \
    -e TARGET="$TARGET" \
    python:3.11-slim sh -c '
        pip install --quiet --no-cache-dir alembic "psycopg[binary]==3.2.*" sqlalchemy &&
        alembic upgrade "$TARGET"
    '

echo "Current alembic head:"
docker exec geyam-db psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" \
    -c "SELECT version_num FROM alembic_version;"
