from __future__ import annotations

import hashlib
import subprocess
import sys
from pathlib import Path

import pytest

from scripts.build_remote_wheelhouse import (
    WheelhouseBuildConfig,
    WheelhouseBuildError,
    build_remote_wheelhouse,
)


def _stage(tmp_path: Path) -> WheelhouseBuildConfig:
    stage = tmp_path / "packages" / ("a" * 40)
    stage.mkdir(parents=True)
    for name, contents in (
        ("requirements.lock", "demo==1 --hash=sha256:" + "1" * 64 + "\n"),
        ("backend-build-requirements.lock", "wheel==1 --hash=sha256:" + "2" * 64 + "\n"),
        ("deploy_backend.py", "deployment tool\n"),
    ):
        (stage / name).write_text(contents, encoding="ascii")
    manifest = "".join(
        f"{hashlib.sha256(path.read_bytes()).hexdigest()}  {path.name}\n"
        for path in sorted(stage.iterdir())
    )
    (stage / "BOOTSTRAP_SHA256SUMS").write_text(manifest, encoding="ascii")
    return WheelhouseBuildConfig(stage=stage, expected_machine="test-machine")


def test_wrong_target_machine_fails_before_creating_wheelhouse(
    tmp_path: Path, monkeypatch
) -> None:
    config = _stage(tmp_path)
    monkeypatch.setattr("scripts.build_remote_wheelhouse.platform.machine", lambda: "arm64")

    with pytest.raises(WheelhouseBuildError, match="target machine"):
        build_remote_wheelhouse(config)

    assert not config.wheelhouse.exists()


def test_build_uses_hash_locked_target_host_download_and_writes_final_manifest(
    tmp_path: Path, monkeypatch
) -> None:
    config = _stage(tmp_path)
    monkeypatch.setattr(
        "scripts.build_remote_wheelhouse.platform.machine", lambda: "test-machine"
    )
    commands: list[list[str]] = []

    def run(command: list[str], **kwargs) -> subprocess.CompletedProcess:
        assert kwargs == {"check": True}
        commands.append(command)
        if command[2:5] == ["pip", "download", "--no-build-isolation"]:
            (config.wheelhouse / "demo-1-py3-none-any.whl").write_bytes(b"dependency")
        return subprocess.CompletedProcess(command, 0)

    result = build_remote_wheelhouse(config, run=run)

    assert result == config.wheelhouse
    assert commands[0][:3] == [sys.executable, "-m", "venv"]
    assert "--require-hashes" in commands[1]
    assert "--only-binary=:all:" in commands[1]
    assert "--no-index" in commands[2]
    assert "--no-build-isolation" in commands[3]
    manifest = config.checksums.read_text(encoding="ascii")
    assert "wheelhouse/demo-1-py3-none-any.whl" in manifest
    assert not any(path.name.startswith(".wheelhouse-builder") for path in config.stage.iterdir())


def test_tampered_bootstrap_artifact_fails_before_subprocess(tmp_path: Path, monkeypatch) -> None:
    config = _stage(tmp_path)
    monkeypatch.setattr(
        "scripts.build_remote_wheelhouse.platform.machine", lambda: "test-machine"
    )
    (config.stage / "deploy_backend.py").write_text("tampered\n", encoding="ascii")

    with pytest.raises(WheelhouseBuildError, match="bootstrap checksum mismatch"):
        build_remote_wheelhouse(config)

    assert not config.wheelhouse.exists()
