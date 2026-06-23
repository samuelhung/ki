#!/bin/bash
# 构建知几特权 Helper（SMJobBless）
# 由 Xcode Build Phase 调用，在 flutter assemble 之后运行
# 编译为通用二进制（x86_64 + arm64）
set -euo pipefail

SRCROOT="${SRCROOT:-$(cd "$(dirname "$0")/.." && pwd)}"
BUILT_PRODUCTS_DIR="${BUILT_PRODUCTS_DIR:-$SRCROOT/build/Release}"
CONTENTS_FOLDER_PATH="${CONTENTS_FOLDER_PATH:-}"
HELPER_NAME="com.zhiji.zhijiDesktop.helper"
HELPER_SRC="$SRCROOT/Helper"
SDK_PATH="$(xcrun --sdk macosx --show-sdk-path)"

echo "🔨 构建知几特权 Helper (通用二进制)..."

# 清理
HELPER_TMP="$(mktemp -d)"
trap 'rm -rf "$HELPER_TMP"' EXIT

SWIFT_FILES=(
  "$HELPER_SRC/ZhijiHelperProtocol.swift"
  "$HELPER_SRC/ZhijiHelper.swift"
  "$HELPER_SRC/main.swift"
)

LINK_FLAGS=(
  -Xlinker -sectcreate -Xlinker __TEXT -Xlinker __info_plist -Xlinker "$HELPER_SRC/Info.plist"
  -Xlinker -sectcreate -Xlinker __TEXT -Xlinker __launchd_plist -Xlinker "$HELPER_SRC/Launchd.plist"
)

# 编译 arm64
echo "  编译 arm64..."
swiftc -O \
  -target arm64-apple-macos10.15 \
  -sdk "$SDK_PATH" \
  "${LINK_FLAGS[@]}" \
  -o "$HELPER_TMP/${HELPER_NAME}_arm64" \
  "${SWIFT_FILES[@]}"

# 编译 x86_64
echo "  编译 x86_64..."
swiftc -O \
  -target x86_64-apple-macos10.15 \
  -sdk "$SDK_PATH" \
  "${LINK_FLAGS[@]}" \
  -o "$HELPER_TMP/${HELPER_NAME}_x86_64" \
  "${SWIFT_FILES[@]}"

# 合并为通用二进制
lipo -create \
  "$HELPER_TMP/${HELPER_NAME}_arm64" \
  "$HELPER_TMP/${HELPER_NAME}_x86_64" \
  -output "$HELPER_TMP/$HELPER_NAME"

echo "  ✅ 编译完成 ($(file "$HELPER_TMP/$HELPER_NAME" | sed 's/.*://'))"

# 代码签名（Ad-hoc，与主 App 相同策略）
codesign --force --sign - "$HELPER_TMP/$HELPER_NAME"
echo "  ✅ Ad-hoc 签名完成"

# 找到 App Bundle 并嵌入
find_app_bundle() {
  if [ -n "$CONTENTS_FOLDER_PATH" ] && [ -d "$CONTENTS_FOLDER_PATH" ]; then
    echo "$CONTENTS_FOLDER_PATH"
    return
  fi
  for app in "$BUILT_PRODUCTS_DIR"/*.app; do
    if [ -d "$app" ]; then
      echo "$app/Contents"
      return
    fi
  done
  local app_path="$BUILT_PRODUCTS_DIR/知几.app"
  if [ -d "$app_path" ]; then
    echo "$app_path/Contents"
    return
  fi
  echo ""
}

APP_CONTENTS=$(find_app_bundle)

if [ -n "$APP_CONTENTS" ]; then
  LAUNCH_SERVICES="$APP_CONTENTS/Library/LaunchServices"
  mkdir -p "$LAUNCH_SERVICES"
  cp "$HELPER_TMP/$HELPER_NAME" "$LAUNCH_SERVICES/"
  echo "  ✅ 已嵌入: $LAUNCH_SERVICES/$HELPER_NAME"
else
  echo "  ⚠️ 未找到 App Bundle，跳过嵌入"
fi

echo "🔨 Helper 构建完成"
