#!/usr/bin/env bash
set -euo pipefail

cat >&2 <<'EOF'
❌ scripts/release.sh 已废弃，禁止使用。

当前权威发布流程是 Sparkle 全量 DMG + GitHub Release：

  1. 同步版本号与 changelog
  2. cd app/frontend && npm run build
  3. export PATH="$HOME/flutter/bin:$PATH"
  4. cd desktop && flutter build macos --release
  5. cd .. && python3 scripts/build_release.py --skip-build
  6. python3 scripts/release-check.py X.Y.Z
  7. git add appcast.xml 版本文件 功能改动 && git commit && git push origin main
  8. gh release create 'vX.Y.Z+N' desktop/build/release/zhiji_X.Y.Z.dmg --notes-file desktop/build/release/RELEASE_NOTES.md
  9. 验证远端 appcast 首条和 GitHub Release asset

不要再使用旧的 bsdiff / manifest.json / install_helper 流程。
EOF

exit 1