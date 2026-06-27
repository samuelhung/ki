#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"

for path in \
  "$ROOT/app/frontend/src/api.ts" \
  "$ROOT/app/frontend/src/pages/Dashboard.tsx" \
  "$ROOT/app/frontend/src/pages/Sources.tsx"; do
  if [[ ! -f "$path" ]]; then
    echo "missing frontend file: $path" >&2
    exit 1
  fi
done

for needle in \
  "apiFetch('/api/dashboard/summary')" \
  "apiFetch('/api/sources')" \
  "sources.map"; do
  if ! grep -R -q "$needle" "$ROOT/app/frontend/src"; then
    echo "missing frontend behavior: $needle" >&2
    exit 1
  fi
done

echo "source registry frontend ok"
