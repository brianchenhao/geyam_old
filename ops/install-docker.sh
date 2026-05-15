#!/usr/bin/env bash
# Phase 1 step 5: install Docker Engine + Compose plugin from Docker's official apt repo.
#
# Verification target (PLAN-stage3-Geyam.md Phase 1 §5):
#   "docker run hello-world works"
#
# Why Docker's repo, not Ubuntu's docker.io: the Ubuntu package lags behind on
# Compose v2 plugin support, and Stage 3 uses `docker compose` (not the legacy
# docker-compose binary). The official packages also ship security updates faster.
#
# Run as root on the VPS. Idempotent.

set -euo pipefail

if [[ $EUID -ne 0 ]]; then
  echo "Must run as root" >&2
  exit 1
fi

. /etc/os-release  # exports $ID (ubuntu) and $VERSION_CODENAME (noble for 24.04)

# Remove any old Ubuntu-packaged docker so it doesn't shadow the official one.
for pkg in docker.io docker-doc docker-compose docker-compose-v2 podman-docker containerd runc; do
  apt-get remove -y "$pkg" >/dev/null 2>&1 || true
done

install -m 0755 -d /etc/apt/keyrings

if [[ ! -f /etc/apt/keyrings/docker.asc ]]; then
  curl -fsSL "https://download.docker.com/linux/${ID}/gpg" -o /etc/apt/keyrings/docker.asc
  chmod a+r /etc/apt/keyrings/docker.asc
fi

REPO_LINE="deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] https://download.docker.com/linux/${ID} ${VERSION_CODENAME} stable"
echo "$REPO_LINE" > /etc/apt/sources.list.d/docker.list

apt-get update
DEBIAN_FRONTEND=noninteractive apt-get install -y \
  docker-ce \
  docker-ce-cli \
  containerd.io \
  docker-buildx-plugin \
  docker-compose-plugin

systemctl enable --now docker

# Re-add deploy to docker group in case step 3 ran before docker was installed
# and the group didn't exist yet. usermod -aG is idempotent.
if id deploy >/dev/null 2>&1; then
  usermod -aG docker deploy
fi

# Smoke test from root. The deploy user will need a fresh login to pick up the
# docker group; we don't sudo-su into deploy here.
docker run --rm hello-world

echo
echo "Docker installed. Verify as deploy user (re-login first):"
echo "  ssh deploy@<droplet-ip> 'docker run --rm hello-world'"
