#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"

for path in \
  "$ROOT/app/frontend/package.json" \
  "$ROOT/app/frontend/src/App.tsx" \
  "$ROOT/src/zhiji_backend/main.py" \
  "$ROOT/scripts/check.sh"; do
  if [[ ! -f "$path" ]]; then
    echo "missing: $path" >&2
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

for text in "仪表盘" "内容采集" "头脑风暴" "专题系列" "待办事务" "系统说明"; do
  if ! grep -q "$text" "$ROOT/app/frontend/src"/*.tsx "$ROOT/app/frontend/src/components"/*.tsx 2>/dev/null; then
    echo "frontend Chinese text missing: $text" >&2
    exit 1
  fi
done

echo "frontend skeleton ok"