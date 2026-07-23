#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
APP="$ROOT/app/frontend/src/App.tsx"
SHELL="$ROOT/app/frontend/src/pages/KiNavigationShell.tsx"
INGEST_SHELL="$ROOT/app/frontend/src/pages/LegacyIngestShellPreview.tsx"
LIBRARY="$ROOT/app/frontend/src/pages/CinematicLibrary.tsx"

for path in \
  "$ROOT/app/frontend/package.json" \
  "$APP" \
  "$SHELL" \
  "$INGEST_SHELL" \
  "$LIBRARY" \
  "$ROOT/src/zhiji_backend/main.py" \
  "$ROOT/scripts/check.sh"; do
  if [[ ! -f "$path" ]]; then
    echo "missing production skeleton file: $path" >&2
    exit 1
  fi
done

if grep -q "@tauri-apps/api" "$ROOT/app/frontend/package.json"; then
  echo "frontend package must not depend on Tauri API" >&2
  exit 1
fi

if ! grep -q "version=__version__" "$ROOT/src/zhiji_backend/main.py"; then
  echo "FastAPI app must use zhiji_backend.__version__" >&2
  exit 1
fi

for route in \
  'path="ingest" element={<LegacyIngestShellPreview />}' \
  'path="briefings" element={<CinematicBriefings />}' \
  'path="events" element={<CinematicLibrary />}' \
  'path="sources" element={<CinematicLibrary />}'; do
  if ! grep -F -q "$route" "$APP"; then
    echo "missing production route: $route" >&2
    exit 1
  fi
done

for retired_page in Events.tsx Sources.tsx; do
  if [[ -e "$ROOT/app/frontend/src/pages/$retired_page" ]]; then
    echo "retired page must stay removed: $retired_page" >&2
    exit 1
  fi
done

for label in "内容采集" "即时快报" "专题系列" "头脑风暴" "产业链" "工具箱" "系统中枢"; do
  if ! grep -q "$label" "$SHELL"; then
    echo "production navigation missing: $label" >&2
    exit 1
  fi
done

for contract in \
  "<KiNavigationShell" \
  "<Ingest />"; do
  if ! grep -F -q "$contract" "$INGEST_SHELL"; then
    echo "ingestion shell missing production contract: $contract" >&2
    exit 1
  fi
done

for contract in \
  "mode === 'events'" \
  "mode === 'sources'" \
  "资料与信息源索引"; do
  if ! grep -F -q "$contract" "$LIBRARY"; then
    echo "unified library missing production contract: $contract" >&2
    exit 1
  fi
done

echo "frontend skeleton ok"
