#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

PYTHON_BIN="${PYTHON_BIN:-}"
if [[ -z "$PYTHON_BIN" ]]; then
  if command -v python >/dev/null 2>&1; then
    PYTHON_BIN="python"
  elif command -v python3.12 >/dev/null 2>&1; then
    PYTHON_BIN="python3.12"
  else
    echo "FAIL: Python 3.12 is required; set PYTHON_BIN=/path/to/python3.12" >&2
    exit 1
  fi
fi

PYTHON_VERSION="$($PYTHON_BIN - <<'PY'
import sys
print(f"{sys.version_info.major}.{sys.version_info.minor}")
PY
)"
if [[ "$PYTHON_VERSION" != "3.12" ]]; then
  echo "FAIL: Python 3.12 is required, got $PYTHON_VERSION from $PYTHON_BIN" >&2
  exit 1
fi

VERSION="${1:-}"
if [[ -z "$VERSION" ]]; then
  VERSION=$($PYTHON_BIN - <<'PY'
from pathlib import Path
ns = {}
exec(Path('src/zhiji_backend/__init__.py').read_text(), ns)
print(ns['__version__'])
PY
)
fi

echo "== 知几检查: v$VERSION =="

echo "== Python syntax =="
PYTHONPATH=src $PYTHON_BIN -m compileall -q src/zhiji_backend

echo "== Version consistency =="
PYTHONPATH=src $PYTHON_BIN - "$VERSION" <<'PY'
from pathlib import Path
import re
import sys
version = sys.argv[1]
checks = {
    'src/zhiji_backend/__init__.py': f'__version__ = "{version}"',
    'pyproject.toml': f'version = "{version}"',
    'app/frontend/src/constants.ts': f'APP_VERSION = "{version}"',
    'app/frontend/vite.config.ts': f"appVersion = '{version}'",
    'desktop/lib/main.dart': f"_desktopVersion = '{version}'",
    'app/frontend/public/about.html': f'v{version}',
}
for rel, needle in checks.items():
    text = Path(rel).read_text()
    if needle not in text:
        raise SystemExit(f'FAIL version mismatch: {rel} missing {needle!r}')
pubspec = Path('desktop/pubspec.yaml').read_text()
if not re.search(rf'^version:\s*{re.escape(version)}\+\d+\s*$', pubspec, re.M):
    raise SystemExit('FAIL version mismatch: desktop/pubspec.yaml')
main = Path('src/zhiji_backend/main.py').read_text()
if 'version=__version__' not in main:
    raise SystemExit('FAIL FastAPI app must use zhiji_backend.__version__')
dashboard = Path('src/zhiji_backend/routes/dashboard_routes.py').read_text()
if '"version": __version__' not in dashboard:
    raise SystemExit('FAIL /api/health must use zhiji_backend.__version__')
print('version consistency ok')
PY

echo "== Stale code scan =="
if [[ -d app/backend ]]; then
  echo "FAIL: legacy backend directory app/backend must not exist; archive under app/_archive/ if needed" >&2
  exit 1
fi
if grep -R "from backend\.\|import backend\.\|ROOT / \"app\"" tests scripts app/scripts 2>/dev/null; then
  echo "FAIL: stale legacy backend import/path found" >&2
  exit 1
fi
if grep -R "__TAURI_INTERNALS__\|@tauri-apps\|check_updates\|tauriInvoke\|tauriListen\|get_desktop_version" \
  app/frontend/src app/frontend/public app/frontend/package.json desktop/lib 2>/dev/null; then
  echo "FAIL: stale Tauri/update residue found" >&2
  exit 1
fi
if grep -R "patch_.*\.bsdiff\|bsdiff .*zhiji\|bspatch .*zhiji\|manifest.json.*gh release\|install_helper\.sh\|10\.8\.0\.105:9120/releases\|后端 DMG 分发\|BACKEND_DMG_URL\|RELEASES_DIR_LOCAL" scripts/build_release.py scripts/release-check.py 2>/dev/null; then
  echo "FAIL: stale patch-update implementation found in active release scripts" >&2
  exit 1
fi

echo "== Frontend build =="
(cd app/frontend && npm run build)

echo "== Frontend dist version =="
if ! grep -q "index-${VERSION}-" app/frontend/dist/index.html; then
  echo "FAIL: dist/index.html does not reference versioned assets for $VERSION" >&2
  exit 1
fi

echo "== Cinematic QA baseline =="
if [[ "${ZHIJI_RUN_CINEMATIC_QA:-}" == "1" ]]; then
  ZHIJI_QA_BASE_URL="${ZHIJI_QA_BASE_URL:-http://10.8.0.105:9120}"
  (cd app/frontend && npm run qa:cinematic-pages "$ZHIJI_QA_BASE_URL" tmp/check-cinematic-pages)
  (cd app/frontend && npm run qa:cinematic-pages:compact "$ZHIJI_QA_BASE_URL" tmp/check-cinematic-pages-compact)
  (cd app/frontend && npm run qa:cinematic-pages:perf "$ZHIJI_QA_BASE_URL" tmp/check-cinematic-pages-perf)
  (cd app/frontend && npm run qa:cinematic-pages:journey "$ZHIJI_QA_BASE_URL" tmp/check-cinematic-pages-journey)
else
  echo "skip cinematic QA: set ZHIJI_RUN_CINEMATIC_QA=1"
fi

echo "== Optional release artifact check =="
if [[ "${ZHIJI_SKIP_RELEASE_CHECK:-}" == "1" ]]; then
  echo "skip release-check: ZHIJI_SKIP_RELEASE_CHECK=1"
elif [[ -f "desktop/build/release/zhiji_${VERSION}.dmg" ]]; then
  PYTHONPATH=src $PYTHON_BIN scripts/release-check.py "$VERSION"
else
  echo "skip release-check: desktop/build/release/zhiji_${VERSION}.dmg not found"
fi

echo "== check ok =="
