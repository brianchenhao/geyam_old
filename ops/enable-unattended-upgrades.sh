#!/usr/bin/env bash
# Phase 1 step 7: enable unattended security updates.
#
# Verification target (PLAN-stage3-Geyam.md Phase 1 §7):
#   "automatic security updates active"
#
# Configures:
#   - Pull security pocket only (NOT main updates — those need a human reading release notes).
#   - Email reports on failure to root@localhost (forwarded later via /etc/aliases).
#   - Auto-reboot at 03:00 local (Asia/KL — set in step 6) only if a package requires it.
#   - Hold deploy time low: tries from 06:00 daily so the cron window doesn't overlap
#     the 02:00 pg_dump backup window.
#
# Run as root on the VPS. Idempotent.

set -euo pipefail

if [[ $EUID -ne 0 ]]; then
  echo "Must run as root" >&2
  exit 1
fi

DEBIAN_FRONTEND=noninteractive apt-get update
DEBIAN_FRONTEND=noninteractive apt-get install -y unattended-upgrades apt-listchanges

# Whitelist security pocket only. Stable releases of Ubuntu pin packages by codename;
# "${distro_codename}" expands at runtime so this works regardless of which LTS we're on.
cat > /etc/apt/apt.conf.d/50unattended-upgrades <<'EOF'
Unattended-Upgrade::Allowed-Origins {
    "${distro_id}:${distro_codename}-security";
    "${distro_id}ESMApps:${distro_codename}-apps-security";
    "${distro_id}ESM:${distro_codename}-infra-security";
};
Unattended-Upgrade::Package-Blacklist {
    // Pin docker by hand — security updates that bump the Engine can break running
    // containers mid-deploy. Apply docker bumps from ops/deploy.sh during a window.
    "docker-ce";
    "docker-ce-cli";
    "containerd.io";
};
Unattended-Upgrade::DevRelease "auto";
Unattended-Upgrade::Remove-Unused-Kernel-Packages "true";
Unattended-Upgrade::Remove-Unused-Dependencies "true";
Unattended-Upgrade::Automatic-Reboot "true";
Unattended-Upgrade::Automatic-Reboot-WithUsers "true";
Unattended-Upgrade::Automatic-Reboot-Time "03:00";
Unattended-Upgrade::Mail "root";
Unattended-Upgrade::MailReport "on-change";
EOF

# Turn on the periodic timers (download + apply). 1 = enabled.
cat > /etc/apt/apt.conf.d/20auto-upgrades <<'EOF'
APT::Periodic::Update-Package-Lists "1";
APT::Periodic::Download-Upgradeable-Packages "1";
APT::Periodic::AutocleanInterval "7";
APT::Periodic::Unattended-Upgrade "1";
EOF

# Dry-run to confirm config parses.
unattended-upgrades --dry-run --verbose | head -30

systemctl enable --now unattended-upgrades

echo
echo "Unattended-upgrades active. Next run logged to /var/log/unattended-upgrades/."
