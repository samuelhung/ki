#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"

for path in \
  "$ROOT/app/frontend/src/api.ts" \
  "$ROOT/app/frontend/src/pages/Ingest.tsx" \
  "$ROOT/app/frontend/src/pages/Events.tsx"; do
  if [[ ! -f "$path" ]]; then
    echo "missing frontend file: $path" >&2
    exit 1
  fi
done

for needle in \
  "apiFetch('/api/collect'" \
  "apiFetch('/api/events" \
  "内容采集" \
  "立即采集"; do
  if ! grep -R -q "$needle" "$ROOT/app/frontend/src"; then
    echo "missing collector frontend behavior: $needle" >&2
    exit 1
  fi
done

echo "rss collector frontend ok"
