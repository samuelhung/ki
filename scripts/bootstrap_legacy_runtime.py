#!/usr/bin/env python3
"""Bootstrap an immutable legacy runtime snapshot for atomic deployments."""

from __future__ import annotations

import argparse
import fcntl
import json
import os
import re
import shutil
import stat
import subprocess
import sys
import tempfile
from collections.abc import Callable
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path


class BootstrapError(RuntimeError):
    pass


@dataclass(frozen=True)
class BootstrapConfig:
    runtime_root: Path
    expected_version: str
    snapshot_name: str
    source_sha: str

    @property
    def source(self) -> Path:
        return self.runtime_root / "venv"

    @property
    def versions(self) -> Path:
        return self.runtime_root / "versions"

    @property
    def current(self) -> Path:
        return self.runtime_root / "current"

    @property
    def target(self) -> Path:
        return self.versions / self.snapshot_name


def _real_directory(path: Path) -> os.stat_result:
    try:
        metadata = path.lstat()
    except FileNotFoundError as exc:
        raise BootstrapError(f"directory is missing: {path}") from exc
    if stat.S_ISLNK(metadata.st_mode):
        raise BootstrapError(f"directory must not be a symlink: {path}")
    if not stat.S_ISDIR(metadata.st_mode):
        raise BootstrapError(f"path is not a directory: {path}")
    return metadata


def _require_absent(path: Path, label: str) -> None:
    try:
        path.lstat()
    except FileNotFoundError:
        return
    raise BootstrapError(f"{label} already exists: {path}")


def _fsync_directory(path: Path) -> None:
    descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


@contextmanager
def _deployment_lock(runtime: Path):
    lock_path = runtime / ".backend-deploy.lock"
    descriptor = os.open(
        lock_path,
        os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW | os.O_NONBLOCK,
        0o600,
    )
    try:
        os.fchmod(descriptor, 0o600)
        metadata = os.fstat(descriptor)
        if not stat.S_ISREG(metadata.st_mode):
            raise BootstrapError("deployment lock is not a regular file")
        fcntl.flock(descriptor, fcntl.LOCK_EX)
        yield
    finally:
        os.close(descriptor)


def _default_copy(source: Path, destination: Path) -> None:
    subprocess.run(["/usr/bin/ditto", str(source), str(destination)], check=True)


def _default_version_reader(python: Path) -> str:
    result = subprocess.run(
        [
            str(python),
            "-c",
            "import importlib.metadata as m; print(m.version('zhiji-backend'))",
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip()


def _write_release_metadata(path: Path, payload: dict[str, str]) -> None:
    data = (json.dumps(payload, indent=2, sort_keys=True) + "\n").encode()
    descriptor = os.open(
        path,
        os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW | os.O_NONBLOCK,
        0o600,
    )
    try:
        os.fchmod(descriptor, 0o600)
        view = memoryview(data)
        while view:
            written = os.write(descriptor, view)
            view = view[written:]
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _fsync_tree(root: Path) -> None:
    for directory, _directories, names in os.walk(root, topdown=False):
        directory_path = Path(directory)
        for name in names:
            path = directory_path / name
            metadata = path.lstat()
            if stat.S_ISLNK(metadata.st_mode):
                continue
            if not stat.S_ISREG(metadata.st_mode):
                raise BootstrapError(f"copied tree contains unsupported file: {path}")
            descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
            try:
                opened = os.fstat(descriptor)
                if (opened.st_dev, opened.st_ino) != (metadata.st_dev, metadata.st_ino):
                    raise BootstrapError(f"copied file identity changed: {path}")
                os.fsync(descriptor)
            finally:
                os.close(descriptor)
        _fsync_directory(directory_path)


def _prepare_versions(config: BootstrapConfig) -> None:
    try:
        _real_directory(config.versions)
    except BootstrapError:
        try:
            config.versions.lstat()
        except FileNotFoundError:
            config.versions.mkdir(mode=0o755)
            _fsync_directory(config.runtime_root)
            _real_directory(config.versions)
            return
        raise


def bootstrap_legacy_runtime(
    config: BootstrapConfig,
    *,
    copy_runner: Callable[[Path, Path], None] = _default_copy,
    version_reader: Callable[[Path], str] = _default_version_reader,
) -> Path:
    if not re.fullmatch(r"[A-Za-z0-9._+-]+", config.snapshot_name):
        raise BootstrapError("snapshot name contains unsupported characters")
    if not re.fullmatch(r"[0-9a-fA-F]{7,64}", config.source_sha):
        raise BootstrapError("source SHA is invalid")
    runtime_metadata = _real_directory(config.runtime_root)
    stage: Path | None = None
    published = False
    current_published = False
    with _deployment_lock(config.runtime_root):
        try:
            current_runtime = _real_directory(config.runtime_root)
            if (current_runtime.st_dev, current_runtime.st_ino) != (
                runtime_metadata.st_dev,
                runtime_metadata.st_ino,
            ):
                raise BootstrapError("runtime identity changed")
            source_metadata = _real_directory(config.source)
            _prepare_versions(config)
            versions_metadata = _real_directory(config.versions)
            _require_absent(config.current, "current")
            _require_absent(config.target, "target")
            stage = Path(
                tempfile.mkdtemp(prefix=f".{config.snapshot_name}.", dir=config.versions)
            )
            copy_runner(config.source, stage / "venv")
            copied_python = stage / "venv/bin/python"
            copied_zhiji = stage / "venv/bin/zhiji"
            if not copied_python.is_file() or not os.access(copied_python, os.X_OK):
                raise BootstrapError("copied Python is missing or not executable")
            if not copied_zhiji.is_file() or not os.access(copied_zhiji, os.X_OK):
                raise BootstrapError("copied zhiji is missing or not executable")
            if version_reader(copied_python) != config.expected_version:
                raise BootstrapError("copied zhiji-backend version does not match")
            _write_release_metadata(
                stage / "release.json",
                {
                    "git_sha": config.source_sha,
                    "migrated_at": datetime.now(UTC).isoformat(),
                    "release": config.snapshot_name,
                    "source": str(config.source),
                    "version": config.expected_version,
                },
            )
            _fsync_tree(stage)
            current_source = _real_directory(config.source)
            if (current_source.st_dev, current_source.st_ino) != (
                source_metadata.st_dev,
                source_metadata.st_ino,
            ):
                raise BootstrapError("source identity changed during copy")
            current_versions = _real_directory(config.versions)
            if (current_versions.st_dev, current_versions.st_ino) != (
                versions_metadata.st_dev,
                versions_metadata.st_ino,
            ):
                raise BootstrapError("versions identity changed during copy")
            _require_absent(config.current, "current")
            _require_absent(config.target, "target")
            os.replace(stage, config.target)
            stage = None
            published = True
            _fsync_directory(config.versions)
            _require_absent(config.current, "current")
            temporary = config.runtime_root / f".current.{os.getpid()}"
            _require_absent(temporary, "temporary current")
            temporary.symlink_to(config.target)
            try:
                _require_absent(config.current, "current")
                os.replace(temporary, config.current)
                current_published = True
                _fsync_directory(config.runtime_root)
            finally:
                temporary.unlink(missing_ok=True)
            return config.target
        except Exception as exc:
            if published and not current_published:
                shutil.rmtree(config.target, ignore_errors=True)
                _fsync_directory(config.versions)
            if isinstance(exc, BootstrapError):
                raise
            raise BootstrapError(str(exc)) from exc
        finally:
            if stage is not None:
                shutil.rmtree(stage, ignore_errors=True)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runtime-root", type=Path, required=True)
    parser.add_argument("--expected-version", required=True)
    parser.add_argument("--snapshot-name", default="legacy-2.0.0-pre-atomic")
    parser.add_argument("--source-sha", required=True)
    args = parser.parse_args(argv)
    try:
        target = bootstrap_legacy_runtime(
            BootstrapConfig(
                runtime_root=args.runtime_root.absolute(),
                expected_version=args.expected_version,
                snapshot_name=args.snapshot_name,
                source_sha=args.source_sha,
            )
        )
    except BootstrapError as exc:
        print(f"legacy runtime bootstrap failed: {exc}", file=sys.stderr)
        return 2
    print(f"legacy runtime bootstrap complete: {target}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
