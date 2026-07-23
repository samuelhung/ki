from __future__ import annotations

import base64
import hashlib
import json
import shutil
import subprocess
from pathlib import Path

import pytest

from scripts.build_release import (
    ReleaseBuildError,
    generate_release_sbom,
    parse_sparkle_signature,
    require_fresh_release_build,
    sign_sparkle_update,
    verify_release_build_checkout,
    write_candidate_appcast,
    write_release_metadata,
)
from scripts.publish_release import (
    GitHubReleaseClient,
    publish_live_appcast,
    publish_release_candidate,
    verify_appcast_push_ready,
)
from scripts.release_contract import expected_artifact_names, load_release_contract

ROOT = Path(__file__).resolve().parents[1]
VALID_SPARKLE_SIGNATURE = base64.b64encode(b"s" * 64).decode("ascii")


def _write_complete_artifacts(directory: Path, *, commit: str = "c" * 40) -> tuple[object, Path]:
    contract = load_release_contract(ROOT, "v2.0.0+90")
    directory.mkdir(parents=True, exist_ok=True)
    for name in expected_artifact_names(contract) - {"SHA256SUMS", contract.provenance_name}:
        (directory / name).write_bytes(name.encode())
    (directory / contract.sbom_name).write_text(
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
                                "content": hashlib.sha256((directory / name).read_bytes()).hexdigest(),
                            }
                        ],
                    }
                    for name in (contract.dmg_name, contract.wheel_name)
                ],
            }
        ),
        encoding="utf-8",
    )
    candidate = directory / contract.candidate_appcast_name
    candidate.write_text(
        f"""<rss version="2.0" xmlns:sparkle="http://www.andymatuschak.org/xml-namespaces/sparkle">
<channel><item><enclosure url="{contract.download_url}"
sparkle:version="{contract.build}" sparkle:shortVersionString="{contract.version}"
sparkle:edSignature="{VALID_SPARKLE_SIGNATURE}" length="{(directory / contract.dmg_name).stat().st_size}"
type="application/octet-stream" /></item></channel></rss>
""",
        encoding="utf-8",
    )
    provenance = {
        "schema_version": 1,
        "tag": contract.tag,
        "version": contract.version,
        "build": contract.build,
        "commit": commit,
        "built_at": "2026-07-23T00:00:00Z",
        "tools": {"python": "3.12.11"},
        "candidate_appcast_sha256": hashlib.sha256(candidate.read_bytes()).hexdigest(),
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
    return contract, candidate


def test_sparkle_signature_parser_requires_structured_signature_and_exact_length() -> None:
    assert (
        parse_sparkle_signature(
            f'sparkle:edSignature="{VALID_SPARKLE_SIGNATURE}" length="42"',
            expected_length=42,
        )
        == VALID_SPARKLE_SIGNATURE
    )
    with pytest.raises(ReleaseBuildError, match="malformed"):
        parse_sparkle_signature("abc123", expected_length=42)
    with pytest.raises(ReleaseBuildError, match="length"):
        parse_sparkle_signature(
            f'sparkle:edSignature="{VALID_SPARKLE_SIGNATURE}" length="41"',
            expected_length=42,
        )
    with pytest.raises(ReleaseBuildError, match="signature is invalid"):
        parse_sparkle_signature('sparkle:edSignature="abc123" length="42"', expected_length=42)


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

    write_candidate_appcast(
        live,
        candidate,
        contract,
        VALID_SPARKLE_SIGNATURE,
        dmg_size=123,
        pub_date="date",
    )

    assert live.read_bytes() == before
    assert contract.download_url in candidate.read_text(encoding="utf-8")
    assert 'sparkle:version="90"' in candidate.read_text(encoding="utf-8")


def test_release_metadata_writes_provenance_and_complete_checksums(tmp_path: Path) -> None:
    contract = load_release_contract(ROOT, "v2.0.0+90")
    for name in (contract.dmg_name, contract.wheel_name, contract.sbom_name):
        (tmp_path / name).write_bytes(name.encode())
    candidate = tmp_path / contract.candidate_appcast_name
    candidate.write_bytes(b"candidate")

    write_release_metadata(
        tmp_path,
        contract,
        candidate_appcast=candidate,
        commit="f" * 40,
        tools={"python": "3.12.11", "flutter": "3.44.2"},
        built_at="2026-07-23T00:00:00Z",
    )

    provenance = json.loads((tmp_path / contract.provenance_name).read_text(encoding="utf-8"))
    assert provenance["tag"] == contract.tag
    assert provenance["commit"] == "f" * 40
    assert provenance["candidate_appcast_sha256"] == hashlib.sha256(b"candidate").hexdigest()
    checksum_names = {
        line.split("  ", 1)[1]
        for line in (tmp_path / "SHA256SUMS").read_text(encoding="ascii").splitlines()
    }
    assert checksum_names == expected_artifact_names(contract) - {"SHA256SUMS"}


def test_release_sbom_is_generated_by_syft_from_only_release_binaries(tmp_path: Path) -> None:
    dmg = tmp_path / "zhiji_2.0.0.dmg"
    wheel = tmp_path / "zhiji_backend-2.0.0-py3-none-any.whl"
    dmg.write_bytes(b"dmg")
    wheel.write_bytes(b"wheel")
    output = tmp_path / "zhiji_2.0.0+90.cdx.json"
    syft = tmp_path / "syft"
    syft.write_text("verified tool", encoding="utf-8")
    observed_sources: list[set[str]] = []

    def fake_run(command: list[str], **kwargs) -> None:
        assert kwargs["check"] is True
        assert kwargs["env"]["SYFT_CHECK_FOR_APP_UPDATE"] == "false"
        source = Path(command[2].removeprefix("dir:"))
        observed_sources.append({path.name for path in source.iterdir()})
        destination = Path(command[-1].split("=", 1)[1])
        destination.write_text(
            json.dumps(
                {
                    "bomFormat": "CycloneDX",
                    "specVersion": "1.6",
                    "components": [{"type": "application", "name": "zhiji", "version": "2.0.0"}],
                }
            ),
            encoding="utf-8",
        )

    generate_release_sbom(
        syft,
        [dmg, wheel],
        output,
        run=fake_run,
    )

    assert observed_sources == [{dmg.name, wheel.name}]
    payload = json.loads(output.read_text(encoding="utf-8"))
    assert payload["bomFormat"] == "CycloneDX"
    file_components = {
        component["name"]: component["hashes"][0]["content"]
        for component in payload["components"]
        if component["type"] == "file"
    }
    assert file_components == {
        dmg.name: hashlib.sha256(dmg.read_bytes()).hexdigest(),
        wheel.name: hashlib.sha256(wheel.read_bytes()).hexdigest(),
    }


class FakeReleaseClient:
    def __init__(
        self,
        source: Path,
        events: list[str],
        *,
        corrupt_download: bool = False,
        replace_remote_set: bool = False,
    ):
        self.source = source
        self.events = events
        self.corrupt_download = corrupt_download
        self.replace_remote_set = replace_remote_set

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
        if self.replace_remote_set:
            dmg = next(destination.glob("*.dmg"))
            dmg.write_bytes(b"remote replacement")
            sbom_path = next(destination.glob("*.cdx.json"))
            sbom = json.loads(sbom_path.read_text(encoding="utf-8"))
            for component in sbom["components"]:
                if component.get("name") == dmg.name:
                    component["hashes"] = [
                        {"alg": "SHA-256", "content": hashlib.sha256(dmg.read_bytes()).hexdigest()}
                    ]
            sbom_path.write_text(json.dumps(sbom), encoding="utf-8")
            checksum_path = destination / "SHA256SUMS"
            lines = []
            for line in checksum_path.read_text(encoding="ascii").splitlines():
                _digest, name = line.split("  ", 1)
                lines.append(
                    f"{hashlib.sha256((destination / name).read_bytes()).hexdigest()}  {name}"
                )
            checksum_path.write_text("\n".join(lines) + "\n", encoding="ascii")

    def publish(self, tag: str) -> None:
        self.events.append(f"publish:{tag}")


def test_publish_order_verifies_redownload_before_release_and_appcast(tmp_path: Path) -> None:
    artifacts = tmp_path / "artifacts"
    contract, candidate = _write_complete_artifacts(artifacts, commit="d" * 40)
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
    contract, candidate = _write_complete_artifacts(artifacts, commit="e" * 40)
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


def test_remote_verification_must_match_the_frozen_local_artifact_set(tmp_path: Path) -> None:
    artifacts = tmp_path / "artifacts"
    contract, candidate = _write_complete_artifacts(artifacts, commit="e" * 40)
    notes = artifacts / "RELEASE_NOTES.md"
    notes.write_text("notes", encoding="utf-8")
    events: list[str] = []

    with pytest.raises(ValueError, match="does not match uploaded artifact"):
        publish_release_candidate(
            ROOT,
            contract.tag,
            artifacts,
            candidate,
            notes,
            commit="e" * 40,
            client=FakeReleaseClient(artifacts, events, replace_remote_set=True),
            publish_appcast=lambda _candidate: events.append("appcast"),
            temp_root=tmp_path / "verify",
        )

    assert "publish" not in [event.split(":", 1)[0] for event in events]
    assert "appcast" not in events


def test_release_build_requires_clean_main_checkout(tmp_path: Path) -> None:
    responses = {
        ("branch", "--show-current"): "main\n",
        ("status", "--porcelain"): "",
        ("rev-parse", "HEAD"): f"{'a' * 40}\n",
    }

    def clean(command: list[str], **kwargs) -> str:
        assert command[0] == "git"
        assert kwargs == {"cwd": tmp_path, "text": True}
        return responses[tuple(command[1:])]

    assert verify_release_build_checkout(tmp_path, check_output=clean) == "a" * 40

    responses[("status", "--porcelain")] = " M src/changed.py\n"
    with pytest.raises(ReleaseBuildError, match="clean checkout"):
        verify_release_build_checkout(tmp_path, check_output=clean)

    responses[("status", "--porcelain")] = ""
    responses[("branch", "--show-current")] = "feature\n"
    with pytest.raises(ReleaseBuildError, match="from main"):
        verify_release_build_checkout(tmp_path, check_output=clean)


def test_release_build_cannot_reuse_an_unattested_existing_binary() -> None:
    require_fresh_release_build(skip_build=False)
    with pytest.raises(ReleaseBuildError, match="skip-build is disabled"):
        require_fresh_release_build(skip_build=True)


def test_release_target_must_match_artifact_provenance_before_draft_creation(tmp_path: Path) -> None:
    artifacts = tmp_path / "artifacts"
    contract, candidate = _write_complete_artifacts(artifacts, commit="a" * 40)
    notes = artifacts / "RELEASE_NOTES.md"
    notes.write_text("notes", encoding="utf-8")
    events: list[str] = []

    with pytest.raises(ValueError, match="provenance commit"):
        publish_release_candidate(
            ROOT,
            contract.tag,
            artifacts,
            candidate,
            notes,
            commit="b" * 40,
            client=FakeReleaseClient(artifacts, events),
            publish_appcast=lambda _candidate: events.append("appcast"),
            temp_root=tmp_path / "verify",
        )

    assert events == []


def test_tampered_candidate_appcast_fails_before_draft_creation(tmp_path: Path) -> None:
    artifacts = tmp_path / "artifacts"
    contract, candidate = _write_complete_artifacts(artifacts)
    candidate.write_text(candidate.read_text(encoding="utf-8") + "\n", encoding="utf-8")
    notes = artifacts / "RELEASE_NOTES.md"
    notes.write_text("notes", encoding="utf-8")
    events: list[str] = []

    with pytest.raises(ValueError, match="candidate Appcast checksum"):
        publish_release_candidate(
            ROOT,
            contract.tag,
            artifacts,
            candidate,
            notes,
            commit="c" * 40,
            client=FakeReleaseClient(artifacts, events),
            publish_appcast=lambda _candidate: events.append("appcast"),
            temp_root=tmp_path / "verify",
        )

    assert events == []


def test_published_appcast_uses_the_verified_candidate_snapshot(tmp_path: Path) -> None:
    artifacts = tmp_path / "artifacts"
    contract, candidate = _write_complete_artifacts(artifacts)
    verified_bytes = candidate.read_bytes()
    notes = artifacts / "RELEASE_NOTES.md"
    notes.write_text("notes", encoding="utf-8")
    events: list[str] = []

    class MutatingClient(FakeReleaseClient):
        def publish(self, tag: str) -> None:
            super().publish(tag)
            candidate.write_text("<rss>tampered</rss>", encoding="utf-8")

    published: list[bytes] = []
    publish_release_candidate(
        ROOT,
        contract.tag,
        artifacts,
        candidate,
        notes,
        commit="c" * 40,
        client=MutatingClient(artifacts, events),
        publish_appcast=lambda snapshot: published.append(snapshot.read_bytes()),
        temp_root=tmp_path / "verify",
    )

    assert published == [verified_bytes]


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


def test_appcast_push_capability_is_checked_before_publication(tmp_path: Path) -> None:
    calls: list[tuple[list[str], dict[str, object]]] = []

    def record(command: list[str], **kwargs) -> None:
        calls.append((command, kwargs))

    verify_appcast_push_ready(tmp_path, run=record)

    assert calls == [
        (["git", "push", "--dry-run", "origin", "main"], {"cwd": tmp_path, "check": True})
    ]


def test_appcast_push_rebases_once_after_a_concurrent_main_update(tmp_path: Path) -> None:
    candidate = tmp_path / "candidate.xml"
    candidate.write_text("<rss />", encoding="utf-8")
    commands: list[list[str]] = []
    push_attempts = 0

    def run(command: list[str], **kwargs) -> None:
        nonlocal push_attempts
        assert kwargs == {"cwd": tmp_path, "check": True}
        commands.append(command)
        if command[:2] == ["git", "push"]:
            push_attempts += 1
            if push_attempts == 1:
                raise subprocess.CalledProcessError(1, command)

    publish_live_appcast(tmp_path, candidate, run=run)

    assert commands == [
        ["git", "add", "appcast.xml"],
        ["git", "commit", "-m", "release: publish verified appcast"],
        ["git", "push", "origin", "main"],
        ["git", "fetch", "origin", "main"],
        ["git", "rebase", "origin/main"],
        ["git", "push", "origin", "main"],
    ]
