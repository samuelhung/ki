#!/usr/bin/env bash
set -euo pipefail

cat >&2 <<'EOF'
ZHIJI_RETIRED_ENTRYPOINT: scripts/generate_appcast.sh is disabled.

Candidate Appcasts are generated and published in order by:
  python scripts/build_release.py vX.Y.Z+N
  python scripts/publish_release.py vX.Y.Z+N ...
Backend deployment uses:
  python scripts/deploy_backend.py vX.Y.Z+N ...
EOF
exit 64
