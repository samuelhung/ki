#!/bin/bash
# 知几更新助手 — 手动安装脚本
# 脱离 App 独立运行，需 sudo 权限（仅一次）
# 用法: sudo bash install_helper.sh
set -euo pipefail

HELPER_NAME="com.zhiji.zhijiDesktop.helper"
APP_PATH="/Applications/知几.app"
BUNDLED_HELPER="${APP_PATH}/Contents/Library/LaunchServices/${HELPER_NAME}"
DEST_HELPER="/Library/PrivilegedHelperTools/${HELPER_NAME}"
PLIST_PATH="/Library/LaunchDaemons/${HELPER_NAME}.plist"

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

echo "🔧 知几更新助手 — 安装脚本"
echo ""

# 权限检查
if [ "$(id -u)" -ne 0 ]; then
    echo -e "${RED}✗ 需要 root 权限${NC}"
    echo "  请运行: sudo bash $0"
    exit 1
fi

# 1. 找 App
if [ ! -d "$APP_PATH" ]; then
    echo -e "${RED}✗ 未找到知几: ${APP_PATH}${NC}"
    echo "  请确认知几已安装到 /Applications/"
    exit 1
fi
echo -e "${GREEN}✓${NC} 找到知几: ${APP_PATH}"

# 2. 找内嵌 Helper
if [ ! -f "$BUNDLED_HELPER" ]; then
    echo -e "${RED}✗ App 内未找到 Helper${NC}"
    echo "  预期路径: ${BUNDLED_HELPER}"
    echo "  请确认知几版本 >= v1.0.28"
    exit 1
fi
echo -e "${GREEN}✓${NC} 找到内嵌 Helper"

# 3. 停止旧服务
if launchctl list "$HELPER_NAME" &>/dev/null; then
    echo "  停止旧 Helper..."
    launchctl unload "$PLIST_PATH" 2>/dev/null || true
fi

# 4. 安装 Helper
echo -n "  安装 Helper → ${DEST_HELPER}... "
mkdir -p /Library/PrivilegedHelperTools
cp -f "$BUNDLED_HELPER" "$DEST_HELPER"
chmod 755 "$DEST_HELPER"
chown root:wheel "$DEST_HELPER"
echo -e "${GREEN}✓${NC}"

# 5. 写入 launchd plist
echo -n "  写入 launchd plist... "
cat > "$PLIST_PATH" << PLISTEOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>${HELPER_NAME}</string>
    <key>MachServices</key>
    <dict>
        <key>${HELPER_NAME}</key>
        <true/>
    </dict>
    <key>ProgramArguments</key>
    <array>
        <string>${DEST_HELPER}</string>
    </array>
    <key>RunAtLoad</key>
    <true/>
    <key>KeepAlive</key>
    <true/>
</dict>
</plist>
PLISTEOF
chmod 644 "$PLIST_PATH"
chown root:wheel "$PLIST_PATH"
echo -e "${GREEN}✓${NC}"

# 6. 加载 launchd
echo -n "  加载 launchd... "
launchctl load "$PLIST_PATH"
echo -e "${GREEN}✓${NC}"

# 7. 验证
sleep 1
if launchctl list "$HELPER_NAME" &>/dev/null; then
    echo ""
    echo -e "${GREEN}✅ 安装完成！${NC}"
    echo "  Helper 已运行，下次更新将自动完成（无需再次授权）"
else
    echo ""
    echo -e "${RED}✗ Helper 未能启动${NC}"
    echo "  请检查日志: sudo launchctl list ${HELPER_NAME}"
    exit 1
fi
