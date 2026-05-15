#!/usr/bin/env bash
# Provision the Geyam production VPS on DigitalOcean.
#
# Locked specs (PLAN-stage3-Geyam.md, "Locked Scope Summary"):
#   - Region:   SGP1 (Singapore)
#   - Image:    ubuntu-24-04-x64
#   - Size:     s-1vcpu-2gb           ($12.00/mo, Basic Regular, 2 GiB / 1 vCPU / 50 GB SSD / 2 TB transfer)
#   - Backups:  enabled at create-time ($2.40/mo, 20% of Droplet cost — cheaper than enabling later)
#   - Auth:     SSH key only
#   - Budget:   $14.40/mo total, under the $16/mo backend cap
#
# Prereqs on whoever runs this:
#   - doctl installed and authenticated (`doctl auth init`, paste a DO API token with write scope)
#   - A DO SSH key already uploaded; the fingerprint is passed via $DO_SSH_FINGERPRINT
#   - Optional: $DO_VPC_UUID to drop the Droplet into a specific VPC (defaults to region default)
#
# Idempotent: re-running with the same $DROPLET_NAME is a no-op once the Droplet exists.

set -euo pipefail

DROPLET_NAME="${DROPLET_NAME:-geyam-prod}"
REGION="sgp1"
IMAGE="ubuntu-24-04-x64"
SIZE="s-1vcpu-2gb"

: "${DO_SSH_FINGERPRINT:?Set DO_SSH_FINGERPRINT to the fingerprint of the SSH key uploaded to DigitalOcean. List with: doctl compute ssh-key list}"

if ! command -v doctl >/dev/null 2>&1; then
  cat >&2 <<'EOF'
doctl is not installed. Install it first:
  macOS:    brew install doctl
  Linux:    snap install doctl
  Windows:  scoop install doctl   (or download from github.com/digitalocean/doctl/releases)

Then: doctl auth init   # paste a DO API token with write scope.

If you'd rather click through the web UI, use these exact settings:
  - Region:   Singapore (SGP1)
  - Image:    Ubuntu 24.04 (LTS) x64
  - Plan:     Basic / Regular CPU / 2 GB / 1 vCPU / 50 GB / 2 TB ($12/mo)
  - Backups:  ENABLED at create time (+20%, $2.40/mo — do NOT enable after the fact, it's pricier)
  - Auth:     SSH key (select your already-uploaded key)
  - Hostname: geyam-prod
EOF
  exit 1
fi

if doctl compute droplet list --format Name --no-header | grep -Fxq "$DROPLET_NAME"; then
  echo "Droplet '$DROPLET_NAME' already exists — skipping create."
else
  echo "Creating Droplet '$DROPLET_NAME' in $REGION ($SIZE, $IMAGE, weekly backups on)..."
  doctl compute droplet create "$DROPLET_NAME" \
    --region "$REGION" \
    --image "$IMAGE" \
    --size "$SIZE" \
    --enable-backups \
    --ssh-keys "$DO_SSH_FINGERPRINT" \
    ${DO_VPC_UUID:+--vpc-uuid "$DO_VPC_UUID"} \
    --tag-names geyam,stage-3,prod \
    --wait
fi

PUBLIC_IP="$(doctl compute droplet list --format Name,PublicIPv4 --no-header | awk -v n="$DROPLET_NAME" '$1==n {print $2}')"
echo
echo "Droplet ready."
echo "  Name : $DROPLET_NAME"
echo "  IP   : $PUBLIC_IP"
echo
echo "Next: ssh root@$PUBLIC_IP, then run ./ops/bootstrap-vps.sh"
