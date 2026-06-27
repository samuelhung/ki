#!/usr/bin/env bash
set -euo pipefail

cat >&2 <<'EOF'
❌ scripts/update_helper_only.sh 已废弃，禁止使用。

旧 Helper/增量更新方案已停止维护。当前更新方式是 Sparkle 全量 DMG。
请使用 GitHub Release 的 zhiji_X.Y.Z.dmg 或知几内置“检查更新”。
EOF

exit 1