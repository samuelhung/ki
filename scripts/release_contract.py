#!/usr/bin/env python3
"""Release naming and integrity contract shared by build and publish tooling."""

from __future__ import annotations

import base64
import binascii
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


def validate_candidate_appcast(
    path: Path,
    contract: ReleaseContract,
    *,
    dmg_path: Path | None = None,
) -> None:
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
    validate_sparkle_signature(signature)
    try:
        length = int(enclosure.get("length", "0"))
    except ValueError as exc:
        raise ReleaseContractError("candidate appcast length is invalid") from exc
    if length <= 0:
        raise ReleaseContractError("candidate appcast length is invalid")
    if dmg_path is not None:
        try:
            actual_length = dmg_path.stat().st_size
        except OSError as exc:
            raise ReleaseContractError("candidate appcast DMG is missing") from exc
        if length != actual_length:
            raise ReleaseContractError("candidate appcast length does not match DMG")


def validate_sparkle_signature(signature: str | None) -> None:
    if not signature:
        raise ReleaseContractError("candidate appcast is missing Sparkle signature")
    try:
        decoded = base64.b64decode(signature, validate=True)
    except (ValueError, binascii.Error) as exc:
        raise ReleaseContractError("candidate appcast signature is invalid") from exc
    if len(decoded) != 64:
        raise ReleaseContractError("candidate appcast signature is invalid")


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


def validate_release_artifacts(
    directory: Path,
    contract: ReleaseContract,
    *,
    expected_commit: str | None = None,
) -> None:
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
    if expected_commit is not None and provenance["commit"] != expected_commit:
        raise ReleaseContractError("provenance commit does not match release target")
    if not isinstance(provenance.get("built_at"), str) or not provenance["built_at"].endswith("Z"):
        raise ReleaseContractError("provenance built_at must be UTC")
    if not isinstance(provenance.get("tools"), dict) or not provenance["tools"]:
        raise ReleaseContractError("provenance tools are missing")
    if not re.fullmatch(r"[0-9a-f]{64}", str(provenance.get("candidate_appcast_sha256", ""))):
        raise ReleaseContractError("provenance candidate Appcast checksum is missing")

    expected_targets = required - {"SHA256SUMS"}
    checksums = _read_checksums(directory / "SHA256SUMS")
    if set(checksums) != expected_targets:
        raise ReleaseContractError("SHA256SUMS entries do not match release artifact set")
    for name, expected in checksums.items():
        if _sha256(directory / name) != expected:
            raise ReleaseContractError(f"checksum mismatch: {name}")

    try:
        sbom = json.loads((directory / contract.sbom_name).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ReleaseContractError("release SBOM must be valid CycloneDX JSON") from exc
    if (
        sbom.get("bomFormat") != "CycloneDX"
        or not sbom.get("specVersion")
        or not isinstance(sbom.get("components"), list)
        or not sbom["components"]
    ):
        raise ReleaseContractError("release SBOM must be a populated CycloneDX document")
    expected_artifacts = (contract.dmg_name, contract.wheel_name)
    component_hashes: dict[str, set[str]] = {}
    for component in sbom["components"]:
        if not isinstance(component, dict) or component.get("type") != "file":
            continue
        name = component.get("name")
        if not isinstance(name, str):
            continue
        hashes = {
            str(entry.get("content", ""))
            for entry in component.get("hashes", [])
            if isinstance(entry, dict) and entry.get("alg") == "SHA-256"
        }
        component_hashes.setdefault(name, set()).update(hashes)
    for name in expected_artifacts:
        if _sha256(directory / name) not in component_hashes.get(name, set()):
            raise ReleaseContractError(f"SBOM does not bind release artifact: {name}")


def validate_candidate_binding(
    candidate_appcast: Path,
    directory: Path,
    contract: ReleaseContract,
) -> None:
    provenance = json.loads(
        (directory / contract.provenance_name).read_text(encoding="utf-8")
    )
    if provenance.get("candidate_appcast_sha256") != _sha256(candidate_appcast):
        raise ReleaseContractError("candidate Appcast checksum does not match provenance")
