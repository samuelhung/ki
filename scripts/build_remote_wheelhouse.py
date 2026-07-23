#!/usr/bin/env python3
"""Build a hash-locked deployment wheelhouse on the target host."""

from __future__ import annotations

import argparse
import hashlib
import os
import platform
import re
import shutil
import stat
import subprocess
import sys
import tempfile
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path


class WheelhouseBuildError(RuntimeError):
    pass


@dataclass(frozen=True)
class WheelhouseBuildConfig:
    stage: Path
    expected_machine: str = "x86_64"

    @property
    def requirements(self) -> Path:
        return self.stage / "requirements.lock"

    @property
    def build_requirements(self) -> Path:
        return self.stage / "backend-build-requirements.lock"

    @property
    def bootstrap_checksums(self) -> Path:
        return self.stage / "BOOTSTRAP_SHA256SUMS"

    @property
    def wheelhouse(self) -> Path:
        return self.stage / "wheelhouse"

    @property
    def checksums(self) -> Path:
        return self.stage / "SHA256SUMS"


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _real_file(path: Path, label: str) -> None:
    try:
        metadata = path.lstat()
    except FileNotFoundError as exc:
        raise WheelhouseBuildError(f"{label} is missing") from exc
    if stat.S_ISLNK(metadata.st_mode) or not stat.S_ISREG(metadata.st_mode):
        raise WheelhouseBuildError(f"{label} must be a regular non-symlink file")


def _validate_stage(config: WheelhouseBuildConfig) -> None:
    if platform.machine() != config.expected_machine:
        raise WheelhouseBuildError(
            f"target machine must be {config.expected_machine}, got {platform.machine()}"
        )
    try:
        metadata = config.stage.lstat()
    except FileNotFoundError as exc:
        raise WheelhouseBuildError("artifact stage is missing") from exc
    if stat.S_ISLNK(metadata.st_mode) or not stat.S_ISDIR(metadata.st_mode):
        raise WheelhouseBuildError("artifact stage must be a real directory")
    if config.stage.parent.name != "packages" or not re.fullmatch(
        r"[0-9a-fA-F]{40}", config.stage.name
    ):
        raise WheelhouseBuildError("artifact stage must be packages/<40-hex-source-sha>")
    for path, label in (
        (config.requirements, "requirements.lock"),
        (config.build_requirements, "backend build requirements"),
        (config.bootstrap_checksums, "bootstrap checksums"),
    ):
        _real_file(path, label)
    if config.wheelhouse.exists() or config.wheelhouse.is_symlink():
        raise WheelhouseBuildError("wheelhouse already exists")
    if config.checksums.exists() or config.checksums.is_symlink():
        raise WheelhouseBuildError("SHA256SUMS already exists")


def _verify_bootstrap_manifest(config: WheelhouseBuildConfig) -> None:
    checked = 0
    for line in config.bootstrap_checksums.read_text(encoding="ascii").splitlines():
        match = re.fullmatch(r"([0-9a-f]{64})  ([A-Za-z0-9._+-]+)", line)
        if match is None:
            raise WheelhouseBuildError("bootstrap checksum manifest is malformed")
        artifact = config.stage / match.group(2)
        _real_file(artifact, "bootstrap artifact")
        if _sha256(artifact) != match.group(1):
            raise WheelhouseBuildError(f"bootstrap checksum mismatch: {artifact.name}")
        checked += 1
    if checked == 0:
        raise WheelhouseBuildError("bootstrap checksum manifest is empty")


def _artifact_paths(config: WheelhouseBuildConfig) -> list[Path]:
    artifacts: list[Path] = []
    for path in sorted(config.stage.iterdir()):
        if path.name == "SHA256SUMS" or path == config.wheelhouse:
            continue
        metadata = path.lstat()
        if stat.S_ISLNK(metadata.st_mode) or not stat.S_ISREG(metadata.st_mode):
            raise WheelhouseBuildError(f"unsafe artifact entry: {path.name}")
        artifacts.append(path)
    for path in sorted(config.wheelhouse.iterdir()):
        metadata = path.lstat()
        if stat.S_ISLNK(metadata.st_mode) or not stat.S_ISREG(metadata.st_mode):
            raise WheelhouseBuildError(f"unsafe wheelhouse entry: {path.name}")
        artifacts.append(path)
    return artifacts


def _write_checksums(config: WheelhouseBuildConfig) -> None:
    lines = [
        f"{_sha256(path)}  {path.relative_to(config.stage).as_posix()}\n"
        for path in _artifact_paths(config)
    ]
    descriptor, temporary_name = tempfile.mkstemp(prefix=".SHA256SUMS.", dir=config.stage)
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w", encoding="ascii") as handle:
            handle.writelines(lines)
            handle.flush()
            os.fsync(handle.fileno())
        temporary.chmod(0o600)
        os.replace(temporary, config.checksums)
    finally:
        temporary.unlink(missing_ok=True)


def build_remote_wheelhouse(
    config: WheelhouseBuildConfig,
    *,
    run: Callable[..., subprocess.CompletedProcess] = subprocess.run,
) -> Path:
    _validate_stage(config)
    _verify_bootstrap_manifest(config)
    builder = Path(tempfile.mkdtemp(prefix=".wheelhouse-builder.", dir=config.stage))
    try:
        run([sys.executable, "-m", "venv", str(builder)], check=True)
        python = str(builder / "bin/python")
        config.wheelhouse.mkdir(mode=0o700)
        run(
            [
                python,
                "-m",
                "pip",
                "download",
                "--require-hashes",
                "--only-binary=:all:",
                "--dest",
                str(config.wheelhouse),
                "--requirement",
                str(config.build_requirements),
            ],
            check=True,
        )
        run(
            [
                python,
                "-m",
                "pip",
                "install",
                "--no-index",
                "--require-hashes",
                "--find-links",
                str(config.wheelhouse),
                "--requirement",
                str(config.build_requirements),
            ],
            check=True,
        )
        run(
            [
                python,
                "-m",
                "pip",
                "download",
                "--no-build-isolation",
                "--require-hashes",
                "--dest",
                str(config.wheelhouse),
                "--requirement",
                str(config.requirements),
            ],
            check=True,
        )
        if not any(config.wheelhouse.iterdir()):
            raise WheelhouseBuildError("wheelhouse is empty")
        shutil.rmtree(builder)
        _write_checksums(config)
        return config.wheelhouse
    except Exception:
        shutil.rmtree(config.wheelhouse, ignore_errors=True)
        config.checksums.unlink(missing_ok=True)
        raise
    finally:
        shutil.rmtree(builder, ignore_errors=True)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--stage", type=Path, required=True)
    parser.add_argument("--expected-machine", default="x86_64")
    args = parser.parse_args(argv)
    try:
        wheelhouse = build_remote_wheelhouse(
            WheelhouseBuildConfig(args.stage.absolute(), args.expected_machine)
        )
    except (WheelhouseBuildError, OSError, subprocess.CalledProcessError) as exc:
        print(f"remote wheelhouse build failed: {exc}", file=sys.stderr)
        return 2
    print(f"remote wheelhouse build complete: {wheelhouse}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
