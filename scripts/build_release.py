#!/usr/bin/env python3
"""
知几桌面端发布构建脚本

功能:
  1. 编译 Flutter macOS
  2. 生成 DMG 安装包
  3. 计算 SHA256 哈希
  4. 对比上一版本生成 bsdiff 增量补丁
  5. 生成 manifest.json 更新清单

输出: build/release/
  ├── zhiji_desktop_<version>_universal.dmg   安装包
  ├── manifest.json                             更新清单
  └── patch_v<old>_v<new>.bsdiff                增量补丁（如非首次发布）

依赖: flutter, hdiutil, bsdiff, bspatch
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from urllib.request import urlopen, Request

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


def download_file(url: str, dest: Path) -> bool:
    """下载文件到指定路径。"""
    try:
        req = Request(url)
        req.add_header("Accept", "application/octet-stream")
        req.add_header("User-Agent", "zhiji-build")
        with urlopen(req, timeout=300) as resp:
            with open(dest, "wb") as f:
                shutil.copyfileobj(resp, f)
        return True
    except Exception as e:
        print(f"⚠️  下载失败: {e}")
        return False


def fetch_previous_binary(prev_version: str) -> Path | None:
    """从 GitHub Release 下载上一版本的 DMG 并提取 App 二进制。"""
    tmpdir = Path(tempfile.mkdtemp(prefix="zhiji_prev_"))
    dmg_path = tmpdir / f"zhiji_desktop_{prev_version}_universal.dmg"

    url = f"https://github.com/{GITHUB_REPO}/releases/download/v{prev_version}/zhiji_desktop_{prev_version}_universal.dmg"
    if not download_file(url, dmg_path):
        shutil.rmtree(tmpdir, ignore_errors=True)
        return None

    # 挂载 DMG
    mount_point = tmpdir / "mount"
    mount_point.mkdir(exist_ok=True)
    subprocess.run(
        ["hdiutil", "attach", str(dmg_path), "-mountpoint", str(mount_point), "-nobrowse"],
        capture_output=True, timeout=30, check=True,
    )

    prev_binary_old = mount_point / "zhiji_desktop.app" / "Contents" / "Frameworks" / "App.framework" / "Versions" / "A" / "App"
    prev_binary_new = mount_point / "知几.app" / "Contents" / "Frameworks" / "App.framework" / "Versions" / "A" / "App"

    prev_binary = prev_binary_old if prev_binary_old.exists() else prev_binary_new

    if not prev_binary.exists():
        print(f"⚠️  DMG 中找不到 App 二进制")
        subprocess.run(["hdiutil", "detach", str(mount_point)], capture_output=True)
        shutil.rmtree(tmpdir, ignore_errors=True)
        return None

    # 复制出来
    result_path = tmpdir / "App.prev"
    shutil.copy2(prev_binary, result_path)

    # 卸载
    subprocess.run(["hdiutil", "detach", str(mount_point)], capture_output=True)

    return result_path


def generate_patches(version: str, current_hash: str) -> list[dict]:
    """对比上一版本或更早版本，生成 bsdiff 补丁列表。"""
    try:
        releases_url = f"{GITHUB_API}/releases"
        req = Request(releases_url)
        req.add_header("Accept", "application/vnd.github+json")
        req.add_header("User-Agent", "zhiji-build")
        with urlopen(req, timeout=15) as resp:
            releases = json.loads(resp.read())
    except Exception as e:
        print(f"⚠️  无法获取 Release 列表: {e}")
        return []

    patches = []

    # 对比最近 3 个版本
    for release in releases[:3]:
        tag = release.get("tag_name", "").lstrip("v")
        if not tag or tag == version:
            continue

        print(f"🔍 对比版本 v{tag}...")
        prev_bin = fetch_previous_binary(tag)
        if prev_bin is None:
            continue

        prev_hash = _shasum(prev_bin)
        if prev_hash == current_hash:
            print(f"  哈希相同，跳过")
            shutil.rmtree(prev_bin.parent, ignore_errors=True)
            continue

        # 生成 bsdiff
        patch_name = f"patch_v{tag}_v{version}.bsdiff"
        patch_path = RELEASE_DIR / patch_name

        print(f"  bsdiff {prev_bin} → {patch_name}")
        result = subprocess.run(
            ["bsdiff", str(prev_bin), str(APP_BINARY), str(patch_path)],
            capture_output=True, timeout=300,
        )

        shutil.rmtree(prev_bin.parent, ignore_errors=True)

        if result.returncode == 0 and patch_path.exists():
            patch_size_kb = patch_path.stat().st_size / 1024
            patches.append({
                "from_version": tag,
                "url": patch_name,
                "size": patch_path.stat().st_size,
            })
            print(f"  ✅ 补丁: {patch_name} ({patch_size_kb:.0f} KB)")
        else:
            print(f"  ⚠️  bsdiff 失败")

        break  # 只生成最近一个版本的补丁

    return patches


def generate_manifest(version: str, app_hash: str, dmg_path: Path, patches: list[dict]) -> Path:
    """生成 manifest.json。"""
    manifest = {
        "version": version,
        "app_hash": app_hash,
        "dmg_url": dmg_path.name,
        "dmg_size": dmg_path.stat().st_size,
        "dmg_sha256": _shasum(dmg_path),
        "patches": patches,
        "notes": f"知几桌面端 v{version}",
    }

    manifest_path = RELEASE_DIR / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False))
    print(f"📋 manifest.json 已生成")
    return manifest_path


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

    release_notes = _generate_release_notes(version)

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
    """从 desktop/changelog.json 读取版本说明，生成 GitHub Release 正文。"""
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

    # 4. 生成增量补丁
    patches = generate_patches(version, app_hash)

    # 5. 生成 manifest
    manifest_path = generate_manifest(version, app_hash, dmg_path, patches)

    # 5.5 复制安装脚本到发布目录
    install_script_src = PROJECT_ROOT / "scripts" / "install_helper.sh"
    if install_script_src.exists():
        install_script_dst = RELEASE_DIR / "install_helper.sh"
        shutil.copy2(install_script_src, install_script_dst)
        print(f"🔧 安装脚本: install_helper.sh")
    else:
        install_script_dst = None
        print(f"⚠️  安装脚本不存在: {install_script_src}")

    # 6. 生成/更新 Sparkle appcast
    appcast_path = PROJECT_ROOT / "appcast.xml"
    appcast_entry = _generate_appcast_entry(version, dmg_path)
    if appcast_entry:
        _update_appcast(appcast_path, appcast_entry)
        print(f"📡 appcast: {appcast_path}")

    # 7. 总结
    print()
    print("━" * 50)
    print(f"✅ 发布包就绪: {RELEASE_DIR}")
    print(f"   安装包: {dmg_path.name} ({dmg_path.stat().st_size / 1024 / 1024:.1f} MB)")
    print(f"   清单:   manifest.json")
    if install_script_dst:
        print(f"   安装脚本: install_helper.sh")
    if patches:
        for p in patches:
            print(f"   补丁:   {p['url']} ({p['size'] / 1024:.0f} KB)")
    else:
        print(f"   补丁:   (首次发布，无增量补丁)")
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
    print(f"    {manifest_path} \\\\")
    if install_script_dst:
        print(f"    {install_script_dst} \\\\")
    if patches:
        for p in patches:
            print(f"    {RELEASE_DIR / p['url']} \\\\")
    print(f"  --notes-file {notes_path}")
    print("━" * 50)


if __name__ == "__main__":
    main()
