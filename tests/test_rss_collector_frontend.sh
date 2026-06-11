#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
APP="$ROOT/app/frontend/src/App.tsx"

for needle in \
  "fetch('/api/collect'" \
  "fetch('/api/events')" \
  "手动采集" \
  "最新事件" \
  "events.map"; do
  if ! grep -q "$needle" "$APP"; then
    echo "missing collector frontend behavior: $needle" >&2
    exit 1
  fi
done

echo "rss collector frontend ok"
