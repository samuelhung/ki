#!/usr/bin/env bash
# ============================================================
# 知几 统一发版脚本
#
# 用法:
#   ./scripts/release.sh <version>          完整发版（服务端+桌面端）
#   ./scripts/release.sh <version> server   仅服务端
#   ./scripts/release.sh <version> desktop  仅桌面端
#
# 流程:
#   1. 更新版本号（server __init__.py + desktop pubspec.yaml）
#   2. 构建服务端 whl
#   3. 构建桌面端 DMG + 增量补丁 + manifest.json
#   4. 创建 GitHub Release 并上传产物
#   5. 打 tag 并推送
# ============================================================
set -euo pipefail

RED='\033[0;31m'
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
NC='\033[0m'

log()    { echo -e "${BLUE}→${NC} $*"; }
success(){ echo -e "${GREEN}✅${NC} $*"; }
warn()   { echo -e "${YELLOW}⚠️${NC} $*"; }
fail()   { echo -e "${RED}❌ $*${NC}" >&2; exit 1; }

# ---- 参数 ----
VERSION="${1:-}"
TARGET="${2:-all}"

if [ -z "$VERSION" ]; then
    echo "用法: $0 <version> [server|desktop|all]"
    echo "示例: $0 1.10.0"
    exit 1
fi

# 去除可能的前导 v
VERSION="${VERSION#v}"

PROJECT_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$PROJECT_ROOT"

REPO="samuelhung/ki"
SERVER_INIT="src/zhiji_backend/__init__.py"
DESKTOP_PUBSPEC="desktop/pubspec.yaml"

echo ""
echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "${BLUE}  知几 发版 v${VERSION}${NC}"
echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo ""

# ============================================================
# 1. 版本号更新
# ============================================================
bump_version() {
    log "更新版本号..."

    if [ "$TARGET" = "all" ] || [ "$TARGET" = "server" ]; then
        # 更新 __init__.py
        sed -i '' "s/__version__ = \".*\"/__version__ = \"$VERSION\"/" "$SERVER_INIT"
        success "server: $SERVER_INIT → $VERSION"
    fi

    if [ "$TARGET" = "all" ] || [ "$TARGET" = "desktop" ]; then
        # 更新 pubspec.yaml（保持 build number 不变，只改 version）
        local current_line
        current_line=$(grep "^version:" "$DESKTOP_PUBSPEC" | head -1)
        local build_num
        build_num=$(echo "$current_line" | sed 's/.*+//')
        sed -i '' "s/^version: .*/version: ${VERSION}+${build_num}/" "$DESKTOP_PUBSPEC"
        success "desktop: $DESKTOP_PUBSPEC → ${VERSION}+${build_num}"
    fi
}

# ============================================================
# 2. 构建服务端
# ============================================================
build_server() {
    log "构建服务端 whl..."

    # 清理旧产物
    rm -rf dist/ build/ *.egg-info

    # 构建
    python3 -m build --wheel || fail "whl 构建失败"

    local whl_file
    whl_file=$(ls dist/zhiji_backend-*.whl | head -1)
    local whl_name
    whl_name=$(basename "$whl_file")

    success "服务端 whl: $whl_name ($(du -h "$whl_file" | cut -f1))"
    echo "$whl_file"
}

# ============================================================
# 3. 构建桌面端
# ============================================================
build_desktop() {
    log "构建桌面端..."

    python3 scripts/build_release.py --version "$VERSION" || fail "桌面端构建失败"

    success "桌面端构建完成 → desktop/build/release/"
}

# ============================================================
# 4. Git 提交 & Tag
# ============================================================
commit_and_tag() {
    log "提交版本变更..."

    if git diff --quiet && git diff --cached --quiet; then
        warn "没有文件变更，跳过提交"
    else
        git add "$SERVER_INIT" "$DESKTOP_PUBSPEC"
        git commit -m "release: v${VERSION}"
        success "已提交"
    fi

    log "创建 tag v${VERSION}..."
    if git rev-parse "v${VERSION}" >/dev/null 2>&1; then
        warn "tag v${VERSION} 已存在，删除重建"
        git tag -d "v${VERSION}"
    fi
    git tag "v${VERSION}"
    success "tag v${VERSION} 已创建"
}

# ============================================================
# 5. 创建 GitHub Release
# ============================================================
create_release() {
    log "创建 GitHub Release..."

    local release_assets=()
    local release_notes="知几 v${VERSION}"

    # 服务端资产
    if [ "$TARGET" = "all" ] || [ "$TARGET" = "server" ]; then
        local whl_file
        whl_file=$(ls dist/zhiji_backend-*.whl 2>/dev/null | head -1)
        if [ -n "$whl_file" ]; then
            release_assets+=("$whl_file")
        fi
        release_notes+="

🔧 服务端
- \`curl -fsSL https://raw.githubusercontent.com/samuelhung/ki/main/scripts/install.sh | sh\`"
    fi

    # 桌面端资产
    if [ "$TARGET" = "all" ] || [ "$TARGET" = "desktop" ]; then
        local release_dir="desktop/build/release"
        if [ -d "$release_dir" ]; then
            # DMG
            local dmg_file
            dmg_file=$(ls "$release_dir"/*.dmg 2>/dev/null | head -1)
            [ -n "$dmg_file" ] && release_assets+=("$dmg_file")

            # manifest.json
            [ -f "$release_dir/manifest.json" ] && release_assets+=("$release_dir/manifest.json")

            # patches
            for patch in "$release_dir"/patch_*.bsdiff; do
                [ -f "$patch" ] && release_assets+=("$patch")
            done
        fi
        release_notes+="

💻 桌面端
- 下载 DMG 拖入 Applications 即可
- 启动后自动检查增量更新"
    fi

    # 用 gh CLI 创建 release
    local gh_args=()
    for asset in "${release_assets[@]}"; do
        gh_args+=("$asset")
    done

    if command -v gh &>/dev/null; then
        gh release create "v${VERSION}" \
            "${gh_args[@]}" \
            --title "知几 v${VERSION}" \
            --notes "$release_notes" \
            --repo "$REPO" \
            || fail "GitHub Release 创建失败"

        success "GitHub Release v${VERSION} 已发布"
    else
        warn "gh CLI 未安装，跳过 GitHub Release 创建"
        echo ""
        echo "手动上传以下文件到:"
        echo "  https://github.com/$REPO/releases/new?tag=v${VERSION}"
        echo ""
        for asset in "${release_assets[@]}"; do
            echo "  - $asset"
        done
    fi
}

# ============================================================
# 6. 推送
# ============================================================
push_all() {
    log "推送到 GitHub..."
    git push origin main || fail "推送 main 失败"
    git push origin "v${VERSION}" || fail "推送 tag 失败"
    success "已推送 main + v${VERSION}"
}

# ============================================================
# 执行
# ============================================================

# 检查依赖
command -v python3 >/dev/null 2>&1 || fail "需要 Python 3"
command -v flutter >/dev/null 2>&1 || fail "需要 Flutter"
command -v bsdiff  >/dev/null 2>&1 || fail "需要 bsdiff（brew install bsdiff）"

# 检查 git 状态
if ! git diff --quiet || ! git diff --cached --quiet; then
    warn "工作区有未提交的变更！"
    warn "请先提交或暂存，再执行发版。"
    exit 1
fi

# 1. 版本号
bump_version

# 2. 构建
if [ "$TARGET" = "all" ] || [ "$TARGET" = "server" ]; then
    build_server
fi

if [ "$TARGET" = "all" ] || [ "$TARGET" = "desktop" ]; then
    build_desktop
fi

# 3. 提交 + tag
commit_and_tag

# 4. GitHub Release
create_release

# 5. 推送
push_all

echo ""
echo -e "${GREEN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "${GREEN}  🎉 知几 v${VERSION} 发版完成！${NC}"
echo -e "${GREEN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo ""
echo "服务端安装:"
echo "  curl -fsSL https://raw.githubusercontent.com/samuelhung/ki/main/scripts/install.sh | sh"
echo ""
echo "桌面端下载:"
echo "  https://github.com/samuelhung/ki/releases/download/v${VERSION}/zhiji_desktop_${VERSION}_universal.dmg"
echo ""
echo "桌面端更新检测:"
echo "  https://github.com/samuelhung/ki/releases/latest/download/manifest.json"
echo ""
