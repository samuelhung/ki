#!/usr/bin/env python3
"""知几桌面端发布构建脚本 (Sparkle 版)。

流程:
1. flutter build macos
2. 用自签证书 codesign .app
3. 创建 DMG（纯 ASCII 文件名，防 GitHub 吞中文）
4. codesign DMG
5. 用 Sparkle sign_update 签名 DMG → 生成 appcast.xml
6. 输出到 desktop/build/release/
"""
import hashlib
import re
import subprocess
import sys
from pathlib import Path
from datetime import datetime, timezone

PROJECT = Path(__file__).resolve().parent.parent
DESKTOP = PROJECT
BUILD_DIR = DESKTOP / "build" / "macos" / "Build" / "Products" / "Release"
APP_PATH = BUILD_DIR / "知几.app"
RELEASE_DIR = DESKTOP / "build" / "release"
APPCAST_PATH = RELEASE_DIR / "appcast.xml"
SIGN_UPDATE = DESKTOP / "macos" / "Sparkle" / "bin" / "sign_update"
CERT_NAME = "Zhiji"
GITHUB_REPO = "samuelhung/ki"


def get_version() -> tuple[str, str]:
    """从 pubspec.yaml 读取版本，返回 (version_name, build_number)。"""
    content = (DESKTOP / "pubspec.yaml").read_text()
    for line in content.splitlines():
        if line.strip().startswith("version:"):
            ver = line.split(":")[1].strip()
            if "+" in ver:
                name, build = ver.split("+", 1)
                return name, build
            return ver, "1"
    return "0.1.0", "1"


def sign_app():
    print("🔐 签名 .app ...")
    subprocess.run(
        ["codesign", "--deep", "--force", "--sign", CERT_NAME, str(APP_PATH)],
        check=True, timeout=60,
    )
    print("   ✅ 已签名 (Zhiji)")


def create_dmg(version_name: str) -> Path:
    """创建 DMG，纯 ASCII 文件名。"""
    dmg_name = f"zhiji_{version_name}.dmg"
    dmg_path = RELEASE_DIR / dmg_name
    dmg_path.parent.mkdir(parents=True, exist_ok=True)

    print(f"💿 创建 DMG: {dmg_name}")

    tmp_dmg = RELEASE_DIR / "tmp.dmg"
    subprocess.run([
        "hdiutil", "create", "-fs", "HFS+",
        "-srcfolder", str(APP_PATH),
        "-volname", f"知几 {version_name}",
        "-size", "200m",
        str(tmp_dmg),
    ], check=True, timeout=120)

    if dmg_path.exists():
        dmg_path.unlink()
    subprocess.run([
        "hdiutil", "convert", str(tmp_dmg),
        "-format", "UDZO",
        "-imagekey", "zlib-level=9",
        "-o", str(dmg_path),
    ], check=True, timeout=120)
    tmp_dmg.unlink()

    print(f"   ✅ DMG 就绪: {dmg_path.name}")
    return dmg_path


def sign_dmg(dmg_path: Path):
    print("🔐 签名 DMG ...")
    subprocess.run(
        ["codesign", "--force", "--sign", CERT_NAME, str(dmg_path)],
        check=True, timeout=30,
    )
    print("   ✅ DMG 已签名")


def generate_appcast(version_name: str, build_number: str, dmg_path: Path):
    """生成/更新 appcast.xml。"""
    dmg_size = dmg_path.stat().st_size

    # GitHub release tag: v{version_name}+{build_number}
    full_ver = f"{version_name}+{build_number}"
    tag = f"v{full_ver}"
    dmg_url = f"https://github.com/{GITHUB_REPO}/releases/download/{tag}/{dmg_path.name}"

    # Sparkle 签名
    result = subprocess.run(
        [str(SIGN_UPDATE), str(dmg_path)],
        capture_output=True, text=True, timeout=30,
    )
    sig_match = re.search(r'sparkle:edSignature="([^"]+)"', result.stdout)
    if not sig_match:
        print(f"   ❌ 无法解析签名: {result.stdout}")
        sys.exit(1)
    ed_sig = sig_match.group(1)
    print(f"   Sparkle 签名: {ed_sig[:40]}...")

    pub_date = datetime.now(timezone.utc).strftime("%a, %d %b %Y %H:%M:%S GMT")

    # sparkle:version 用 build number（匹配 CFBundleVersion）
    # sparkle:shortVersionString 用版本名（显示用）
    item_xml = f"""    <item>
        <title>知几 {version_name}</title>
        <sparkle:releaseNotesLink xml:lang="zh">
            https://github.com/{GITHUB_REPO}/releases/tag/{tag}
        </sparkle:releaseNotesLink>
        <pubDate>{pub_date}</pubDate>
        <enclosure
            url="{dmg_url}"
            sparkle:version="{build_number}"
            sparkle:shortVersionString="{version_name}"
            length="{dmg_size}"
            type="application/octet-stream"
            sparkle:edSignature="{ed_sig}"
        />
    </item>
"""

    if APPCAST_PATH.exists():
        content = APPCAST_PATH.read_text()
        insert_pos = content.find("</channel>")
        if insert_pos == -1:
            insert_pos = content.find("</rss>")
        new_content = content[:insert_pos] + "\n" + item_xml + content[insert_pos:]
    else:
        new_content = f"""<?xml version="1.0" encoding="utf-8"?>
<rss version="2.0"
     xmlns:sparkle="http://www.andymatuschak.org/xml-namespaces/sparkle"
     xmlns:dc="http://purl.org/dc/elements/1.1/">
    <channel>
        <title>知几更新</title>
        <description>知几桌面端自动更新通道</description>
        <language>zh</language>
        <link>https://github.com/{GITHUB_REPO}/releases</link>
{item_xml}
    </channel>
</rss>
"""

    APPCAST_PATH.write_text(new_content)
    print(f"   ✅ appcast.xml 已更新: {APPCAST_PATH}")


def build_release():
    version_name, build_number = get_version()
    full_ver = f"{version_name}+{build_number}"
    tag = f"v{full_ver}"
    print(f"📦 知几桌面端 v{version_name} (build {build_number})\n")

    if not APP_PATH.exists():
        print(f"❌ 找不到 {APP_PATH}，先运行 flutter build macos")
        sys.exit(1)

    sign_app()
    dmg_path = create_dmg(version_name)
    sign_dmg(dmg_path)
    generate_appcast(version_name, build_number, dmg_path)

    dmg_size_mb = dmg_path.stat().st_size / 1024 / 1024
    print(f"\n📋 发布清单:")
    print(f"   版本: {full_ver}")
    print(f"   DMG:  {dmg_path.name} ({dmg_size_mb:.1f} MB)")
    print(f"   Appcast: appcast.xml")
    print(f"\n   上传 {dmg_path.name} + appcast.xml 至 GitHub Release {tag}")


if __name__ == "__main__":
    build_release()
