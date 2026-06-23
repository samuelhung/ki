#!/usr/bin/env python3
"""知几桌面端发布构建脚本。

流程:
1. flutter build macos
2. 计算 App.framework/App 的 SHA256
3. 如果存在上次构建，生成 bsdiff 增量补丁
4. 生成 manifest.json（版本、哈希、补丁信息）
5. 输出到 desktop/build/release/
"""
import hashlib
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
from datetime import datetime, timezone

PROJECT = Path(__file__).resolve().parent.parent
DESKTOP = PROJECT
BUILD_DIR = DESKTOP / "build" / "macos" / "Build" / "Products" / "Release"
APP_PATH = BUILD_DIR / "zhiji_desktop.app"
FRAMEWORK_APP = APP_PATH / "Contents" / "Frameworks" / "App.framework" / "Versions" / "A" / "App"
RELEASE_DIR = DESKTOP / "build" / "release"
MANIFEST_PATH = RELEASE_DIR / "manifest.json"
PREV_MANIFEST = RELEASE_DIR / "manifest.prev.json"
VERSION_FILE = DESKTOP / "pubspec.yaml"


def get_version() -> str:
    """从 pubspec.yaml 读取版本。"""
    content = (DESKTOP / "pubspec.yaml").read_text()
    for line in content.splitlines():
        if line.strip().startswith("version:"):
            return line.split(":")[1].strip()
    return "0.1.0"


def sha256(path: Path) -> str:
    """计算文件 SHA256。"""
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while chunk := f.read(8192):
            h.update(chunk)
    return h.hexdigest()


def build_release():
    version = get_version()
    print(f"📦 知几桌面端 {version} 发布构建")

    # 1. 确保编译产物存在
    if not FRAMEWORK_APP.exists():
        print("❌ 找不到 App.framework/App，先运行 flutter build macos")
        sys.exit(1)

    app_hash = sha256(FRAMEWORK_APP)
    app_size = FRAMEWORK_APP.stat().st_size
    print(f"   App.framework/App: {app_hash[:16]}... ({app_size / 1024 / 1024:.1f} MB)")

    # 2. 创建 release 目录
    RELEASE_DIR.mkdir(parents=True, exist_ok=True)

    # 3. 加载上次 manifest
    prev = {}
    if PREV_MANIFEST.exists():
        prev = json.loads(PREV_MANIFEST.read_text())

    # 4. 生成增量补丁
    patches = []
    prev_hash = prev.get("app_hash", "")
    if prev_hash and prev_hash != app_hash:
        # 找上次的 App 文件
        prev_app = RELEASE_DIR / f"App.{prev_hash[:16]}.bin"
        if prev_app.exists():
            patch_file = RELEASE_DIR / f"patch_{prev_hash[:8]}_{app_hash[:8]}.bsdiff"
            print(f"   ⚡ 生成增量补丁: {patch_file.name}")
            subprocess.run(
                ["bsdiff", str(prev_app), str(FRAMEWORK_APP), str(patch_file)],
                check=True, timeout=60,
            )
            patch_size = patch_file.stat().st_size
            patches.append({
                "from_hash": prev_hash,
                "to_hash": app_hash,
                "url": f"patches/{patch_file.name}",
                "size": patch_size,
                "size_mb": round(patch_size / 1024 / 1024, 2),
            })
            print(f"      补丁大小: {patch_size / 1024 / 1024:.2f} MB")

    # 5. 保存当前 App 副本（供下次 diff）
    backup_app = RELEASE_DIR / f"App.{app_hash[:16]}.bin"
    shutil.copy2(FRAMEWORK_APP, backup_app)

    # 6. 生成 manifest
    manifest = {
        "version": version,
        "app_hash": app_hash,
        "app_size": app_size,
        "app_size_mb": round(app_size / 1024 / 1024, 2),
        "built_at": datetime.now(timezone.utc).isoformat(),
        "platform": "macos",
        "arch": "universal",  # x86_64 + arm64
        "patches": patches,
        "full_download": {
            "url": "",
            "size_mb": round((APP_PATH.stat().st_size if hasattr(APP_PATH, 'stat') else 0) / 1024 / 1024, 2) if APP_PATH.exists() else 0,
        },
    }

    manifest_path = RELEASE_DIR / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False))
    print(f"✅ manifest.json 已生成: {manifest_path}")

    # 7. 更新 prev manifest
    PREV_MANIFEST.write_text(json.dumps(manifest, indent=2, ensure_ascii=False))

    print(f"\n📋 发布清单:")
    print(f"   版本: {version}")
    print(f"   哈希: {app_hash[:16]}")
    print(f"   补丁: {len(patches)} 个")
    if patches:
        print(f"   增量: {patches[0]['size_mb']} MB")
    print(f"\n   上传至 GitHub Release 或静态服务器即可。")


if __name__ == "__main__":
    build_release()
