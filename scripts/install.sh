#!/usr/bin/env bash
set -euo pipefail

cat >&2 <<'EOF'
ZHIJI_RETIRED_ENTRYPOINT: scripts/install.sh is disabled because it installs in place.

Use the verified build and publication flow:
  python scripts/build_release.py vX.Y.Z+N
  python scripts/publish_release.py vX.Y.Z+N ...
Deploy the backend through version directories and the atomic current link:
  python scripts/deploy_backend.py vX.Y.Z+N ...
EOF
exit 64
