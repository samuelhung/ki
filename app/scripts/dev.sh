#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

if [[ ! -d app/frontend/node_modules ]]; then
  (cd app/frontend && npm install)
fi

(cd app/frontend && npm run build)
python -m uvicorn backend.main:app --app-dir app --host 0.0.0.0 --port 9120
