#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"

for path in \
  "$ROOT/app/frontend/package.json" \
  "$ROOT/app/frontend/src/App.tsx" \
  "$ROOT/app/backend/main.py" \
  "$ROOT/app/scripts/dev.sh"; do
  if [[ ! -f "$path" ]]; then
    echo "missing: $path" >&2
    exit 1
  fi
done

if ! grep -q "知识情报中心" "$ROOT/app/frontend/src/App.tsx"; then
  echo "frontend title missing" >&2
  exit 1
fi

if ! grep -q "9120" "$ROOT/app/scripts/dev.sh"; then
  echo "dev script must bind port 9120" >&2
  exit 1
fi

for script in "$ROOT/app/scripts/dev.sh" "$ROOT/app/scripts/start.sh"; do
  if ! grep -q -- "--host 0.0.0.0" "$script"; then
    echo "script must listen on all interfaces for LAN access: $script" >&2
    exit 1
  fi
done

if ! grep -q "10.8.0.105:9120" "$ROOT/app/frontend/src/App.tsx"; then
  echo "frontend must document LAN access URL" >&2
  exit 1
fi

for text in "仪表盘" "信息源" "摘要" "主题" "行动候选" "最新事件" "生成每日摘要" "首次采集只建立基线" "确认行动" "忽略" "标记已处理" "待人工审核"; do
  if ! grep -q "$text" "$ROOT/app/frontend/src/App.tsx"; then
    echo "frontend Chinese text missing: $text" >&2
    exit 1
  fi
done

for text in "Dashboard" "Recent Events" "ActionCandidates" "Daily Digest" "uncategorized"; do
  if grep -q "$text" "$ROOT/app/frontend/src/App.tsx"; then
    echo "frontend still contains untranslated text: $text" >&2
    exit 1
  fi
done

echo "frontend skeleton ok"
