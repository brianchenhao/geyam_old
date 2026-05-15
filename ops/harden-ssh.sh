#!/usr/bin/env bash
# Phase 1 step 2: lock down sshd so only key auth works, no root, no password.
#
# Verification target (PLAN-stage3-Geyam.md Phase 1 §2):
#   "only key auth works" — after running this, `ssh -o PreferredAuthentications=password root@host`
#   and `ssh root@host` must both fail.
#
# Idempotent. Writes a drop-in under /etc/ssh/sshd_config.d/ rather than editing
# the main config in place, so unattended-upgrades pushing a new sshd_config
# doesn't silently undo this hardening.
#
# Run as root on the VPS, immediately after the first login.
# DO NOT run this until you have confirmed the deploy user (step 3) can SSH in
# with their key — otherwise you lock yourself out the moment sshd restarts.

set -euo pipefail

if [[ $EUID -ne 0 ]]; then
  echo "Must run as root" >&2
  exit 1
fi

DROPIN=/etc/ssh/sshd_config.d/10-geyam-hardening.conf

cat > "$DROPIN" <<'EOF'
# Managed by ops/harden-ssh.sh — do not edit by hand.
PermitRootLogin no
PasswordAuthentication no
ChallengeResponseAuthentication no
KbdInteractiveAuthentication no
PubkeyAuthentication yes
PermitEmptyPasswords no
UsePAM yes
X11Forwarding no
AllowAgentForwarding no
AllowTcpForwarding no
ClientAliveInterval 300
ClientAliveCountMax 2
MaxAuthTries 3
LoginGraceTime 30
EOF
chmod 644 "$DROPIN"

# Validate before restarting. sshd -t exits non-zero on bad config.
sshd -t

systemctl reload ssh || systemctl reload sshd

echo "sshd hardened. Confirm from a SECOND terminal that key auth still works"
echo "before closing this session:"
echo "  ssh deploy@<droplet-ip>      # should succeed"
echo "  ssh root@<droplet-ip>        # should be refused"
