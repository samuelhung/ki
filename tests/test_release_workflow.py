from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
from pathlib import Path

import pytest

from scripts.build_release import (
    ReleaseBuildError,
    parse_sparkle_signature,
    sign_sparkle_update,
    write_release_metadata,
    write_candidate_appcast,
)
from scripts.publish_release import GitHubReleaseClient, publish_release_candidate
from scripts.release_contract import expected_artifact_names, load_release_contract


ROOT = Path(__file__).resolve().parents[1]


def _write_complete_artifacts(directory: Path) -> tuple[object, Path]:
    contract = load_release_contract(ROOT, "v2.0.0+90")
    directory.mkdir(parents=True, exist_ok=True)
    for name in expected_artifact_names(contract) - {"SHA256SUMS", contract.provenance_name}:
        (directory / name).write_bytes(name.encode())
    provenance = {
        "schema_version": 1,
        "tag": contract.tag,
        "version": contract.version,
        "build": contract.build,
        "commit": "c" * 40,
        "built_at": "2026-07-23T00:00:00Z",
        "tools": {"python": "3.12.11"},
    }
    (directory / contract.provenance_name).write_text(json.dumps(provenance), encoding="utf-8")
    targets = expected_artifact_names(contract) - {"SHA256SUMS"}
    (directory / "SHA256SUMS").write_text(
        "".join(
            f"{hashlib.sha256((directory / name).read_bytes()).hexdigest()}  {name}\n"
            for name in sorted(targets)
        ),
        encoding="ascii",
    )
    candidate = directory / contract.candidate_appcast_name
    candidate.write_text(
        f"""<rss version="2.0" xmlns:sparkle="http://www.andymatuschak.org/xml-namespaces/sparkle">
<channel><item><enclosure url="{contract.download_url}"
sparkle:version="{contract.build}" sparkle:shortVersionString="{contract.version}"
sparkle:edSignature="signed" length="1" type="application/octet-stream" /></item></channel></rss>
""",
        encoding="utf-8",
    )
    return contract, candidate


def test_sparkle_signature_parser_requires_structured_signature_and_exact_length() -> None:
    assert (
        parse_sparkle_signature('sparkle:edSignature="abc123" length="42"', expected_length=42)
        == "abc123"
    )
    with pytest.raises(ReleaseBuildError, match="malformed"):
        parse_sparkle_signature("abc123", expected_length=42)
    with pytest.raises(ReleaseBuildError, match="length"):
        parse_sparkle_signature('sparkle:edSignature="abc123" length="41"', expected_length=42)


def test_sparkle_signing_missing_tool_and_nonzero_exit_are_hard_failures(tmp_path: Path) -> None:
    dmg = tmp_path / "release.dmg"
    dmg.write_bytes(b"release")
    with pytest.raises(ReleaseBuildError, match="sign_update is missing"):
        sign_sparkle_update(tmp_path / "missing", dmg)

    tool = tmp_path / "sign_update"
    tool.write_text("tool", encoding="utf-8")

    def failed_run(*_args, **_kwargs):
        return subprocess.CompletedProcess([], 1, stdout="", stderr="no key")

    with pytest.raises(ReleaseBuildError, match="sign_update failed"):
        sign_sparkle_update(tool, dmg, run=failed_run)


def test_candidate_appcast_is_generated_without_mutating_live_feed(tmp_path: Path) -> None:
    contract = load_release_contract(ROOT, "v2.0.0+90")
    live = tmp_path / "appcast.xml"
    live.write_text(
        """<rss version="2.0" xmlns:sparkle="http://www.andymatuschak.org/xml-namespaces/sparkle">
<channel><title>feed</title><link>https://github.com/samuelhung/ki/releases</link></channel></rss>
""",
        encoding="utf-8",
    )
    before = live.read_bytes()
    candidate = tmp_path / contract.candidate_appcast_name

    write_candidate_appcast(live, candidate, contract, "signature", dmg_size=123, pub_date="date")

    assert live.read_bytes() == before
    assert contract.download_url in candidate.read_text(encoding="utf-8")
    assert 'sparkle:version="90"' in candidate.read_text(encoding="utf-8")


def test_release_metadata_writes_provenance_and_complete_checksums(tmp_path: Path) -> None:
    contract = load_release_contract(ROOT, "v2.0.0+90")
    for name in (contract.dmg_name, contract.wheel_name, contract.sbom_name):
        (tmp_path / name).write_bytes(name.encode())

    write_release_metadata(
        tmp_path,
        contract,
        commit="f" * 40,
        tools={"python": "3.12.11", "flutter": "3.44.2"},
        built_at="2026-07-23T00:00:00Z",
    )

    provenance = json.loads((tmp_path / contract.provenance_name).read_text(encoding="utf-8"))
    assert provenance["tag"] == contract.tag
    assert provenance["commit"] == "f" * 40
    checksum_names = {
        line.split("  ", 1)[1]
        for line in (tmp_path / "SHA256SUMS").read_text(encoding="ascii").splitlines()
    }
    assert checksum_names == expected_artifact_names(contract) - {"SHA256SUMS"}


class FakeReleaseClient:
    def __init__(self, source: Path, events: list[str], *, corrupt_download: bool = False):
        self.source = source
        self.events = events
        self.corrupt_download = corrupt_download

    def create_draft(self, tag: str, commit: str, notes: Path) -> None:
        self.events.append(f"draft:{tag}:{commit}:{notes.name}")

    def upload(self, tag: str, assets: list[Path]) -> None:
        self.events.append(f"upload:{tag}:{','.join(path.name for path in assets)}")

    def download(self, tag: str, destination: Path) -> None:
        self.events.append(f"download:{tag}")
        destination.mkdir(parents=True, exist_ok=True)
        for path in self.source.iterdir():
            if path.is_file() and path.name != "RELEASE_NOTES.md" and ".candidate." not in path.name:
                shutil.copy2(path, destination / path.name)
        if self.corrupt_download:
            dmg = next(destination.glob("*.dmg"))
            dmg.write_bytes(b"corrupt")

    def publish(self, tag: str) -> None:
        self.events.append(f"publish:{tag}")


def test_publish_order_verifies_redownload_before_release_and_appcast(tmp_path: Path) -> None:
    artifacts = tmp_path / "artifacts"
    contract, candidate = _write_complete_artifacts(artifacts)
    notes = artifacts / "RELEASE_NOTES.md"
    notes.write_text("notes", encoding="utf-8")
    events: list[str] = []
    client = FakeReleaseClient(artifacts, events)

    publish_release_candidate(
        ROOT,
        contract.tag,
        artifacts,
        candidate,
        notes,
        commit="d" * 40,
        client=client,
        publish_appcast=lambda _candidate: events.append("appcast"),
        temp_root=tmp_path / "verify",
    )

    assert [event.split(":", 1)[0] for event in events] == [
        "draft",
        "upload",
        "download",
        "publish",
        "appcast",
    ]


def test_failed_remote_verification_leaves_release_draft_and_appcast_untouched(tmp_path: Path) -> None:
    artifacts = tmp_path / "artifacts"
    contract, candidate = _write_complete_artifacts(artifacts)
    notes = artifacts / "RELEASE_NOTES.md"
    notes.write_text("notes", encoding="utf-8")
    events: list[str] = []
    client = FakeReleaseClient(artifacts, events, corrupt_download=True)

    with pytest.raises(ValueError, match="checksum mismatch"):
        publish_release_candidate(
            ROOT,
            contract.tag,
            artifacts,
            candidate,
            notes,
            commit="e" * 40,
            client=client,
            publish_appcast=lambda _candidate: events.append("appcast"),
            temp_root=tmp_path / "verify",
        )

    assert "publish" not in [event.split(":", 1)[0] for event in events]
    assert "appcast" not in events


def test_github_release_client_uses_fail_closed_release_commands(tmp_path: Path) -> None:
    commands: list[list[str]] = []

    def record(command: list[str], **kwargs) -> None:
        assert kwargs == {"check": True}
        commands.append(command)

    client = GitHubReleaseClient(run=record)
    notes = tmp_path / "RELEASE_NOTES.md"
    assets = [tmp_path / "artifact.dmg", tmp_path / "SHA256SUMS"]
    destination = tmp_path / "download"

    client.create_draft("v2.0.0+90", "a" * 40, notes)
    client.upload("v2.0.0+90", assets)
    client.download("v2.0.0+90", destination)
    client.publish("v2.0.0+90")

    assert commands == [
        [
            "gh",
            "release",
            "create",
            "v2.0.0+90",
            "--draft",
            "--target",
            "a" * 40,
            "--title",
            "v2.0.0+90",
            "--notes-file",
            str(notes),
        ],
        [
            "gh",
            "release",
            "upload",
            "v2.0.0+90",
            str(assets[0]),
            str(assets[1]),
        ],
        ["gh", "release", "download", "v2.0.0+90", "--dir", str(destination)],
        ["gh", "release", "edit", "v2.0.0+90", "--draft=false", "--latest"],
    ]
