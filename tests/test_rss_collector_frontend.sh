#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
INGEST="$ROOT/app/frontend/src/pages/Ingest.tsx"
LIBRARY="$ROOT/app/frontend/src/pages/CinematicLibrary.tsx"
SOURCES_OVERLAY="$ROOT/app/frontend/src/pages/GlobalDockSourcesOverlay.tsx"

for path in \
  "$ROOT/app/frontend/src/api.ts" \
  "$INGEST" \
  "$LIBRARY" \
  "$SOURCES_OVERLAY"; do
  if [[ ! -f "$path" ]]; then
    echo "missing collector production file: $path" >&2
    exit 1
  fi
done

if [[ -e "$ROOT/app/frontend/src/pages/Events.tsx" || -e "$ROOT/app/frontend/src/pages/Sources.tsx" ]]; then
  echo "collector test must use the unified production library, not retired pages" >&2
  exit 1
fi

for needle in \
  "apiFetch('/api/collect'" \
  "apiFetch(\`/api/events?\${params}\`" \
  "loadSources()" \
  "立即采集"; do
  if ! grep -F -q "$needle" "$INGEST" "$LIBRARY" "$SOURCES_OVERLAY"; then
    echo "missing collector frontend behavior: $needle" >&2
    exit 1
  fi
done

for mode in "mode === 'events'" "mode === 'sources'"; do
  if ! grep -F -q "$mode" "$LIBRARY"; then
    echo "unified library missing mode: $mode" >&2
    exit 1
  fi
done

echo "rss collector frontend ok"
