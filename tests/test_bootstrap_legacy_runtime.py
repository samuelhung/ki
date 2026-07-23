from __future__ import annotations

import json
import os
import shutil
from pathlib import Path

import pytest

from scripts.bootstrap_legacy_runtime import (
    BootstrapConfig,
    BootstrapError,
    bootstrap_legacy_runtime,
)


def _runtime(tmp_path: Path, *, versions: bool = True) -> Path:
    runtime = tmp_path / "runtime"
    source_bin = runtime / "venv/bin"
    source_bin.mkdir(parents=True)
    for name in ("python", "zhiji"):
        executable = source_bin / name
        executable.write_text(name, encoding="utf-8")
        executable.chmod(0o755)
    if versions:
        (runtime / "versions").mkdir()
    return runtime


def _copy(source: Path, destination: Path) -> None:
    shutil.copytree(source, destination, symlinks=True)


def _config(runtime: Path) -> BootstrapConfig:
    return BootstrapConfig(
        runtime_root=runtime,
        expected_version="2.0.0",
        snapshot_name="legacy-2.0.0-pre-atomic",
        source_sha="a" * 40,
    )


def test_success_creates_missing_versions_and_publishes_snapshot(tmp_path: Path) -> None:
    runtime = _runtime(tmp_path, versions=False)

    target = bootstrap_legacy_runtime(
        _config(runtime), copy_runner=_copy, version_reader=lambda _python: "2.0.0"
    )

    assert target == runtime / "versions/legacy-2.0.0-pre-atomic"
    assert (runtime / "venv/bin/zhiji").exists()
    assert (target / "venv/bin/zhiji").exists()
    assert (runtime / "current").resolve() == target


@pytest.mark.parametrize("unsafe", ["source", "versions"])
def test_rejects_source_or_versions_symlink(tmp_path: Path, unsafe: str) -> None:
    runtime = _runtime(tmp_path)
    path = runtime / ("venv" if unsafe == "source" else "versions")
    real = runtime / f"real-{unsafe}"
    path.rename(real)
    path.symlink_to(real, target_is_directory=True)

    with pytest.raises(BootstrapError, match="symlink"):
        bootstrap_legacy_runtime(
            _config(runtime), copy_runner=_copy, version_reader=lambda _python: "2.0.0"
        )


def test_copy_failure_cleans_stage_and_allows_retry(tmp_path: Path) -> None:
    runtime = _runtime(tmp_path)

    def fail_copy(_source: Path, destination: Path) -> None:
        destination.mkdir(parents=True)
        raise OSError("copy failed")

    with pytest.raises(BootstrapError, match="copy failed"):
        bootstrap_legacy_runtime(
            _config(runtime), copy_runner=fail_copy, version_reader=lambda _python: "2.0.0"
        )

    assert list((runtime / "versions").iterdir()) == []
    bootstrap_legacy_runtime(
        _config(runtime), copy_runner=_copy, version_reader=lambda _python: "2.0.0"
    )


def test_current_appearing_during_copy_aborts_without_target(tmp_path: Path) -> None:
    runtime = _runtime(tmp_path)

    def copy_and_create_current(source: Path, destination: Path) -> None:
        _copy(source, destination)
        (runtime / "current").symlink_to(runtime / "venv")

    with pytest.raises(BootstrapError, match="current"):
        bootstrap_legacy_runtime(
            _config(runtime),
            copy_runner=copy_and_create_current,
            version_reader=lambda _python: "2.0.0",
        )

    assert not (runtime / "versions/legacy-2.0.0-pre-atomic").exists()
    assert not any(path.name.startswith(".legacy") for path in (runtime / "versions").iterdir())


def test_current_appearing_after_target_publish_removes_new_target(
    tmp_path: Path, monkeypatch
) -> None:
    runtime = _runtime(tmp_path)
    real_replace = os.replace

    def race_after_target(source: Path, destination: Path) -> None:
        real_replace(source, destination)
        if destination == runtime / "versions/legacy-2.0.0-pre-atomic":
            (runtime / "current").symlink_to(runtime / "venv")

    monkeypatch.setattr("scripts.bootstrap_legacy_runtime.os.replace", race_after_target)

    with pytest.raises(BootstrapError, match="current"):
        bootstrap_legacy_runtime(
            _config(runtime), copy_runner=_copy, version_reader=lambda _python: "2.0.0"
        )

    assert not (runtime / "versions/legacy-2.0.0-pre-atomic").exists()
    assert (runtime / "current").resolve() == runtime / "venv"


def test_source_identity_replacement_during_copy_aborts(tmp_path: Path) -> None:
    runtime = _runtime(tmp_path)

    def copy_and_replace_source(source: Path, destination: Path) -> None:
        _copy(source, destination)
        source.rename(runtime / "venv-old")
        source.mkdir()

    with pytest.raises(BootstrapError, match="identity"):
        bootstrap_legacy_runtime(
            _config(runtime),
            copy_runner=copy_and_replace_source,
            version_reader=lambda _python: "2.0.0",
        )

    assert not (runtime / "versions/legacy-2.0.0-pre-atomic").exists()
    assert not (runtime / "current").exists()


def test_release_metadata_is_non_secret_and_complete(tmp_path: Path) -> None:
    runtime = _runtime(tmp_path)

    target = bootstrap_legacy_runtime(
        _config(runtime), copy_runner=_copy, version_reader=lambda _python: "2.0.0"
    )
    metadata = json.loads((target / "release.json").read_text())

    assert metadata["release"] == "legacy-2.0.0-pre-atomic"
    assert metadata["version"] == "2.0.0"
    assert metadata["source"] == str(runtime / "venv")
    assert metadata["git_sha"] == "a" * 40
    assert "token" not in json.dumps(metadata).lower()
