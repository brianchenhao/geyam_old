#!/usr/bin/env bash
# Phase 1 wrapper: run all VPS hardening scripts in safe order.
#
# Usage:
#   1. From your laptop: ./ops/provision-droplet.sh   # creates the Droplet, prints IP
#   2. scp -r ops/ root@<droplet-ip>:/root/ops/
#   3. ssh root@<droplet-ip> 'bash /root/ops/bootstrap-vps.sh'
#
# Order matters and is NOT alphabetical:
#   1. create-deploy-user.sh         # MUST run before harden-ssh, or you lock yourself out
#   2. install-docker.sh             # before harden-ssh too, so the docker group exists
#   3. setup-firewall.sh             # opens 22/80/443 before sshd reload double-checks 22
#   4. set-timezone.sh               # before unattended-upgrades so the auto-reboot time is MY-local
#   5. enable-unattended-upgrades.sh
#   6. setup-swap.sh
#   7. harden-ssh.sh                 # LAST — locks the door once everything else is verified

set -euo pipefail

if [[ $EUID -ne 0 ]]; then
  echo "Must run as root" >&2
  exit 1
fi

HERE="$(cd "$(dirname "$0")" && pwd)"

# Confirm deploy can log in with key BEFORE we lock down sshd.
if [[ ! -s /root/.ssh/authorized_keys ]]; then
  cat >&2 <<'EOF'
/root/.ssh/authorized_keys is empty or missing. harden-ssh.sh refuses to lock
sshd to key-only auth without a working key — you'd be stranded. Provision
the Droplet with --ssh-keys (provision-droplet.sh handles this) and re-run.
EOF
  exit 1
fi

step() {
  local script="$1"
  echo
  echo "==================== $script ===================="
  bash "$HERE/$script"
}

step create-deploy-user.sh
step install-docker.sh
step setup-firewall.sh
step set-timezone.sh
step enable-unattended-upgrades.sh
step setup-swap.sh
step harden-ssh.sh

echo
echo "==================== Phase 1 complete ===================="
echo "Verify from your laptop:"
echo "  ssh deploy@<droplet-ip> 'docker run --rm hello-world && free -h && date'"
echo "  ssh root@<droplet-ip>                                  # should be refused"
echo "  nmap -Pn -p 1-1024 <droplet-ip>                        # only 22, 80, 443 open"
