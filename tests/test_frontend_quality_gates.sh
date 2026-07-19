#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"

WORKFLOW="$ROOT/.github/workflows/zhiji-check.yml"
VITE_CONFIG="$ROOT/app/frontend/vite.config.ts"
SYSTEM_DOC_DATA="$ROOT/app/frontend/src/systemDocData.ts"
SYSTEM_CENTER_PANELS="$ROOT/app/frontend/src/components/cinematic-system/SystemCenterPanels.tsx"
APP_TSX="$ROOT/app/frontend/src/App.tsx"
INGEST_TSX="$ROOT/app/frontend/src/pages/Ingest.tsx"
INSTALL_SH="$ROOT/scripts/install.sh"

for path in "$WORKFLOW" "$VITE_CONFIG" "$SYSTEM_DOC_DATA" "$SYSTEM_CENTER_PANELS" "$APP_TSX" "$INGEST_TSX" "$INSTALL_SH"; do
  if [[ ! -f "$path" ]]; then
    echo "missing frontend quality gate file: $path" >&2
    exit 1
  fi
done

if grep -Eq '^[[:space:]]*[0-9]+\|' "$INSTALL_SH"; then
  echo "install.sh must not contain line-number prefixes" >&2
  exit 1
fi

if grep -q "/api/ingest/upload" "$APP_TSX"; then
  echo "drag-drop upload must use /api/ingest/file" >&2
  exit 1
fi

if ! python3 - "$INGEST_TSX" <<'PY'
import re, sys
text = open(sys.argv[1], encoding='utf-8').read()
pattern = r"apiFetch\('/api/collect',\s*\{[^}]*method:\s*'POST'[^}]*headers:\s*\{\s*'Content-Type'\s*:\s*'application/json'\s*\}[^}]*body:\s*JSON\.stringify\(\{\}\)"
sys.exit(0 if re.search(pattern, text, re.S) else 1)
PY
then
  echo "manual collect must POST an explicit empty JSON body" >&2
  exit 1
fi

if grep -R "\`/event/\|\"/event/\|'/event/" "$ROOT/app/frontend/src" --include='*.tsx' >/dev/null; then
  echo "internal event links must use /events/:id" >&2
  exit 1
fi

if ! grep -q "ZHIJI_SKIP_RELEASE_CHECK=1 ./scripts/check.sh" "$WORKFLOW"; then
  echo "GitHub Actions must run the unified zhiji check" >&2
  exit 1
fi

if ! grep -q "npm ci" "$WORKFLOW" || ! grep -q "setup-node" "$WORKFLOW"; then
  echo "GitHub Actions must install frontend dependencies with Node" >&2
  exit 1
fi

if ! grep -q "manualChunks" "$VITE_CONFIG"; then
  echo "Vite config must define manualChunks for predictable vendor splitting" >&2
  exit 1
fi

if ! grep -q "chunkSizeWarningLimit: 1800" "$VITE_CONFIG"; then
  echo "Vite chunk warning limit must match the isolated graph vendor bundle" >&2
  exit 1
fi

for export_name in SYSTEM_DOC_TABS RUNTIME_ARCHITECTURE DATA_DIRECTORY_TREE CORE_MODULES TECH_STACK ARCHITECTURE_FEATURES CHANGELOG_ENTRIES RELEASE_GUARDRAILS; do
  if ! grep -q "export const $export_name" "$SYSTEM_DOC_DATA"; then
    echo "systemDocData.ts missing export: $export_name" >&2
    exit 1
  fi
done

for export_name in TECH_STACK CHANGELOG_ENTRIES RELEASE_GUARDRAILS; do
  if ! grep -q "$export_name" "$SYSTEM_CENTER_PANELS"; then
    echo "SystemCenterPanels must render structured system data: $export_name" >&2
    exit 1
  fi
done

if [[ -e "$ROOT/app/frontend/src/pages/SystemDoc.tsx" ]]; then
  echo "retired standalone SystemDoc page must stay removed" >&2
  exit 1
fi

echo "frontend quality gates ok"
