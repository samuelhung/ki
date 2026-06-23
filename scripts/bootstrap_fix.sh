#!/bin/bash
# 知几一键修复 — 下载最新版并安装 Helper
# 一条命令彻底解决增量更新闪退
set -euo pipefail

RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; NC='\033[0m'
REPO="samuelhung/ki"
TMP=$(mktemp -d)
cd "$TMP"

echo "🔧 知几一键修复"
echo ""

# 1. 获取最新版本号
echo -n "查询最新版本... "
LATEST=$(curl -fsSL "https://api.github.com/repos/${REPO}/releases/latest" | python3 -c "import sys,json; print(json.load(sys.stdin)['tag_name'].lstrip('v'))")
echo -e "${GREEN}v${LATEST}${NC}"

# 2. 下载 DMG
DMG="zhiji_desktop_${LATEST}_universal.dmg"
URL="https://github.com/${REPO}/releases/download/v${LATEST}/${DMG}"
echo -n "下载 ${DMG}... "
curl -fsSL -o "${DMG}" "$URL"
SIZE=$(du -h "${DMG}" | cut -f1)
echo -e "${GREEN}${SIZE}${NC}"

# 3. 挂载 DMG
echo -n "挂载 DMG... "
hdiutil attach "${DMG}" -nobrowse -quiet
echo -e "${GREEN}✓${NC}"

# 4. 替换 App
echo -n "替换知几.app... "
if [ -d "/Applications/知几.app" ]; then
    rm -rf "/Applications/知几.app"
fi
cp -a /Volumes/知几/知几.app /Applications/
echo -e "${GREEN}✓${NC}"

# 5. 卸载 DMG
echo -n "卸载 DMG... "
hdiutil detach /Volumes/知几 -quiet
echo -e "${GREEN}✓${NC}"

# 6. 安装 Helper
HELPER="com.zhiji.zhijiDesktop.helper"
BUNDLED="/Applications/知几.app/Contents/Library/LaunchServices/${HELPER}"
if [ ! -f "$BUNDLED" ]; then
    echo -e "${RED}✗ App 内未找到 Helper${NC}"
    exit 1
fi

echo -n "安装 Helper... "
launchctl unload "/Library/LaunchDaemons/${HELPER}.plist" 2>/dev/null || true
mkdir -p /Library/PrivilegedHelperTools
cp -f "$BUNDLED" "/Library/PrivilegedHelperTools/${HELPER}"
chmod 755 "/Library/PrivilegedHelperTools/${HELPER}"
chown root:wheel "/Library/PrivilegedHelperTools/${HELPER}"

# launchd plist
cat > "/Library/LaunchDaemons/${HELPER}.plist" << PLISTEOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>${HELPER}</string>
    <key>MachServices</key>
    <dict>
        <key>${HELPER}</key>
        <true/>
    </dict>
    <key>ProgramArguments</key>
    <array>
        <string>/Library/PrivilegedHelperTools/${HELPER}</string>
    </array>
    <key>RunAtLoad</key>
    <true/>
    <key>KeepAlive</key>
    <true/>
</dict>
</plist>
PLISTEOF
chmod 644 "/Library/LaunchDaemons/${HELPER}.plist"
chown root:wheel "/Library/LaunchDaemons/${HELPER}.plist"
launchctl load "/Library/LaunchDaemons/${HELPER}.plist"
echo -e "${GREEN}✓${NC}"

# 7. 清理
cd / && rm -rf "$TMP"

echo ""
echo -e "${GREEN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "${GREEN}✅ 修复完成！${NC}"
echo ""
echo "  知几 v${LATEST} 已安装"
echo "  Helper v1.0.4 已就绪"
echo "  以后的增量更新将全自动、零弹窗"
echo -e "${GREEN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
