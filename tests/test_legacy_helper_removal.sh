#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

fail() {
  echo "FAIL: $*" >&2
  exit 1
}

search() {
  if command -v rg >/dev/null 2>&1; then
    rg -n "$@"
  else
    grep -Ern "$@"
  fi
}

[[ ! -e desktop/macos/Helper ]] || fail "retired Helper source directory still exists"

if search "com\.zhiji\.zhijiDesktop\.helper|ZhijiHelper|com\.zhiji\.helper|build_helper\.sh|MachServices|mach-lookup" \
  desktop/macos/Runner desktop/macos/Runner.xcodeproj/project.pbxproj; then
  fail "retired Helper build, XPC, MethodChannel, or entitlement integration remains"
fi

search "com\.zhiji\.sparkle" desktop/macos/Runner/AppDelegate.swift >/dev/null \
  || fail "Sparkle MethodChannel must remain registered"

SCRIPT="scripts/remove_legacy_helper.sh"
[[ -x "$SCRIPT" ]] || fail "$SCRIPT must exist and be executable"

search '^HELPER_PATH="/Library/PrivilegedHelperTools/com\.zhiji\.zhijiDesktop\.helper"$' "$SCRIPT" >/dev/null \
  || fail "cleanup script helper path is not exact"
search '^PLIST_PATH="/Library/LaunchDaemons/com\.zhiji\.zhijiDesktop\.helper\.plist"$' "$SCRIPT" >/dev/null \
  || fail "cleanup script plist path is not exact"
search '^SERVICE="system/com\.zhiji\.zhijiDesktop\.helper"$' "$SCRIPT" >/dev/null \
  || fail "cleanup script service target is not exact"
search 'EUID.*-ne 0|id -u.*-ne 0' "$SCRIPT" >/dev/null \
  || fail "--remove must require sudo/root"

"$SCRIPT" --check
"$SCRIPT" --check

if "$SCRIPT" --unknown >/dev/null 2>&1; then
  fail "unknown cleanup mode must fail"
fi

if search "ki_session|HttpOnly 会话|同源会话" README.md wiki/Architecture.md; then
  fail "cookie-session documentation remains"
fi

if [[ "${LEGACY_HELPER_REMOVAL_NO_RG_CHILD:-0}" != "1" ]]; then
  no_rg_path="$(mktemp -d)"
  trap 'rm -rf "$no_rg_path"' EXIT

  for tool in bash dirname grep; do
    tool_path="$(command -v "$tool")" || fail "required test tool is unavailable: $tool"
    ln -s "$tool_path" "$no_rg_path/$tool"
  done

  if ! LEGACY_HELPER_REMOVAL_NO_RG_CHILD=1 PATH="$no_rg_path" \
    "$no_rg_path/bash" "$0" >/dev/null; then
    fail "legacy helper removal checks must pass without rg"
  fi
fi

echo "legacy helper removal checks passed"
