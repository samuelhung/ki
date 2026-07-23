#!/usr/bin/env python3
"""Publish a verified release, exposing the Appcast only after remote verification."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile
from collections.abc import Callable
from pathlib import Path
from typing import Protocol

try:
    from scripts.release_contract import (
        ReleaseContract,
        expected_artifact_names,
        validate_release_artifacts,
    )
    from scripts.release_preflight import run_preflight
except ModuleNotFoundError:
    from release_contract import (  # type: ignore[no-redef]
        ReleaseContract,
        expected_artifact_names,
        validate_release_artifacts,
    )
    from release_preflight import run_preflight  # type: ignore[no-redef]


class ReleaseClient(Protocol):
    def create_draft(self, tag: str, commit: str, notes: Path) -> None: ...

    def upload(self, tag: str, assets: list[Path]) -> None: ...

    def download(self, tag: str, destination: Path) -> None: ...

    def publish(self, tag: str) -> None: ...


class GitHubReleaseClient:
    def __init__(self, *, run=subprocess.run):
        self._run = run

    def _checked(self, command: list[str]) -> None:
        self._run(command, check=True)

    def create_draft(self, tag: str, commit: str, notes: Path) -> None:
        self._checked(
            [
                "gh",
                "release",
                "create",
                tag,
                "--draft",
                "--target",
                commit,
                "--title",
                tag,
                "--notes-file",
                str(notes),
            ]
        )

    def upload(self, tag: str, assets: list[Path]) -> None:
        self._checked(["gh", "release", "upload", tag, *(str(path) for path in assets)])

    def download(self, tag: str, destination: Path) -> None:
        self._checked(["gh", "release", "download", tag, "--dir", str(destination)])

    def publish(self, tag: str) -> None:
        self._checked(["gh", "release", "edit", tag, "--draft=false", "--latest"])


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def publish_release_candidate(
    root: Path,
    tag: str,
    artifacts_dir: Path,
    candidate_appcast: Path,
    notes: Path,
    *,
    commit: str,
    client: ReleaseClient,
    publish_appcast: Callable[[Path], None],
    temp_root: Path,
) -> ReleaseContract:
    if not re.fullmatch(r"[0-9a-f]{40}", commit):
        raise ValueError("release commit must be a full Git SHA")
    if not notes.is_file():
        raise ValueError(f"release notes are missing: {notes}")
    contract = run_preflight(
        root,
        tag,
        artifacts_dir,
        candidate_appcast,
        expected_commit=commit,
    )
    assets = [artifacts_dir / name for name in sorted(expected_artifact_names(contract))]
    local_hashes = {asset.name: _sha256(asset) for asset in assets}
    candidate_bytes = candidate_appcast.read_bytes()
    provenance = json.loads(
        (artifacts_dir / contract.provenance_name).read_text(encoding="utf-8")
    )
    if hashlib.sha256(candidate_bytes).hexdigest() != provenance["candidate_appcast_sha256"]:
        raise ValueError("candidate Appcast changed after preflight")

    client.create_draft(contract.tag, commit, notes)
    client.upload(contract.tag, assets)
    if temp_root.exists() and any(temp_root.iterdir()):
        raise ValueError(f"remote verification directory is not empty: {temp_root}")
    temp_root.mkdir(parents=True, exist_ok=True)
    client.download(contract.tag, temp_root)
    validate_release_artifacts(temp_root, contract, expected_commit=commit)
    for name, expected_hash in local_hashes.items():
        if _sha256(temp_root / name) != expected_hash:
            raise ValueError(f"remote {name} does not match uploaded artifact")
    candidate_snapshot = temp_root / contract.candidate_appcast_name
    candidate_snapshot.write_bytes(candidate_bytes)
    client.publish(contract.tag)
    publish_appcast(candidate_snapshot)
    return contract


def _git_output(root: Path, *args: str) -> str:
    return subprocess.check_output(["git", *args], cwd=root, text=True).strip()


def _verify_release_checkout(root: Path) -> str:
    if _git_output(root, "branch", "--show-current") != "main":
        raise ValueError("release publication must run from main")
    if _git_output(root, "status", "--porcelain"):
        raise ValueError("release publication requires a clean checkout")
    return _git_output(root, "rev-parse", "HEAD")


def verify_appcast_push_ready(root: Path, *, run=subprocess.run) -> None:
    run(["git", "push", "--dry-run", "origin", "main"], cwd=root, check=True)


def publish_live_appcast(root: Path, candidate: Path, *, run=subprocess.run) -> None:
    destination = root / "appcast.xml"
    fd, temporary_name = tempfile.mkstemp(prefix=".appcast.", dir=root)
    temporary = Path(temporary_name)
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(candidate.read_bytes())
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, destination)
    finally:
        temporary.unlink(missing_ok=True)
    run(["git", "add", "appcast.xml"], cwd=root, check=True)
    run(["git", "commit", "-m", "release: publish verified appcast"], cwd=root, check=True)
    try:
        run(["git", "push", "origin", "main"], cwd=root, check=True)
    except subprocess.CalledProcessError:
        run(["git", "fetch", "origin", "main"], cwd=root, check=True)
        try:
            run(["git", "rebase", "origin/main"], cwd=root, check=True)
        except subprocess.CalledProcessError:
            run(["git", "rebase", "--abort"], cwd=root, check=False)
            raise
        run(["git", "push", "origin", "main"], cwd=root, check=True)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Publish a verified Zhiji GitHub release")
    parser.add_argument("tag")
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parent.parent)
    parser.add_argument("--artifacts-dir", type=Path, required=True)
    parser.add_argument("--candidate-appcast", type=Path, required=True)
    parser.add_argument("--notes", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        root = args.root.resolve()
        commit = _verify_release_checkout(root)
        verify_appcast_push_ready(root)
        with tempfile.TemporaryDirectory(prefix="zhiji-release-verify-") as temporary:
            publish_release_candidate(
                root,
                args.tag,
                args.artifacts_dir.resolve(),
                args.candidate_appcast.resolve(),
                args.notes.resolve(),
                commit=commit,
                client=GitHubReleaseClient(),
                publish_appcast=lambda candidate: publish_live_appcast(root, candidate),
                temp_root=Path(temporary),
            )
    except (OSError, subprocess.CalledProcessError, ValueError) as exc:
        print(f"release publication failed: {exc}", file=sys.stderr)
        return 2
    print(f"release published: {args.tag}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
