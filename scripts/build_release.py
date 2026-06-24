#!/usr/bin/env python3
"""
知几桌面端发布构建脚本

功能:
  1. 编译 Flutter macOS
  2. 签名 .app 和 DMG（自签证书 Zhiji）
  3. 生成/更新 Sparkle appcast.xml（EdDSA 签名）
  4. 生成 RELEASE_NOTES.md（来自 changelog.json）

输出: build/release/
  └── zhiji_<X.Y.Z>.dmg                       DMG 安装包（Sparkle 自动更新用）

依赖: flutter, hdiutil, codesign, Sparkle sign_update
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DESKTOP_DIR = PROJECT_ROOT / "desktop"
BUILD_DIR = DESKTOP_DIR / "build"
RELEASE_DIR = BUILD_DIR / "release"
FLUTTER_APP = BUILD_DIR / "macos" / "Build" / "Products" / "Release" / "知几.app"
APP_BINARY = FLUTTER_APP / "Contents" / "Frameworks" / "App.framework" / "Versions" / "A" / "App"

GITHUB_REPO = "samuelhung/ki"
GITHUB_API = f"https://api.github.com/repos/{GITHUB_REPO}"


def _read_desktop_version() -> str:
    """从 pubspec.yaml 读取版本号（不含 build number）。"""
    pubspec = DESKTOP_DIR / "pubspec.yaml"
    content = pubspec.read_text()
    m = re.search(r"^version:\s*(\S+)", content, re.MULTILINE)
    if not m:
        sys.exit("❌ 找不到 version 字段")
    return m.group(1).split("+")[0]  # "1.0.0+1" → "1.0.0"


def _read_full_version() -> str:
    """从 pubspec.yaml 读取完整版本号（含 build number，如 '1.0.51+52'）。"""
    pubspec = DESKTOP_DIR / "pubspec.yaml"
    content = pubspec.read_text()
    m = re.search(r"^version:\s*(\S+)", content, re.MULTILINE)
    if not m:
        sys.exit("❌ 找不到 version 字段")
    return m.group(1)  # "1.0.51+52"


def _shasum(path: Path) -> str:
    """计算文件 SHA256。"""
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()


def build_flutter() -> bool:
    """编译 Flutter macOS Release。"""
    print("🔨 编译 Flutter macOS...")
    result = subprocess.run(
        ["flutter", "build", "macos"],
        cwd=DESKTOP_DIR,
        capture_output=False,
        timeout=300,
    )
    if result.returncode != 0:
        print("❌ Flutter 编译失败")
        return False
    print(f"✅ 编译完成: {APP_BINARY}")
    return True


def build_dmg(version: str) -> Path:
    """创建 DMG 安装包。"""
    dmg_name = f"zhiji_{version}.dmg"
    dmg_path = RELEASE_DIR / dmg_name

    RELEASE_DIR.mkdir(parents=True, exist_ok=True)

    # 准备 staging 目录
    staging = BUILD_DIR / "dmg_staging"
    if staging.exists():
        shutil.rmtree(staging)
    staging.mkdir(parents=True)

    shutil.copytree(FLUTTER_APP, staging / "知几.app", symlinks=True)
    (staging / "Applications").symlink_to("/Applications")

    print(f"📦 打包 DMG: {dmg_name}")
    subprocess.run(
        [
            "hdiutil", "create",
            "-volname", "知几",
            "-srcfolder", str(staging),
            "-ov", "-format", "UDZO",
            "-imagekey", "zlib-level=9",
            str(dmg_path),
        ],
        capture_output=True,
        timeout=120,
        check=True,
    )

    size = dmg_path.stat().st_size / (1024 * 1024)
    print(f"✅ DMG: {dmg_name} ({size:.1f} MB)")
    return dmg_path


def _generate_appcast_entry(version: str, dmg_path: Path) -> str | None:
    """用 Sparkle sign_update 签名 DMG，返回 appcast <item> XML 片段。"""
    sign_update = DESKTOP_DIR / "macos" / "Pods" / "Sparkle" / "bin" / "sign_update"
    if not sign_update.exists():
        print(f"⚠️  sign_update 未找到: {sign_update}")
        return None

    result = subprocess.run(
        [str(sign_update), str(dmg_path)],
        capture_output=True, text=True, timeout=15,
    )
    if result.returncode != 0:
        print(f"⚠️  sign_update 失败: {result.stderr}")
        return None

    ed_sig_raw = result.stdout.strip()
    # sign_update 输出: sparkle:edSignature="xxx" length="nnn"
    m = re.search(r'sparkle:edSignature="([^"]+)"', ed_sig_raw)
    ed_sig = m.group(1) if m else ed_sig_raw
    dmg_name = dmg_path.name
    dmg_size = dmg_path.stat().st_size
    full_version = _read_full_version()  # "1.0.51+52"
    full_version_enc = full_version.replace("+", "%2B")
    build_number = full_version.split("+")[1] if "+" in full_version else "0"
    # 下载 URL 用短版本号（GitHub Release tag 不含 build number）
    download_url = f"https://github.com/{GITHUB_REPO}/releases/download/v{version}/{dmg_name}"
    pub_date = datetime.now(timezone.utc).strftime("%a, %d %b %Y %H:%M:%S %z")

    release_notes = _release_notes_plain(version)

    return f"""    <item>
      <title>知几桌面端 v{version}</title>
      <description><![CDATA[{release_notes}]]></description>
      <pubDate>{pub_date}</pubDate>
      <enclosure
        url="{download_url}"
        sparkle:version="{build_number}"
        sparkle:shortVersionString="{version}"
        sparkle:edSignature="{ed_sig}"
        length="{dmg_size}"
        type="application/octet-stream"
      />
    </item>"""


def _update_appcast(appcast_path: Path, entry: str) -> None:
    """将新 item 插入 appcast.xml — 移除同版本旧条目后在 </link> 后插入。"""
    if not appcast_path.exists():
        print(f"⚠️  appcast.xml 不存在: {appcast_path}")
        return

    content = appcast_path.read_text()

    # 提取新条目的 shortVersionString 用于去重
    ver_match = re.search(r'sparkle:shortVersionString="([^"]+)"', entry)
    if ver_match:
        new_ver = ver_match.group(1)
        # 移除已有同版本 <item>...</item> 块
        pattern = re.compile(
            r'\n    <item>.*?sparkle:shortVersionString="' + re.escape(new_ver) + r'".*?</item>',
            re.DOTALL,
        )
        content = pattern.sub("", content)

    # 在 channel 元数据后、第一个 <item> 前插入
    marker = "</link>"
    new_content = content.replace(marker, f"{marker}\n{entry}", 1)
    appcast_path.write_text(new_content)
    print(f"📡 appcast.xml 已更新")


def _generate_release_notes(version: str) -> str:
    """从 desktop/changelog.json 读取版本说明，生成 Markdown 正文（GitHub Release 用）。"""
    changelog_path = DESKTOP_DIR / "changelog.json"
    if not changelog_path.exists():
        return f"知几桌面端 v{version}"

    data = json.loads(changelog_path.read_text())
    for v in data.get("versions", []):
        if v.get("version") == version:
            title = v.get("title", "")
            sections = v.get("sections", [])
            lines = [f"## ✨ 知几 v{version} — {title}", ""]
            for sec in sections:
                icon = sec.get("icon", "")
                label = sec.get("label", "")
                lines.append(f"### {icon} {label}")
                lines.append("")
                for item in sec.get("items", []):
                    lines.append(f"- {item}")
                lines.append("")
            lines.append("## 📦 桌面端更新")
            lines.append("")
            lines.append(f"- DMG: `zhiji_{version}.dmg`")
            lines.append("- 自动更新: Sparkle 检测 appcast.xml → EdDSA 签名验证 → DMG 覆盖安装")
            return "\n".join(lines)
    return f"知几桌面端 v{version}"


def _release_notes_plain(version: str) -> str:
    """生成 HTML 版本说明（Sparkle appcast CDATA 用，带 &lt;br&gt; 换行）。"""
    changelog_path = DESKTOP_DIR / "changelog.json"
    if not changelog_path.exists():
        return f"知几桌面端 v{version}"

    data = json.loads(changelog_path.read_text())
    for v in data.get("versions", []):
        if v.get("version") == version:
            title = v.get("title", "")
            sections = v.get("sections", [])
            parts = [f"知几 v{version} — {title}"]
            for sec in sections:
                label = sec.get("label", "")
                parts.append(f"<br><br><b>▸ {label}</b>")
                for item in sec.get("items", []):
                    parts.append(f"<br>&nbsp;&nbsp;&nbsp;&nbsp;{item}")
            return "".join(parts)
    return f"知几桌面端 v{version}"


def main():
    parser = argparse.ArgumentParser(description="知几桌面端发布构建")
    parser.add_argument("--skip-build", action="store_true", help="跳过编译（使用已有产物）")
    parser.add_argument("--version", default=None, help="指定版本号（默认读取 pubspec.yaml）")
    args = parser.parse_args()

    version = args.version or _read_desktop_version()
    print(f"📦 知几桌面端 v{version} 发布构建")
    print(f"   项目根: {PROJECT_ROOT}")
    print()

    # 1. 编译
    if not args.skip_build:
        if not build_flutter():
            sys.exit(1)
        # 签名 .app（Sparkle 要求证书签名，不能用 ad-hoc）
        print("🔐 签名 .app: Zhiji")
        subprocess.run(
            ["codesign", "--deep", "--force", "--sign", "Zhiji", str(FLUTTER_APP)],
            capture_output=True, check=True, timeout=60,
        )
        print("✅ .app 签名完成")
    elif not APP_BINARY.exists():
        sys.exit(f"❌ 编译产物不存在: {APP_BINARY}")
    else:
        print("⏭️  跳过编译")

    # 2. 哈希
    app_hash = _shasum(APP_BINARY)
    print(f"🔑 App SHA256: {app_hash[:16]}...")

    # 3. 打包 DMG
    dmg_path = build_dmg(version)

    # 签名 DMG
    print("🔐 签名 DMG: Zhiji")
    subprocess.run(
        ["codesign", "--force", "--sign", "Zhiji", str(dmg_path)],
        capture_output=True, check=True, timeout=30,
    )
    print("✅ DMG 签名完成")

    # 4. 生成/更新 Sparkle appcast
    appcast_path = PROJECT_ROOT / "appcast.xml"
    appcast_entry = _generate_appcast_entry(version, dmg_path)
    if appcast_entry:
        _update_appcast(appcast_path, appcast_entry)
        print(f"📡 appcast: {appcast_path}")

    # 5. 总结
    print()
    print("━" * 50)
    print(f"✅ 发布包就绪: {RELEASE_DIR}")
    print(f"   安装包: {dmg_path.name} ({dmg_path.stat().st_size / 1024 / 1024:.1f} MB)")
    print()

    # 生成 Release 说明
    notes = _generate_release_notes(version)
    notes_path = RELEASE_DIR / "RELEASE_NOTES.md"
    notes_path.write_text(notes)
    print("📝 Release 说明 (来自 changelog.json):")
    print(notes)
    print()

    print("上传到 GitHub Release:")
    print(f"  gh release create v{version} \\\\")
    print(f"    {dmg_path} \\\\")
    print(f"  --notes-file {notes_path}")
    print("━" * 50)


if __name__ == "__main__":
    main()
