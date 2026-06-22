     1|#!/bin/bash
     2|set -eu
     3|
     4|REPO="samuelhung/ki"
     5|APP_NAME="zhiji-backend"
     6|VERSION="${ZHIJI_VERSION:-}"
     7|INSTALL_QUIET="${ZHIJI_QUIET:-0}"
     8|DATA_DIR="${ZHIJI_HOME:-$HOME/.zhiji}"
     9|
    10|RED='\033[0;31m'
    11|GREEN='\033[0;32m'
    12|BLUE='\033[0;34m'
    13|NC='\033[0m'
    14|
    15|log() { [ "$INSTALL_QUIET" = "1" ] || echo -e "$*"; }
    16|success() { echo -e "${GREEN}✅ $*${NC}"; }
    17|fail() { echo -e "${RED}❌ $*${NC}" >&2; exit 1; }
    18|
    19|log "${BLUE}📦 知几后端安装脚本${NC}"
    20|log ""
    21|
    22|# 1. Check Python
    23|log "1/5 检查环境..."
    24|PYTHON=""
    25|for py in python3.12 python3.11 python3; do
    26|    if command -v "$py" &>/dev/null; then
    27|        ver=$("$py" -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')")
    28|        major=$(echo "$ver" | cut -d. -f1)
    29|        minor=$(echo "$ver" | cut -d. -f2)
    30|        if [ "$major" -ge 3 ] && [ "$minor" -ge 11 ]; then
    31|            PYTHON="$py"
    32|            break
    33|        fi
    34|    fi
    35|done
    36|[ -n "$PYTHON" ] || fail "需要 Python >= 3.11，请先安装"
    37|success "Python: $($PYTHON --version)"
    38|
    39|# 2. Get latest version
    40|log "2/5 获取最新版本..."
    41|if [ -z "$VERSION" ]; then
    42|    VERSION=$(curl -fsSL "https://api.github.com/repos/$REPO/releases/latest" 2>/dev/null | \
    43|        python3 -c "import json,sys; d=json.load(sys.stdin); print(d.get('tag_name','').lstrip('v'))" 2>/dev/null || echo "")
    44|    if [ -z "$VERSION" ]; then
    45|        VERSION=$(curl -fsSL "https://api.github.com/repos/$REPO/releases" 2>/dev/null | \
    46|            python3 -c "import json,sys; d=json.load(sys.stdin); print(d[0]['tag_name'].lstrip('v'))" 2>/dev/null || echo "")
    47|    fi
    48|    [ -n "$VERSION" ] || fail "无法获取最新版本，请手动指定: ZHIJI_VERSION=x.y.z curl ... | sh"
    49|fi
    50|success "版本: v$VERSION"
    51|
    52|# 3. Download whl
    53|log "3/5 下载安装包..."
    54|WHL_URL="https://github.com/$REPO/releases/download/v$VERSION/zhiji_backend-$VERSION-py3-none-any.whl"
    55|TMP_WHL=$(mktemp /tmp/zhiji-backend.XXXXXX.whl)
    56|curl -fsSL "$WHL_URL" -o "$TMP_WHL" || fail "下载失败: $WHL_URL"
    57|success "下载完成"
    58|
    59|# 4. Install
    60|log "4/5 安装..."
    61|"$PYTHON" -m pip install --upgrade "$TMP_WHL" --quiet || fail "安装失败"
    62|rm -f "$TMP_WHL"
    63|success "安装完成"
    64|
    65|# 5. Setup data dir + launchd
    66|log "5/5 配置开机自启..."
    67|LAUNCHD_PLIST="$HOME/Library/LaunchAgents/com.zhiji.backend.plist"
    68|
    69|# Use the pip-installed zhiji binary location
    70|ZHIJI_BIN=$(which zhiji 2>/dev/null || echo "$($PYTHON -c 'import sysconfig; print(sysconfig.get_path("scripts"))')/zhiji")
    71|
    72|mkdir -p "$DATA_DIR"/data
    73|
    74|# Copy .env if exists in old location
    75|OLD_ENV="/Users/mrh/Documents/Projects/zhiji/.env"
    76|if [ -f "$OLD_ENV" ] && [ ! -f "$DATA_DIR/.env" ]; then
    77|    cp "$OLD_ENV" "$DATA_DIR/.env"
    78|    success "已复制配置文件"
    79|fi
    80|
    81|cat > "$LAUNCHD_PLIST" << PLASTEOF
    82|<?xml version="1.0" encoding="UTF-8"?>
    83|<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
    84|<plist version="1.0">
    85|<dict>
    86|    <key>Label</key>
    87|    <string>com.zhiji.backend</string>
    88|    <key>ProgramArguments</key>
    89|    <array>
    90|        <string>$ZHIJI_BIN</string>
    91|        <string>serve</string>
    92|        <string>--host</string>
    93|        <string>0.0.0.0</string>
    94|        <string>--port</string>
    95|        <string>9120</string>
    96|    </array>
    97|    <key>RunAtLoad</key>
    98|    <true/>
    99|    <key>KeepAlive</key>
   100|    <true/>
   101|    <key>WorkingDirectory</key>
   102|    <string>$DATA_DIR</string>
   103|    <key>StandardOutPath</key>
   104|    <string>$HOME/Library/Logs/zhiji-backend.log</string>
   105|    <key>StandardErrorPath</key>
   106|    <string>$HOME/Library/Logs/zhiji-backend.error.log</string>
   107|    <key>EnvironmentVariables</key>
   108|    <dict>
   109|        <key>ZHIJI_HOME</key>
   110|        <string>$DATA_DIR</string>
   111|    </dict>
   112|</dict>
   113|</plist>
   114|PLASTEOF
   115|
   116|# Migrate old data (symlink for dev, copy for release)
   117|OLD_DATA="/Users/mrh/Documents/Projects/zhiji/data"
   118|if [ -d "$OLD_DATA" ] && [ ! -d "$DATA_DIR/data/intelligence.sqlite" ] && [ ! -L "$DATA_DIR/data/intelligence.sqlite" ]; then
   119|    log "发现旧数据，创建符号链接..."
   120|    ln -sf "$OLD_DATA" "$DATA_DIR/data"
   121|fi
   122|
   123|launchctl unload "$LAUNCHD_PLIST" 2>/dev/null || true
   124|launchctl load "$LAUNCHD_PLIST"
   125|success "服务已配置开机自启"
   126|
   127|echo ""
   128|echo "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
   129|echo "  ${GREEN}知几后端安装完成！${NC}"
   130|echo ""
   131|echo "  打开浏览器访问："
   132|echo "  ${BLUE}http://localhost:9120${NC}"
   133|echo ""
   134|echo "  管理命令："
   135|echo "  zhiji serve        启动服务"
   136|echo "  zhiji version      查看版本"
   137|echo ""
   138|echo "  服务管理："
   139|echo "  launchctl stop com.zhiji.backend    停止"
   140|echo "  launchctl start com.zhiji.backend   启动"
   141|echo ""
   142|echo "  日志："
   143|echo "  tail -f ~/Library/Logs/zhiji-backend.log"
   144|echo "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
   145|