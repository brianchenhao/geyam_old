#!/usr/bin/env bash
# Pull the latest geyam-backend image from GHCR and restart the backend
# service on the VPS. Run from the laptop:
#
#   ./ops/deploy.sh
#
# Idempotent: re-running with the same upstream image is a no-op (compose
# detects "no change" and skips recreation). Safe to spam.
#
# Prereqs:
#   - SSH access as deploy@geyam-prod (key auth)
#   - VPS has run `docker login ghcr.io` once (or the package is public)
#   - /opt/geyam/ops/docker-compose.yml is in place + .env.production exists
#
# Plan: Stage 3 Phase 4 folder tree "ops/deploy.sh".

set -euo pipefail

VPS_HOST=${VPS_HOST:-deploy@168.144.46.142}
COMPOSE="docker compose -p geyam -f /opt/geyam/ops/docker-compose.yml --env-file /opt/geyam/.env.production"

echo "==> Pulling latest backend image on $VPS_HOST"
ssh "$VPS_HOST" "$COMPOSE pull backend"

echo "==> Recreating backend container"
ssh "$VPS_HOST" "$COMPOSE up -d backend"

echo "==> Waiting for healthcheck..."
for _ in $(seq 1 20); do
    status=$(ssh "$VPS_HOST" "docker inspect --format '{{.State.Health.Status}}' geyam-backend 2>/dev/null || echo missing")
    if [[ "$status" == "healthy" ]]; then
        echo "    backend is healthy."
        break
    fi
    echo "    status=$status (waiting)"
    sleep 3
done
if [[ "$status" != "healthy" ]]; then
    echo "FATAL: backend did not reach healthy in 60s. Recent logs:" >&2
    ssh "$VPS_HOST" "$COMPOSE logs --tail 50 backend" >&2
    exit 1
fi

echo "==> Recent backend logs:"
ssh "$VPS_HOST" "$COMPOSE logs --tail 20 backend"
