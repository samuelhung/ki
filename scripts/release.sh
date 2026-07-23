#!/usr/bin/env bash
set -euo pipefail

cat >&2 <<'EOF'
ZHIJI_RETIRED_ENTRYPOINT: scripts/release.sh is disabled.

Use the verified flow only:
  python scripts/build_release.py vX.Y.Z+N
  python scripts/publish_release.py vX.Y.Z+N ...
  python scripts/deploy_backend.py vX.Y.Z+N ...
EOF
exit 64
