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

for text in "今日知几" "万象资料" "深度研究" "静观思辨" "见微行动" "启蒙辅导" "系统总览"; do
  if ! grep -q "$text" "$ROOT/app/frontend/src"/*.tsx "$ROOT/app/frontend/src/components"/*.tsx 2>/dev/null; then
    echo "frontend Chinese text missing: $text" >&2
    exit 1
  fi
done

if [[ ! -f "$ROOT/app/frontend/src/components/ModuleHeroTabs.tsx" ]]; then
  echo "missing shared ModuleHeroTabs component" >&2
  exit 1
fi

for page in Ingest Events Sources; do
  if ! grep -q "ModuleHeroTabs" "$ROOT/app/frontend/src/pages/$page.tsx"; then
    echo "$page must use shared ModuleHeroTabs" >&2
    exit 1
  fi
done

for tab in "内容采集" "事件列表" "信息源"; do
  if ! grep -q "$tab" "$ROOT/app/frontend/src/components/ModuleHeroTabs.tsx"; then
    echo "ModuleHeroTabs missing Wanxiang data tab: $tab" >&2
    exit 1
  fi
done

echo "frontend skeleton ok"