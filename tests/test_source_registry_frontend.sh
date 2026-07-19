#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
LIBRARY="$ROOT/app/frontend/src/pages/CinematicLibrary.tsx"
SOURCES_OVERLAY="$ROOT/app/frontend/src/pages/GlobalDockSourcesOverlay.tsx"

for path in \
  "$ROOT/app/frontend/src/api.ts" \
  "$LIBRARY" \
  "$SOURCES_OVERLAY"; do
  if [[ ! -f "$path" ]]; then
    echo "missing source registry production file: $path" >&2
    exit 1
  fi
done

for needle in \
  "apiFetch('/api/sources')" \
  "sources.map" \
  "loadSources()" \
  "toggleSource" \
  "collectSource"; do
  if ! grep -F -q "$needle" "$LIBRARY" "$SOURCES_OVERLAY"; then
    echo "missing source registry behavior: $needle" >&2
    exit 1
  fi
done

echo "source registry frontend ok"
