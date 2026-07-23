from __future__ import annotations

import base64
import hashlib
import json
from pathlib import Path

import pytest

from scripts.release_contract import (
    ReleaseContractError,
    expected_artifact_names,
    load_release_contract,
    validate_candidate_appcast,
    validate_release_artifacts,
)
from scripts.release_preflight import run_preflight


ROOT = Path(__file__).resolve().parents[1]
VALID_SPARKLE_SIGNATURE = base64.b64encode(b"s" * 64).decode("ascii")


def test_repository_release_contract_uses_strict_tag_and_consistent_versions() -> None:
    contract = load_release_contract(ROOT, "v2.0.0+90")

    assert contract.version == "2.0.0"
    assert contract.build == 90
    assert contract.tag == "v2.0.0+90"
    assert contract.dmg_name == "zhiji_2.0.0.dmg"
    assert contract.wheel_name == "zhiji_backend-2.0.0-py3-none-any.whl"


@pytest.mark.parametrize(
    "tag",
    ["2.0.0+90", "v2.0+90", "v2.0.0", "v2.0.0+0", "v2.0.0+build"],
)
def test_release_contract_rejects_noncanonical_tags(tag: str) -> None:
    with pytest.raises(ReleaseContractError, match="release tag"):
        load_release_contract(ROOT, tag)


def test_release_contract_rejects_source_version_drift(tmp_path: Path) -> None:
    (tmp_path / "pyproject.toml").write_text('[project]\nversion = "2.0.1"\n', encoding="utf-8")
    backend = tmp_path / "src" / "zhiji_backend"
    backend.mkdir(parents=True)
    (backend / "__init__.py").write_text('__version__ = "2.0.0"\n', encoding="utf-8")
    desktop = tmp_path / "desktop"
    desktop.mkdir()
    (desktop / "pubspec.yaml").write_text("version: 2.0.0+90\n", encoding="utf-8")
    (desktop / "changelog.json").write_text(
        json.dumps({"versions": [{"version": "2.0.0"}]}), encoding="utf-8"
    )
    plist = desktop / "macos" / "Runner" / "Info.plist"
    plist.parent.mkdir(parents=True)
    plist.write_text(
        """<?xml version="1.0" encoding="UTF-8"?>
<plist version="1.0"><dict>
<key>CFBundleShortVersionString</key><string>$(FLUTTER_BUILD_NAME)</string>
<key>CFBundleVersion</key><string>$(FLUTTER_BUILD_NUMBER)</string>
<key>SUFeedURL</key><string>https://raw.githubusercontent.com/samuelhung/ki/main/appcast.xml</string>
<key>SUPublicEDKey</key><string>abcdefghijklmnopqrstuvwxyz1234567890ABCDEFG=</string>
</dict></plist>
""",
        encoding="utf-8",
    )

    with pytest.raises(ReleaseContractError, match="version mismatch"):
        load_release_contract(tmp_path, "v2.0.0+90")


def test_candidate_appcast_must_match_tag_build_url_and_asset(tmp_path: Path) -> None:
    contract = load_release_contract(ROOT, "v2.0.0+90")
    candidate = tmp_path / contract.candidate_appcast_name
    candidate.write_text(
        f"""<?xml version="1.0" encoding="utf-8"?>
<rss version="2.0" xmlns:sparkle="http://www.andymatuschak.org/xml-namespaces/sparkle">
<channel><item><enclosure
url="https://github.com/samuelhung/ki/releases/download/v2.0.0%2B90/{contract.dmg_name}"
sparkle:version="90" sparkle:shortVersionString="2.0.0"
sparkle:edSignature="{VALID_SPARKLE_SIGNATURE}" length="4" type="application/octet-stream" />
</item></channel></rss>
""",
        encoding="utf-8",
    )

    dmg = tmp_path / contract.dmg_name
    dmg.write_bytes(b"test")
    validate_candidate_appcast(candidate, contract, dmg_path=dmg)

    candidate.write_text(
        candidate.read_text().replace('length="4"', 'length="3"'),
        encoding="utf-8",
    )
    with pytest.raises(ReleaseContractError, match="length does not match DMG"):
        validate_candidate_appcast(candidate, contract, dmg_path=dmg)

    candidate.write_text(
        candidate.read_text().replace('length="3"', 'length="4"'),
        encoding="utf-8",
    )
    candidate.write_text(candidate.read_text().replace("%2B90", "%2B91"), encoding="utf-8")
    with pytest.raises(ReleaseContractError, match="download URL"):
        validate_candidate_appcast(candidate, contract, dmg_path=dmg)


def test_release_artifacts_require_exact_assets_checksums_and_provenance(tmp_path: Path) -> None:
    contract = load_release_contract(ROOT, "v2.0.0+90")
    names = expected_artifact_names(contract)
    for name in names - {"SHA256SUMS", contract.provenance_name}:
        (tmp_path / name).write_bytes(name.encode())
    valid_sbom = json.dumps(
        {
            "bomFormat": "CycloneDX",
            "specVersion": "1.6",
            "components": [
                {
                    "type": "file",
                    "name": name,
                    "hashes": [
                        {
                            "alg": "SHA-256",
                            "content": hashlib.sha256((tmp_path / name).read_bytes()).hexdigest(),
                        }
                    ],
                }
                for name in (contract.dmg_name, contract.wheel_name)
            ],
        }
    )
    (tmp_path / contract.sbom_name).write_text(valid_sbom, encoding="utf-8")

    provenance = {
        "schema_version": 1,
        "tag": contract.tag,
        "version": contract.version,
        "build": contract.build,
        "commit": "a" * 40,
        "built_at": "2026-07-23T00:00:00Z",
        "tools": {"python": "3.12.11", "flutter": "3.44.2"},
        "candidate_appcast_sha256": "0" * 64,
    }
    (tmp_path / contract.provenance_name).write_text(json.dumps(provenance), encoding="utf-8")

    checksum_targets = names - {"SHA256SUMS"}
    lines = []
    for name in sorted(checksum_targets):
        digest = hashlib.sha256((tmp_path / name).read_bytes()).hexdigest()
        lines.append(f"{digest}  {name}")
    (tmp_path / "SHA256SUMS").write_text("\n".join(lines) + "\n", encoding="ascii")

    validate_release_artifacts(tmp_path, contract, expected_commit="a" * 40)
    with pytest.raises(ReleaseContractError, match="provenance commit"):
        validate_release_artifacts(tmp_path, contract, expected_commit="b" * 40)

    (tmp_path / contract.sbom_name).write_text(
        json.dumps(
            {
                "bomFormat": "CycloneDX",
                "specVersion": "1.6",
                "components": [{"type": "application", "name": "unrelated"}],
            }
        ),
        encoding="utf-8",
    )
    lines = []
    for name in sorted(checksum_targets):
        digest = hashlib.sha256((tmp_path / name).read_bytes()).hexdigest()
        lines.append(f"{digest}  {name}")
    (tmp_path / "SHA256SUMS").write_text("\n".join(lines) + "\n", encoding="ascii")
    with pytest.raises(ReleaseContractError, match="SBOM does not bind release artifact"):
        validate_release_artifacts(tmp_path, contract)

    (tmp_path / contract.sbom_name).write_text("{}", encoding="utf-8")
    lines = []
    for name in sorted(checksum_targets):
        digest = hashlib.sha256((tmp_path / name).read_bytes()).hexdigest()
        lines.append(f"{digest}  {name}")
    (tmp_path / "SHA256SUMS").write_text("\n".join(lines) + "\n", encoding="ascii")
    with pytest.raises(ReleaseContractError, match="CycloneDX"):
        validate_release_artifacts(tmp_path, contract)

    (tmp_path / contract.sbom_name).write_text(valid_sbom, encoding="utf-8")
    (tmp_path / contract.sbom_name).write_bytes(b"tampered")
    with pytest.raises(ReleaseContractError, match="checksum mismatch"):
        validate_release_artifacts(tmp_path, contract)


def test_single_preflight_validates_source_candidate_and_artifacts(tmp_path: Path) -> None:
    contract = load_release_contract(ROOT, "v2.0.0+90")
    for name in expected_artifact_names(contract) - {"SHA256SUMS", contract.provenance_name}:
        (tmp_path / name).write_bytes(name.encode())
    (tmp_path / contract.sbom_name).write_text(
        json.dumps(
            {
                "bomFormat": "CycloneDX",
                "specVersion": "1.6",
                "components": [
                    {
                        "type": "file",
                        "name": name,
                        "hashes": [
                            {
                                "alg": "SHA-256",
                                "content": hashlib.sha256((tmp_path / name).read_bytes()).hexdigest(),
                            }
                        ],
                    }
                    for name in (contract.dmg_name, contract.wheel_name)
                ],
            }
        ),
        encoding="utf-8",
    )
    candidate = tmp_path / contract.candidate_appcast_name
    candidate.write_text(
        f"""<rss version="2.0" xmlns:sparkle="http://www.andymatuschak.org/xml-namespaces/sparkle">
<channel><item><enclosure url="{contract.download_url}"
sparkle:version="{contract.build}" sparkle:shortVersionString="{contract.version}"
sparkle:edSignature="{VALID_SPARKLE_SIGNATURE}" length="{(tmp_path / contract.dmg_name).stat().st_size}"
type="application/octet-stream" /></item></channel></rss>
""",
        encoding="utf-8",
    )
    provenance = {
        "schema_version": 1,
        "tag": contract.tag,
        "version": contract.version,
        "build": contract.build,
        "commit": "b" * 40,
        "built_at": "2026-07-23T00:00:00Z",
        "tools": {"python": "3.12.11"},
        "candidate_appcast_sha256": hashlib.sha256(candidate.read_bytes()).hexdigest(),
    }
    (tmp_path / contract.provenance_name).write_text(json.dumps(provenance), encoding="utf-8")
    checksum_targets = expected_artifact_names(contract) - {"SHA256SUMS"}
    (tmp_path / "SHA256SUMS").write_text(
        "".join(
            f"{hashlib.sha256((tmp_path / name).read_bytes()).hexdigest()}  {name}\n"
            for name in sorted(checksum_targets)
        ),
        encoding="ascii",
    )
    assert run_preflight(ROOT, contract.tag, tmp_path, candidate, expected_commit="b" * 40) == contract

    candidate.write_text(candidate.read_text(encoding="utf-8") + "\n", encoding="utf-8")
    with pytest.raises(ReleaseContractError, match="candidate Appcast checksum"):
        run_preflight(ROOT, contract.tag, tmp_path, candidate, expected_commit="b" * 40)
