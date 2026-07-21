#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

fail() {
  echo "FAIL: $*" >&2
  exit 1
}

[[ ! -e desktop/macos/Helper ]] || fail "retired Helper source directory still exists"

if rg -n "com\.zhiji\.zhijiDesktop\.helper|ZhijiHelper|com\.zhiji\.helper|build_helper\.sh|MachServices|mach-lookup" \
  desktop/macos/Runner desktop/macos/Runner.xcodeproj/project.pbxproj; then
  fail "retired Helper build, XPC, MethodChannel, or entitlement integration remains"
fi

rg -n "com\.zhiji\.sparkle" desktop/macos/Runner/AppDelegate.swift >/dev/null \
  || fail "Sparkle MethodChannel must remain registered"

SCRIPT="scripts/remove_legacy_helper.sh"
[[ -x "$SCRIPT" ]] || fail "$SCRIPT must exist and be executable"

rg -n '^HELPER_PATH="/Library/PrivilegedHelperTools/com\.zhiji\.zhijiDesktop\.helper"$' "$SCRIPT" >/dev/null \
  || fail "cleanup script helper path is not exact"
rg -n '^PLIST_PATH="/Library/LaunchDaemons/com\.zhiji\.zhijiDesktop\.helper\.plist"$' "$SCRIPT" >/dev/null \
  || fail "cleanup script plist path is not exact"
rg -n '^SERVICE="system/com\.zhiji\.zhijiDesktop\.helper"$' "$SCRIPT" >/dev/null \
  || fail "cleanup script service target is not exact"
rg -n 'EUID.*-ne 0|id -u.*-ne 0' "$SCRIPT" >/dev/null \
  || fail "--remove must require sudo/root"

"$SCRIPT" --check
"$SCRIPT" --check

if "$SCRIPT" --unknown >/dev/null 2>&1; then
  fail "unknown cleanup mode must fail"
fi

if rg -n "ki_session|HttpOnly 会话|同源会话" README.md wiki/Architecture.md; then
  fail "cookie-session documentation remains"
fi

echo "legacy helper removal checks passed"
