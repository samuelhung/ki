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
import os
import re
import shutil
import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ET
from datetime import UTC, datetime
from pathlib import Path

try:
    from scripts.release_contract import (
        SPARKLE_NS,
        ReleaseContract,
        ReleaseContractError,
        load_release_contract,
        validate_candidate_appcast,
        validate_sparkle_signature,
    )
    from scripts.release_preflight import run_preflight
except ModuleNotFoundError:
    from release_contract import (  # type: ignore[no-redef]
        SPARKLE_NS,
        ReleaseContract,
        ReleaseContractError,
        load_release_contract,
        validate_candidate_appcast,
        validate_sparkle_signature,
    )
    from release_preflight import run_preflight  # type: ignore[no-redef]

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DESKTOP_DIR = PROJECT_ROOT / "desktop"
BUILD_DIR = DESKTOP_DIR / "build"
RELEASE_DIR = BUILD_DIR / "release"
FLUTTER_APP = BUILD_DIR / "macos" / "Build" / "Products" / "Release" / "知几.app"
APP_BINARY = FLUTTER_APP / "Contents" / "Frameworks" / "App.framework" / "Versions" / "A" / "App"

class ReleaseBuildError(RuntimeError):
    pass


def _shasum(path: Path) -> str:
    """计算文件 SHA256。"""
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()


def write_release_metadata(
    directory: Path,
    contract: ReleaseContract,
    *,
    candidate_appcast: Path,
    commit: str,
    tools: dict[str, str],
    built_at: str | None = None,
) -> None:
    if not re.fullmatch(r"[0-9a-f]{40}", commit):
        raise ReleaseBuildError("release provenance requires a full Git SHA")
    if not tools:
        raise ReleaseBuildError("release provenance requires tool versions")
    if not candidate_appcast.is_file():
        raise ReleaseBuildError("release provenance requires a candidate Appcast")
    for name in (contract.dmg_name, contract.wheel_name, contract.sbom_name):
        if not (directory / name).is_file():
            raise ReleaseBuildError(f"release artifact is missing: {name}")
    provenance = {
        "schema_version": 1,
        "tag": contract.tag,
        "version": contract.version,
        "build": contract.build,
        "commit": commit,
        "built_at": built_at or datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        "tools": tools,
        "candidate_appcast_sha256": _shasum(candidate_appcast),
    }
    (directory / contract.provenance_name).write_text(
        json.dumps(provenance, ensure_ascii=True, indent=2) + "\n",
        encoding="utf-8",
    )
    targets = (contract.dmg_name, contract.wheel_name, contract.sbom_name, contract.provenance_name)
    (directory / "SHA256SUMS").write_text(
        "".join(f"{_shasum(directory / name)}  {name}\n" for name in sorted(targets)),
        encoding="ascii",
    )


def _tool_output(*command: str) -> str:
    return subprocess.check_output(command, text=True).strip().splitlines()[0]


def collect_tool_versions(syft: Path) -> dict[str, str]:
    return {
        "python": sys.version.split()[0],
        "flutter": _tool_output("flutter", "--version"),
        "node": _tool_output("node", "--version"),
        "npm": _tool_output("npm", "--version"),
        "uv": _tool_output("uv", "--version"),
        "syft": _tool_output(str(syft), "version"),
    }


def verify_release_build_checkout(
    root: Path,
    *,
    check_output=subprocess.check_output,
) -> str:
    def git(*args: str) -> str:
        return check_output(["git", *args], cwd=root, text=True).strip()

    if git("branch", "--show-current") != "main":
        raise ReleaseBuildError("release build must run from main")
    if git("status", "--porcelain"):
        raise ReleaseBuildError("release build requires a clean checkout")
    commit = git("rev-parse", "HEAD")
    if not re.fullmatch(r"[0-9a-f]{40}", commit):
        raise ReleaseBuildError("release build requires a full Git commit")
    return commit


def require_fresh_release_build(*, skip_build: bool) -> None:
    if skip_build:
        raise ReleaseBuildError("--skip-build is disabled for verifiable releases")


def generate_release_sbom(
    syft: Path,
    artifacts: list[Path],
    output: Path,
    *,
    run=subprocess.run,
) -> None:
    if not syft.is_file():
        raise ReleaseBuildError(
            f"verified Syft is missing: {syft}; run scripts/install_supply_chain_tools.sh first"
        )
    if not artifacts or any(not artifact.is_file() for artifact in artifacts):
        raise ReleaseBuildError("release SBOM inputs are missing")
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="zhiji-release-sbom-", dir=output.parent) as temporary:
        source = Path(temporary)
        for artifact in artifacts:
            destination = source / artifact.name
            try:
                os.link(artifact, destination)
            except OSError:
                shutil.copy2(artifact, destination)
        environment = os.environ.copy()
        environment["SYFT_CHECK_FOR_APP_UPDATE"] = "false"
        run(
            [
                str(syft),
                "scan",
                f"dir:{source}",
                "--output",
                f"cyclonedx-json={output}",
            ],
            check=True,
            env=environment,
        )
    try:
        payload = json.loads(output.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        output.unlink(missing_ok=True)
        raise ReleaseBuildError("Syft did not produce valid JSON") from exc
    if (
        payload.get("bomFormat") != "CycloneDX"
        or not payload.get("specVersion")
        or not isinstance(payload.get("components"), list)
        or not payload["components"]
    ):
        output.unlink(missing_ok=True)
        raise ReleaseBuildError("Syft did not produce a populated CycloneDX SBOM")
    artifact_names = {artifact.name for artifact in artifacts}
    components = [
        component
        for component in payload["components"]
        if not (component.get("type") == "file" and component.get("name") in artifact_names)
    ]
    components.extend(
        {
            "type": "file",
            "name": artifact.name,
            "hashes": [{"alg": "SHA-256", "content": _shasum(artifact)}],
        }
        for artifact in artifacts
    )
    payload["components"] = components
    output.write_text(json.dumps(payload, ensure_ascii=True, indent=2) + "\n", encoding="utf-8")


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


def parse_sparkle_signature(output: str, *, expected_length: int) -> str:
    match = re.search(r'sparkle:edSignature="([^"]+)"\s+length="(\d+)"', output.strip())
    if not match:
        raise ReleaseBuildError("sign_update returned malformed output")
    if int(match.group(2)) != expected_length:
        raise ReleaseBuildError("sign_update length does not match DMG")
    signature = match.group(1)
    try:
        validate_sparkle_signature(signature)
    except ReleaseContractError as exc:
        raise ReleaseBuildError("sign_update signature is invalid") from exc
    return signature


def sign_sparkle_update(
    sign_update: Path,
    dmg_path: Path,
    *,
    run=subprocess.run,
) -> str:
    if not sign_update.is_file():
        raise ReleaseBuildError(f"Sparkle sign_update is missing: {sign_update}")
    result = run(
        [str(sign_update), str(dmg_path)],
        capture_output=True,
        text=True,
        timeout=30,
    )
    if result.returncode != 0:
        detail = (result.stderr or "unknown signing error").strip()
        raise ReleaseBuildError(f"Sparkle sign_update failed: {detail}")
    return parse_sparkle_signature(result.stdout, expected_length=dmg_path.stat().st_size)


def write_candidate_appcast(
    live_appcast: Path,
    candidate_path: Path,
    contract: ReleaseContract,
    signature: str,
    *,
    dmg_size: int,
    pub_date: str | None = None,
) -> None:
    ET.register_namespace("sparkle", SPARKLE_NS)
    tree = ET.parse(live_appcast)
    channel = tree.getroot().find("channel")
    if channel is None:
        raise ReleaseBuildError("live appcast has no channel")
    for existing in list(channel.findall("item")):
        enclosure = existing.find("enclosure")
        if enclosure is not None and enclosure.get(f"{{{SPARKLE_NS}}}shortVersionString") == contract.version:
            channel.remove(existing)

    item = ET.Element("item")
    ET.SubElement(item, "title").text = f"知几桌面端 v{contract.version}"
    ET.SubElement(item, "description").text = _release_notes_plain(contract.version)
    ET.SubElement(item, "pubDate").text = pub_date or datetime.now(UTC).strftime(
        "%a, %d %b %Y %H:%M:%S %z"
    )
    ET.SubElement(
        item,
        "enclosure",
        {
            "url": contract.download_url,
            f"{{{SPARKLE_NS}}}version": str(contract.build),
            f"{{{SPARKLE_NS}}}shortVersionString": contract.version,
            f"{{{SPARKLE_NS}}}edSignature": signature,
            "length": str(dmg_size),
            "type": "application/octet-stream",
        },
    )
    insert_at = next((index for index, child in enumerate(channel) if child.tag == "item"), len(channel))
    channel.insert(insert_at, item)
    candidate_path.parent.mkdir(parents=True, exist_ok=True)
    tree.write(candidate_path, encoding="utf-8", xml_declaration=True)
    validate_candidate_appcast(candidate_path, contract)


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
    parser.add_argument("tag", help="规范发布标签，例如 v2.0.0+90")
    parser.add_argument("--skip-build", action="store_true", help="跳过编译（使用已有产物）")
    args = parser.parse_args()

    commit = verify_release_build_checkout(PROJECT_ROOT)
    require_fresh_release_build(skip_build=args.skip_build)
    contract = load_release_contract(PROJECT_ROOT, args.tag)
    version = contract.version
    print(f"📦 知几桌面端 {contract.tag} 发布构建")
    print(f"   项目根: {PROJECT_ROOT}")
    print()

    # 1. 编译
    if not build_flutter():
        sys.exit(1)

    # 签名 .app（Sparkle 要求证书签名，不能用 ad-hoc）
    # ⚠️ 必须每次执行：flutter build 只产 adhoc，--skip-build 时也不会自动签名
    print("🔐 签名 .app: Zhiji")
    subprocess.run(
        ["codesign", "--deep", "--force", "--sign", "Zhiji", str(FLUTTER_APP)],
        capture_output=True, check=True, timeout=60,
    )
    subprocess.run(
        ["codesign", "--verify", "--deep", "--strict", str(FLUTTER_APP)],
        capture_output=True, check=True, timeout=60,
    )
    print("✅ .app 签名完成")

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
    subprocess.run(
        ["codesign", "--verify", "--strict", str(dmg_path)],
        capture_output=True, check=True, timeout=30,
    )
    print("✅ DMG 签名完成")

    # 4. 只生成候选 Appcast。正式 feed 必须等远端制品回读校验后才能发布。
    sign_update = DESKTOP_DIR / "macos" / "Pods" / "Sparkle" / "bin" / "sign_update"
    sparkle_signature = sign_sparkle_update(sign_update, dmg_path)
    candidate_appcast = RELEASE_DIR / contract.candidate_appcast_name
    write_candidate_appcast(
        PROJECT_ROOT / "appcast.xml",
        candidate_appcast,
        contract,
        sparkle_signature,
        dmg_size=dmg_path.stat().st_size,
    )
    print(f"📡 候选 appcast: {candidate_appcast}")

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

    subprocess.run(
        [sys.executable, str(PROJECT_ROOT / "scripts" / "build_backend_wheel.py"), "--outdir", str(RELEASE_DIR)],
        cwd=PROJECT_ROOT,
        check=True,
    )
    if not (RELEASE_DIR / contract.wheel_name).is_file():
        raise ReleaseBuildError(f"backend wheel name does not match release contract: {contract.wheel_name}")
    syft = PROJECT_ROOT / ".tools" / "bin" / "syft"
    generate_release_sbom(
        syft,
        [dmg_path, RELEASE_DIR / contract.wheel_name],
        RELEASE_DIR / contract.sbom_name,
    )
    write_release_metadata(
        RELEASE_DIR,
        contract,
        candidate_appcast=candidate_appcast,
        commit=commit,
        tools=collect_tool_versions(syft),
    )
    run_preflight(
        PROJECT_ROOT,
        contract.tag,
        RELEASE_DIR,
        candidate_appcast,
        expected_commit=commit,
    )
    print(f"✅ 完整发布候选已通过 preflight: {contract.tag}")
    print("━" * 50)


if __name__ == "__main__":
    main()
