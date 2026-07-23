#!/usr/bin/env python3
"""Release naming and integrity contract shared by build and publish tooling."""

from __future__ import annotations

import hashlib
import json
import plistlib
import re
import tomllib
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import quote


TAG_PATTERN = re.compile(r"^v(?P<version>\d+\.\d+\.\d+)\+(?P<build>[1-9]\d*)$")
BACKEND_VERSION_PATTERN = re.compile(r'^__version__\s*=\s*"([^"]+)"', re.MULTILINE)
PUBSPEC_VERSION_PATTERN = re.compile(r"^version:\s*([^+\s]+)\+(\d+)\s*$", re.MULTILINE)
SPARKLE_NS = "http://www.andymatuschak.org/xml-namespaces/sparkle"


class ReleaseContractError(ValueError):
    pass


@dataclass(frozen=True)
class ReleaseContract:
    version: str
    build: int
    tag: str

    @property
    def dmg_name(self) -> str:
        return f"zhiji_{self.version}.dmg"

    @property
    def wheel_name(self) -> str:
        normalized = self.version.replace("-", "_")
        return f"zhiji_backend-{normalized}-py3-none-any.whl"

    @property
    def sbom_name(self) -> str:
        return f"zhiji_{self.version}+{self.build}.cdx.json"

    @property
    def provenance_name(self) -> str:
        return f"zhiji_{self.version}+{self.build}.provenance.json"

    @property
    def candidate_appcast_name(self) -> str:
        return f"appcast-{self.version}+{self.build}.candidate.xml"

    @property
    def download_url(self) -> str:
        encoded_tag = quote(self.tag, safe="v.")
        return f"https://github.com/samuelhung/ki/releases/download/{encoded_tag}/{self.dmg_name}"


def _read_backend_version(root: Path) -> str:
    source = (root / "src" / "zhiji_backend" / "__init__.py").read_text(encoding="utf-8")
    match = BACKEND_VERSION_PATTERN.search(source)
    if not match:
        raise ReleaseContractError("backend version is missing")
    return match.group(1)


def _read_pubspec_version(root: Path) -> tuple[str, int]:
    source = (root / "desktop" / "pubspec.yaml").read_text(encoding="utf-8")
    match = PUBSPEC_VERSION_PATTERN.search(source)
    if not match:
        raise ReleaseContractError("desktop version must use X.Y.Z+N")
    return match.group(1), int(match.group(2))


def _validate_changelog(root: Path, version: str) -> None:
    payload = json.loads((root / "desktop" / "changelog.json").read_text(encoding="utf-8"))
    versions = payload.get("versions")
    if not isinstance(versions, list) or not versions or versions[0].get("version") != version:
        raise ReleaseContractError(f"changelog latest version must be {version}")


def _validate_info_plist(root: Path) -> None:
    with (root / "desktop" / "macos" / "Runner" / "Info.plist").open("rb") as handle:
        payload = plistlib.load(handle)
    expected = {
        "CFBundleShortVersionString": "$(FLUTTER_BUILD_NAME)",
        "CFBundleVersion": "$(FLUTTER_BUILD_NUMBER)",
        "SUFeedURL": "https://raw.githubusercontent.com/samuelhung/ki/main/appcast.xml",
    }
    for key, value in expected.items():
        if payload.get(key) != value:
            raise ReleaseContractError(f"Info.plist {key} must be {value}")
    public_key = payload.get("SUPublicEDKey")
    if not isinstance(public_key, str) or len(public_key.strip()) < 40:
        raise ReleaseContractError("Info.plist SUPublicEDKey is invalid")


def load_release_contract(root: Path, tag: str) -> ReleaseContract:
    match = TAG_PATTERN.fullmatch(tag)
    if not match:
        raise ReleaseContractError("release tag must use vX.Y.Z+N with a positive build number")

    version = match.group("version")
    build = int(match.group("build"))
    pyproject = tomllib.loads((root / "pyproject.toml").read_text(encoding="utf-8"))
    pyproject_version = pyproject.get("project", {}).get("version")
    backend_version = _read_backend_version(root)
    desktop_version, desktop_build = _read_pubspec_version(root)
    source_versions = {pyproject_version, backend_version, desktop_version, version}
    if source_versions != {version} or desktop_build != build:
        raise ReleaseContractError(
            "version mismatch: "
            f"tag={version}+{build}, pyproject={pyproject_version}, "
            f"backend={backend_version}, desktop={desktop_version}+{desktop_build}"
        )

    _validate_changelog(root, version)
    _validate_info_plist(root)
    return ReleaseContract(version=version, build=build, tag=tag)


def expected_artifact_names(contract: ReleaseContract) -> set[str]:
    return {
        contract.dmg_name,
        contract.wheel_name,
        contract.sbom_name,
        contract.provenance_name,
        "SHA256SUMS",
    }


def validate_candidate_appcast(path: Path, contract: ReleaseContract) -> None:
    try:
        root = ET.parse(path).getroot()
    except (ET.ParseError, OSError) as exc:
        raise ReleaseContractError(f"candidate appcast is invalid: {exc}") from exc
    item = root.find("./channel/item")
    enclosure = item.find("enclosure") if item is not None else None
    if enclosure is None:
        raise ReleaseContractError("candidate appcast must contain a leading enclosure")
    sparkle_version = enclosure.get(f"{{{SPARKLE_NS}}}version")
    short_version = enclosure.get(f"{{{SPARKLE_NS}}}shortVersionString")
    signature = enclosure.get(f"{{{SPARKLE_NS}}}edSignature")
    if short_version != contract.version or sparkle_version != str(contract.build):
        raise ReleaseContractError("candidate appcast version does not match release tag")
    if enclosure.get("url") != contract.download_url:
        raise ReleaseContractError("candidate appcast download URL does not match release tag and DMG")
    if not signature:
        raise ReleaseContractError("candidate appcast is missing Sparkle signature")
    try:
        length = int(enclosure.get("length", "0"))
    except ValueError as exc:
        raise ReleaseContractError("candidate appcast length is invalid") from exc
    if length <= 0:
        raise ReleaseContractError("candidate appcast length is invalid")


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _read_checksums(path: Path) -> dict[str, str]:
    checksums: dict[str, str] = {}
    for line in path.read_text(encoding="ascii").splitlines():
        match = re.fullmatch(r"([0-9a-f]{64})  ([^/]+)", line)
        if not match or match.group(2) in checksums:
            raise ReleaseContractError("SHA256SUMS contains an invalid or duplicate entry")
        checksums[match.group(2)] = match.group(1)
    return checksums


def validate_release_artifacts(directory: Path, contract: ReleaseContract) -> None:
    required = expected_artifact_names(contract)
    missing = sorted(name for name in required if not (directory / name).is_file())
    if missing:
        raise ReleaseContractError(f"release artifacts are missing: {', '.join(missing)}")

    provenance = json.loads((directory / contract.provenance_name).read_text(encoding="utf-8"))
    expected_fields = {
        "schema_version": 1,
        "tag": contract.tag,
        "version": contract.version,
        "build": contract.build,
    }
    for key, value in expected_fields.items():
        if provenance.get(key) != value:
            raise ReleaseContractError(f"provenance {key} does not match release contract")
    if not re.fullmatch(r"[0-9a-f]{40}", str(provenance.get("commit", ""))):
        raise ReleaseContractError("provenance commit must be a full Git SHA")
    if not isinstance(provenance.get("built_at"), str) or not provenance["built_at"].endswith("Z"):
        raise ReleaseContractError("provenance built_at must be UTC")
    if not isinstance(provenance.get("tools"), dict) or not provenance["tools"]:
        raise ReleaseContractError("provenance tools are missing")

    expected_targets = required - {"SHA256SUMS"}
    checksums = _read_checksums(directory / "SHA256SUMS")
    if set(checksums) != expected_targets:
        raise ReleaseContractError("SHA256SUMS entries do not match release artifact set")
    for name, expected in checksums.items():
        if _sha256(directory / name) != expected:
            raise ReleaseContractError(f"checksum mismatch: {name}")
