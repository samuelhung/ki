#!/usr/bin/env bash
set -euo pipefail

cat >&2 <<'EOF'
❌ scripts/bootstrap_fix.sh 已废弃，禁止使用。

旧 Helper/增量更新方案已停止维护。当前更新方式是 Sparkle 全量 DMG：

  知几.app → appcast.xml → GitHub Release DMG → Sparkle 验签安装

如需修复安装，请直接下载最新 GitHub Release 中的 zhiji_X.Y.Z.dmg 覆盖安装。
EOF

exit 1