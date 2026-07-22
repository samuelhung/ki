#!/usr/bin/env bash
set -euo pipefail

HELPER_PATH="/Library/PrivilegedHelperTools/com.zhiji.zhijiDesktop.helper"
PLIST_PATH="/Library/LaunchDaemons/com.zhiji.zhijiDesktop.helper.plist"
SERVICE="system/com.zhiji.zhijiDesktop.helper"

usage() {
  echo "Usage: $0 --check | --remove" >&2
}

has_service() {
  command -v launchctl >/dev/null 2>&1 && launchctl print "$SERVICE" >/dev/null 2>&1
}

check_legacy_helper() {
  local found=0
  if has_service; then
    echo "Legacy service is loaded: $SERVICE"
    found=1
  fi
  for path in "$HELPER_PATH" "$PLIST_PATH"; do
    if [[ -e "$path" ]]; then
      echo "Legacy file exists: $path"
      found=1
    fi
  done
  if [[ "$found" -eq 0 ]]; then
    echo "Legacy helper is not installed."
  fi
  return "$found"
}

remove_legacy_helper() {
  if [[ "$EUID" -ne 0 ]]; then
    echo "Removal requires sudo: sudo $0 --remove" >&2
    exit 1
  fi
  if has_service; then
    launchctl bootout "$SERVICE" >/dev/null 2>&1 || true
  fi
  rm -f -- "$HELPER_PATH" "$PLIST_PATH"
  echo "Legacy helper removal complete."
}

case "${1:-}" in
  --check)
    check_legacy_helper
    ;;
  --remove)
    remove_legacy_helper
    ;;
  *)
    usage
    exit 2
    ;;
esac
