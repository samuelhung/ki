#!/bin/bash
set -eu

REPO="samuelhung/ki"
APP_NAME="zhiji-backend"
VERSION="${ZHIJI_VERSION:-}"
INSTALL_QUIET="${ZHIJI_QUIET:-0}"
DATA_DIR="${ZHIJI_HOME:-$HOME/.zhiji}"
HOST="${ZHIJI_HOST:-127.0.0.1}"

RED='\033[0;31m'
GREEN='\033[0;32m'
BLUE='\033[0;34m'
NC='\033[0m'

log() { [ "$INSTALL_QUIET" = "1" ] || echo -e "$*"; }
success() { echo -e "${GREEN}✅ $*${NC}"; }
fail() { echo -e "${RED}❌ $*${NC}" >&2; exit 1; }

log "${BLUE}📦 知几后端安装脚本${NC}"
log ""

# 1. Check Python
log "1/5 检查环境..."
PYTHON=""
for py in python3.12 python3.11 python3; do
    if command -v "$py" &>/dev/null; then
        ver=$("$py" -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')")
        major=$(echo "$ver" | cut -d. -f1)
        minor=$(echo "$ver" | cut -d. -f2)
        if [ "$major" -ge 3 ] && [ "$minor" -ge 11 ]; then
            PYTHON="$py"
            break
        fi
    fi
done
[ -n "$PYTHON" ] || fail "需要 Python >= 3.11，请先安装"
success "Python: $($PYTHON --version)"

# 2. Get latest version
log "2/5 获取最新版本..."
if [ -z "$VERSION" ]; then
    VERSION=$(curl -fsSL "https://api.github.com/repos/$REPO/releases/latest" 2>/dev/null | \
        python3 -c "import json,sys; d=json.load(sys.stdin); print(d.get('tag_name','').lstrip('v'))" 2>/dev/null || echo "")
    if [ -z "$VERSION" ]; then
        VERSION=$(curl -fsSL "https://api.github.com/repos/$REPO/releases" 2>/dev/null | \
            python3 -c "import json,sys; d=json.load(sys.stdin); print(d[0]['tag_name'].lstrip('v'))" 2>/dev/null || echo "")
    fi
    [ -n "$VERSION" ] || fail "无法获取最新版本，请手动指定: ZHIJI_VERSION=x.y.z curl ... | sh"
fi
success "版本: v$VERSION"

# 3. Download whl
log "3/5 下载安装包..."
WHL_URL="https://github.com/$REPO/releases/download/v$VERSION/zhiji_backend-$VERSION-py3-none-any.whl"
TMP_WHL=$(mktemp /tmp/zhiji-backend.XXXXXX.whl)
curl -fsSL "$WHL_URL" -o "$TMP_WHL" || fail "下载失败: $WHL_URL"
success "下载完成"

# 4. Install
log "4/5 安装..."
"$PYTHON" -m pip install --upgrade "$TMP_WHL" --quiet || fail "安装失败"
rm -f "$TMP_WHL"
success "安装完成"

# 5. Setup data dir + launchd
log "5/5 配置开机自启..."
LAUNCHD_PLIST="$HOME/Library/LaunchAgents/com.zhiji.backend.plist"

# Use the pip-installed zhiji binary location
ZHIJI_BIN=$(which zhiji 2>/dev/null || echo "$($PYTHON -c 'import sysconfig; print(sysconfig.get_path("scripts"))')/zhiji")

mkdir -p "$DATA_DIR"/data

# Copy .env if exists in old location
OLD_ENV="/Users/mrh/Documents/Projects/zhiji/.env"
if [ -f "$OLD_ENV" ] && [ ! -f "$DATA_DIR/.env" ]; then
    cp "$OLD_ENV" "$DATA_DIR/.env"
    success "已复制配置文件"
fi

cat > "$LAUNCHD_PLIST" << PLISTEOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.zhiji.backend</string>
    <key>ProgramArguments</key>
    <array>
        <string>$ZHIJI_BIN</string>
        <string>serve</string>
        <string>--host</string>
        <string>$HOST</string>
        <string>--port</string>
        <string>9120</string>
    </array>
    <key>RunAtLoad</key>
    <true/>
    <key>KeepAlive</key>
    <true/>
    <key>WorkingDirectory</key>
    <string>$DATA_DIR</string>
    <key>StandardOutPath</key>
    <string>$HOME/Library/Logs/zhiji-backend.log</string>
    <key>StandardErrorPath</key>
    <string>$HOME/Library/Logs/zhiji-backend.error.log</string>
    <key>EnvironmentVariables</key>
    <dict>
        <key>ZHIJI_HOME</key>
        <string>$DATA_DIR</string>
    </dict>
</dict>
</plist>
PLISTEOF

# Migrate old data (symlink for dev, copy for release)
OLD_DATA="/Users/mrh/Documents/Projects/zhiji/data"
if [ -d "$OLD_DATA" ] && [ ! -d "$DATA_DIR/data/intelligence.sqlite" ] && [ ! -L "$DATA_DIR/data/intelligence.sqlite" ]; then
    log "发现旧数据，创建符号链接..."
    ln -sf "$OLD_DATA" "$DATA_DIR/data"
fi

launchctl unload "$LAUNCHD_PLIST" 2>/dev/null || true
launchctl load "$LAUNCHD_PLIST"
success "服务已配置开机自启"

echo ""
echo "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo "  ${GREEN}知几后端安装完成！${NC}"
echo ""
echo "  打开浏览器访问："
echo "  ${BLUE}http://localhost:9120${NC}"
echo ""
echo "  管理命令："
echo "  zhiji serve        启动服务"
echo "  zhiji version      查看版本"
echo ""
echo "  服务管理："
echo "  launchctl stop com.zhiji.backend    停止"
echo "  launchctl start com.zhiji.backend   启动"
echo ""
echo "  日志："
echo "  tail -f ~/Library/Logs/zhiji-backend.log"
echo "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
