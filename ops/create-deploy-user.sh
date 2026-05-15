#!/usr/bin/env bash
# Phase 1 step 3: create the 'deploy' user that owns geyam on the VPS.
#
# Verification target (PLAN-stage3-Geyam.md Phase 1 §3):
#   "deploy user can run docker"
#
# What this does:
#   - Creates user 'deploy' with a home dir and bash shell
#   - Grants passwordless sudo (deploy can apt-update, docker pull, etc. via cron/CI)
#   - Adds deploy to the docker group so it can run `docker` without sudo
#   - Copies root's authorized_keys to deploy's ~/.ssh/authorized_keys so the
#     same key that provisioned the box works for the deploy user
#
# Run as root on the VPS, immediately AFTER step 2 (or before, but before
# is safer — once SSH is hardened, you don't want to be without a working
# non-root login).
#
# Idempotent.

set -euo pipefail

if [[ $EUID -ne 0 ]]; then
  echo "Must run as root" >&2
  exit 1
fi

USER=deploy

if ! id "$USER" >/dev/null 2>&1; then
  useradd --create-home --shell /bin/bash "$USER"
  echo "Created user $USER."
else
  echo "User $USER already exists — skipping useradd."
fi

# docker group may not exist yet if step 5 hasn't run; create if missing so
# this script can be re-run in any order without surprises.
getent group docker >/dev/null || groupadd docker

usermod -aG sudo,docker "$USER"

# Passwordless sudo for deploy. Drop-in under /etc/sudoers.d/ keeps the main
# sudoers file untouched.
SUDOERS=/etc/sudoers.d/90-deploy-nopasswd
cat > "$SUDOERS" <<EOF
${USER} ALL=(ALL) NOPASSWD:ALL
EOF
chmod 440 "$SUDOERS"
visudo -cf "$SUDOERS"  # validate; aborts the script on syntax error

# Inherit root's authorized_keys so the same key works.
HOME_DIR="$(getent passwd "$USER" | cut -d: -f6)"
install -d -m 700 -o "$USER" -g "$USER" "$HOME_DIR/.ssh"
if [[ -f /root/.ssh/authorized_keys ]]; then
  install -m 600 -o "$USER" -g "$USER" /root/.ssh/authorized_keys "$HOME_DIR/.ssh/authorized_keys"
else
  echo "WARNING: /root/.ssh/authorized_keys not found." >&2
  echo "Add your public key to $HOME_DIR/.ssh/authorized_keys before running step 2 (harden-ssh.sh)." >&2
fi

echo
echo "Deploy user ready. From your laptop, verify in a SECOND terminal:"
echo "  ssh deploy@<droplet-ip> 'sudo -n true && docker --version || echo docker not installed yet'"
echo "Docker comes in step 5; passwordless sudo should already work."
