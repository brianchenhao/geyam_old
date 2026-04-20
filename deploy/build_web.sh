#!/usr/bin/env bash
# Build the Flutter web bundle for Hostinger upload.
#
# Baked-in API base points at api.geyam.com (Cloudflare Tunnel).
# For local-dev web builds, override via --dart-define or edit api_config.dart.
#
# Output: frontend/geyam_pos/build/web/  → drag into Hostinger public_html/.
set -e

cd "$(dirname "$0")/.."
cd frontend/geyam_pos

flutter pub get
flutter build web \
  --release \
  --dart-define=API_BASE_URL=https://api.geyam.com

echo "==> build ready at $(pwd)/build/web"
echo "    upload the CONTENTS of build/web/ into Hostinger public_html/"
echo "    and copy demo.mp4 next to index.html afterwards."
