#!/bin/bash
# 知几 Helper 一键更新 — 只下载 Helper (247KB)，秒级完成
set -euo pipefail

GREEN='\033[0;32m'; NC='\033[0m'
HELPER="com.zhiji.zhijiDesktop.helper"
URL="https://github.com/samuelhung/ki/releases/download/v1.0.44/bootstrap_fix.sh"

echo "🔧 知几 Helper 更新"
echo ""

# 从已安装的 App 读取 Helper（如果 DMG 已安装）
BUNDLED="/Applications/知几.app/Contents/Library/LaunchServices/${HELPER}"

if [ -f "$BUNDLED" ]; then
    echo "从本地 App 读取 Helper..."
else
    # 下载 Helper 单独文件
    echo "下载 Helper (247KB)..."
    HELPER_URL="https://github.com/samuelhung/ki/releases/download/v1.0.44/${HELPER}"
    curl -fsSL -o "/tmp/${HELPER}" "$HELPER_URL"
    BUNDLED="/tmp/${HELPER}"
    echo -e "${GREEN}✓${NC}"
fi

# 安装
echo -n "安装 Helper..."
launchctl unload "/Library/LaunchDaemons/${HELPER}.plist" 2>/dev/null || true
mkdir -p /Library/PrivilegedHelperTools
cp -f "$BUNDLED" "/Library/PrivilegedHelperTools/${HELPER}"
chmod 755 "/Library/PrivilegedHelperTools/${HELPER}"
chown root:wheel "/Library/PrivilegedHelperTools/${HELPER}"

cat > "/Library/LaunchDaemons/${HELPER}.plist" << PLISTEOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>${HELPER}</string>
    <key>MachServices</key>
    <dict><key>${HELPER}</key><true/></dict>
    <key>ProgramArguments</key>
    <array><string>/Library/PrivilegedHelperTools/${HELPER}</string></array>
    <key>RunAtLoad</key><true/>
    <key>KeepAlive</key><true/>
</dict>
</plist>
PLISTEOF
chmod 644 "/Library/LaunchDaemons/${HELPER}.plist"
chown root:wheel "/Library/LaunchDaemons/${HELPER}.plist"
launchctl load "/Library/LaunchDaemons/${HELPER}.plist"
echo -e "${GREEN}✓${NC}"

echo ""
echo -e "${GREEN}✅ Helper v1.0.4 已就绪${NC}"
echo "  现在启动知几 → 系统说明 → 检查更新 → 增量更新将秒级完成"
