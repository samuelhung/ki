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

run_retired_feature_scan() {
  local mode="${1:-scan}"
  PYTHONPATH=src "$PYTHON_BIN" - "$ROOT" "$mode" <<'PY'
from __future__ import annotations

import re
import sys
import tempfile
from pathlib import Path


ROOT = Path(sys.argv[1])
MODE = sys.argv[2]
SOURCE_SUFFIXES = {".js", ".mjs", ".py", ".ts", ".tsx"}
SKIPPED_PARTS = {".git", ".venv", "dist", "node_modules", "tmp"}
RETIRED_TABLES = "event_entities|entity_relations|entities|digests|topics"

RULES = (
    (
        "retired frontend route or demo import",
        re.compile(
            r"today-old|ingest-previous|/demo/|"
            r"(?:from\s+|import\s*\()\s*['\"][^'\"]*"
            r"(?:CircularGalleryDemo|DualNavigationDemo|BrandLockupDemo|BrandDepthDemo|DockPopupVisualDemo)"
            r"(?:\.(?:[cm]?[jt]sx?))?['\"]"
        ),
    ),
    (
        "retired entity or digest API/module",
        re.compile(
            r"/api/entities(?:/[A-Za-z0-9_-]+)?|/api/digest(?:/[A-Za-z0-9_-]+)?|"
            r"\b(?:entity_routes|digest_routes)\b|"
            r"(?:from|import)\s+(?:zhiji_backend\.)?(?:entity|entities|digest|digest_ai)\b"
        ),
    ),
    ("retired knowledge graph", re.compile(r"\bknowledge_graph\b")),
    (
        "retired table creation",
        re.compile(
            rf"\bCREATE\s+TABLE\s+(?:IF\s+NOT\s+EXISTS\s+)?[\"'`\[]?(?:{RETIRED_TABLES})\b",
            re.IGNORECASE,
        ),
    ),
)


def is_test_or_spec(path: Path) -> bool:
    relative = path.as_posix()
    return (
        relative.startswith("tests/")
        or relative.startswith("docs/superpowers/plans/")
        or relative.startswith("docs/superpowers/specs/")
        or ".test." in path.name
        or ".spec." in path.name
    )


def source_paths(root: Path):
    for base in (root / "app/frontend/src", root / "src/zhiji_backend"):
        if not base.exists():
            continue
        for path in base.rglob("*"):
            if not path.is_file() or path.suffix not in SOURCE_SUFFIXES:
                continue
            relative = path.relative_to(root)
            if any(part in SKIPPED_PARTS for part in relative.parts):
                continue
            if is_test_or_spec(relative):
                continue
            yield relative, path


def allowed_match(relative: Path, label: str, match: re.Match[str]) -> bool:
    path = relative.as_posix()
    if label == "retired knowledge graph":
        return path in {
            "src/zhiji_backend/config_manager.py",
            "src/zhiji_backend/migrations.py",
        }
    if label == "retired entity or digest API/module" and path == "src/zhiji_backend/main.py":
        return match.group(0) in {"/api/digest/latest", "/api/digest/generate"}
    return False


def validate_digest_tombstone(root: Path) -> list[str]:
    main_path = root / "src/zhiji_backend/main.py"
    if not main_path.exists():
        return []
    source = main_path.read_text(encoding="utf-8")
    if "/api/digest" not in source:
        return []
    paths = re.findall(r'["\'](/api/digest[^"\']*)["\']', source)
    if sorted(paths) != ["/api/digest/generate", "/api/digest/latest"]:
        return ["src/zhiji_backend/main.py: only the two retired digest tombstone paths are allowed"]
    tombstone = re.compile(
        r'@app\.get\("/api/digest/latest", include_in_schema=False\)\s*'
        r'@app\.post\("/api/digest/generate", include_in_schema=False\)\s*'
        r'async def retired_digest_endpoint\(\):\s*'
        r'"""Keep retired digest API paths from falling through to static mounts\."""\s*'
        r'return JSONResponse\(\{"detail": "Not Found"\}, status_code=404\)',
        re.MULTILINE,
    )
    if tombstone.search(source):
        return []
    return ["src/zhiji_backend/main.py: retired digest paths must remain hidden 404 tombstones"]


def validate_named_compatibility(root: Path) -> list[str]:
    expected = {
        "src/zhiji_backend/config_manager.py": 'normalized.pop("knowledge_graph", None)',
        "src/zhiji_backend/migrations.py": "WHERE module = 'knowledge_graph'",
    }
    violations = []
    for relative, expected_line in expected.items():
        path = root / relative
        if not path.exists():
            continue
        lines = [line.strip() for line in path.read_text(encoding="utf-8").splitlines() if "knowledge_graph" in line]
        if lines and lines != [expected_line]:
            violations.append(f"{relative}: knowledge_graph is allowed only in the named cleanup statement")
    return violations


def scan(root: Path) -> list[str]:
    violations = validate_digest_tombstone(root) + validate_named_compatibility(root)
    retired_files = {
        "app/frontend/src/pages/BrandDepthDemo.tsx",
        "app/frontend/src/pages/BrandLockupDemo.tsx",
        "app/frontend/src/pages/CircularGalleryDemo.tsx",
        "app/frontend/src/pages/DockPopupVisualDemo.tsx",
        "app/frontend/src/pages/DualNavigationDemo.tsx",
        "src/zhiji_backend/entity.py",
        "src/zhiji_backend/entities.py",
        "src/zhiji_backend/digest.py",
        "src/zhiji_backend/digest_ai.py",
        "src/zhiji_backend/routes/entity_routes.py",
        "src/zhiji_backend/routes/digest_routes.py",
    }
    for relative, path in source_paths(root):
        relative_name = relative.as_posix()
        if relative_name in retired_files:
            violations.append(f"{relative_name}: retired business module must not exist")
        source = path.read_text(encoding="utf-8")
        for label, pattern in RULES:
            for match in pattern.finditer(source):
                if allowed_match(relative, label, match):
                    continue
                line = source.count("\n", 0, match.start()) + 1
                violations.append(f"{relative_name}:{line}: {label}: {match.group(0)!r}")
    return violations


def write(root: Path, relative: str, source: str) -> None:
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(source, encoding="utf-8")


def self_test() -> None:
    bad_cases = {
        "app/frontend/src/App.tsx": 'const route = "/demo/dual-nav";\n',
        "src/zhiji_backend/routes/entity_routes.py": 'router.get("/api/entities")\n',
        "src/zhiji_backend/service.py": 'module = "knowledge_graph"\n',
        "src/zhiji_backend/db.py": 'CREATE TABLE IF NOT EXISTS digests (id TEXT);\n',
    }
    with tempfile.TemporaryDirectory(prefix="zhiji-retired-scan-") as temp_dir:
        root = Path(temp_dir)
        for relative, source in bad_cases.items():
            write(root, relative, source)
        violations = scan(root)
        expected = {
            "retired frontend route or demo import",
            "retired entity or digest API/module",
            "retired knowledge graph",
            "retired table creation",
        }
        missing = sorted(label for label in expected if not any(label in item for item in violations))
        if missing:
            raise SystemExit(f"FAIL retired feature scan self-test missed: {', '.join(missing)}")

    with tempfile.TemporaryDirectory(prefix="zhiji-retired-allowlist-") as temp_dir:
        root = Path(temp_dir)
        write(root, "src/zhiji_backend/config_manager.py", 'normalized.pop("knowledge_graph", None)\n')
        write(root, "src/zhiji_backend/migrations.py", "WHERE module = 'knowledge_graph'\n")
        write(root, "app/frontend/src/pages/KiNavigationShell.tsx", "import './DualNavigationDemo.css';\n")
        write(
            root,
            "src/zhiji_backend/main.py",
            '''@app.get("/api/digest/latest", include_in_schema=False)
@app.post("/api/digest/generate", include_in_schema=False)
async def retired_digest_endpoint():
    """Keep retired digest API paths from falling through to static mounts."""
    return JSONResponse({"detail": "Not Found"}, status_code=404)
''',
        )
        write(root, "app/frontend/src/App.test.mjs", 'assert.match(app, /\\/demo\\//);\n')
        if violations := scan(root):
            raise SystemExit("FAIL retired feature allowlist self-test:\n" + "\n".join(violations))

    with tempfile.TemporaryDirectory(prefix="zhiji-retired-allowlist-drift-") as temp_dir:
        root = Path(temp_dir)
        write(
            root,
            "src/zhiji_backend/main.py",
            '''@app.get("/api/digest/latest", include_in_schema=False)
@app.post("/api/digest/generate", include_in_schema=False)
async def retired_digest_endpoint():
    """Keep retired digest API paths from falling through to static mounts."""
    return JSONResponse({"detail": "Not Found"}, status_code=404)

EXTRA_ROUTE = "/api/digest/admin"
''',
        )
        write(
            root,
            "src/zhiji_backend/config_manager.py",
            'normalized.pop("knowledge_graph", None)\nACTIVE_MODULE = "knowledge_graph"\n',
        )
        violations = scan(root)
        if not any("digest" in item for item in violations):
            raise SystemExit("FAIL retired feature self-test allowed digest tombstone drift")
        if not any("knowledge graph" in item or "knowledge_graph" in item for item in violations):
            raise SystemExit("FAIL retired feature self-test allowed knowledge graph drift")

    print("retired feature scan self-test ok")


if MODE == "self-test":
    self_test()
else:
    findings = scan(ROOT)
    if findings:
        raise SystemExit("FAIL: stale retired feature found:\n" + "\n".join(findings))
    print("retired feature scan ok")
PY
}

if [[ "${1:-}" == "--self-test-retired-feature-scan" ]]; then
  run_retired_feature_scan self-test
  exit 0
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
if grep -R "from backend\.\|import backend\.\|ROOT / \"app\" / \"backend\"" tests scripts app/scripts 2>/dev/null; then
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
run_retired_feature_scan

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
