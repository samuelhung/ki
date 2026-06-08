#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
APP="$ROOT/app/frontend/src/App.tsx"

for needle in \
  "fetch('/api/dashboard/summary')" \
  "fetch('/api/sources')" \
  "BBC 世界新闻" \
  "sources.map"; do
  if ! grep -q "$needle" "$APP"; then
    echo "missing frontend behavior: $needle" >&2
    exit 1
  fi
done

echo "source registry frontend ok"
