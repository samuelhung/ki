#!/usr/bin/env python3
"""Install a backend release atomically and roll back failed health checks."""

from __future__ import annotations

import argparse
import errno
import hashlib
import ipaddress
import json
import os
import plistlib
import re
import shutil
import sqlite3
import stat
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
import zipfile
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Protocol

RELEASE_TAG_PATTERN = re.compile(r"^v(?P<version>\d+\.\d+\.\d+)\+(?P<build>[1-9]\d*)$")
BACKUP_PATTERN = re.compile(r"^deploy-(?P<day>\d{8})-(?P<time>\d{6})(?:-\d+)?\.sqlite$")


class BackendDeployError(RuntimeError):
    pass


class ServiceController(Protocol):
    def stop(self) -> None: ...

    def start(self) -> None: ...


@dataclass(frozen=True)
class BackendDeployConfig:
    release_tag: str
    runtime_root: Path
    zhiji_home: Path
    user_home: Path
    database_path: Path
    backups_dir: Path
    wheel: Path
    checksums: Path
    launchd_plist: Path
    launchd_label: str
    health_origin: str
    python_executable: Path
    bind_host: str = "127.0.0.1"

    @property
    def release_id(self) -> str:
        match = RELEASE_TAG_PATTERN.fullmatch(self.release_tag)
        if not match:
            raise BackendDeployError("release tag must use vX.Y.Z+N")
        return f"{match.group('version')}+{match.group('build')}"

    @property
    def version(self) -> str:
        match = RELEASE_TAG_PATTERN.fullmatch(self.release_tag)
        if not match:
            raise BackendDeployError("release tag must use vX.Y.Z+N")
        return match.group("version")

    @property
    def versions_dir(self) -> Path:
        return self.runtime_root / "versions"

    @property
    def current_link(self) -> Path:
        return self.runtime_root / "current"


class LaunchdServiceController:
    def __init__(self, config: BackendDeployConfig, *, run=subprocess.run, uid: int | None = None):
        self._config = config
        self._run = run
        self._domain = f"gui/{os.getuid() if uid is None else uid}"

    def stop(self) -> None:
        self._run(
            ["launchctl", "bootout", f"{self._domain}/{self._config.launchd_label}"],
            check=True,
        )

    def start(self) -> None:
        self._run(
            ["launchctl", "bootstrap", self._domain, str(self._config.launchd_plist)],
            check=True,
        )


def _is_loopback_bind(bind_host: str) -> bool:
    if bind_host == "localhost":
        return True
    try:
        return ipaddress.ip_address(bind_host).is_loopback
    except ValueError as exc:
        raise BackendDeployError("bind host must be an IP literal or localhost") from exc


def _parse_env_value(value: str) -> str | None:
    value = value.strip()
    if value[:1] in {"'", '"'}:
        quote = value[0]
        closing_quote = value.rfind(quote)
        if closing_quote == 0:
            return None
        suffix = value[closing_quote + 1 :].strip()
        if suffix and not suffix.startswith("#"):
            return None
        return value[1:closing_quote].strip()
    return re.split(r"\s+#", value, maxsplit=1)[0].strip()


def _env_value(lines: Iterable[str], key: str) -> str:
    result = ""
    for line in lines:
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line.removeprefix("export ").strip()
        candidate, separator, value = line.partition("=")
        if separator and candidate.strip() == key:
            parsed = _parse_env_value(value)
            if parsed is not None:
                result = parsed
    return result


def _validate_remote_bind_environment(config: BackendDeployConfig) -> None:
    if _is_loopback_bind(config.bind_host):
        return

    env_file = config.zhiji_home / ".env"
    try:
        descriptor = os.open(env_file, os.O_RDONLY | os.O_NOFOLLOW)
    except FileNotFoundError as exc:
        raise BackendDeployError("secure .env is required for a non-loopback bind") from exc
    except OSError as exc:
        if exc.errno == errno.ELOOP:
            raise BackendDeployError(".env must be a regular non-symlink file") from exc
        raise BackendDeployError("unable to inspect secure .env") from exc

    try:
        try:
            env_stat = os.fstat(descriptor)
        except OSError as exc:
            raise BackendDeployError("unable to inspect secure .env") from exc
        if not stat.S_ISREG(env_stat.st_mode):
            raise BackendDeployError(".env must be a regular non-symlink file")
        if stat.S_IMODE(env_stat.st_mode) != 0o600:
            raise BackendDeployError(".env must have mode 0600")
        try:
            with os.fdopen(descriptor, encoding="utf-8", closefd=False) as env_handle:
                api_token = _env_value(env_handle, "KI_API_TOKEN")
        except (OSError, UnicodeError) as exc:
            raise BackendDeployError("unable to read secure .env") from exc
    finally:
        os.close(descriptor)
    if not api_token:
        raise BackendDeployError("KI_API_TOKEN must be non-empty for a non-loopback bind")


def _validate_config(config: BackendDeployConfig) -> None:
    _validate_remote_bind_environment(config)
    paths = {
        "runtime path": config.runtime_root,
        "Zhiji home path": config.zhiji_home,
        "user home path": config.user_home,
        "database path": config.database_path,
        "backups path": config.backups_dir,
        "wheel path": config.wheel,
        "checksums path": config.checksums,
        "launchd plist path": config.launchd_plist,
        "Python path": config.python_executable,
    }
    if any(not path.is_absolute() for path in paths.values()):
        raise BackendDeployError("all deployment paths must be absolute")
    expected = {
        "runtime path": config.zhiji_home / "runtime",
        "database path": config.zhiji_home / "data" / "intelligence.sqlite",
        "backups path": config.zhiji_home / "backups",
        "wheel path": config.zhiji_home / "packages" / config.wheel.name,
        "checksums path": config.zhiji_home / "packages" / "SHA256SUMS",
        "launchd plist path": (
            config.user_home / "Library" / "LaunchAgents" / f"{config.launchd_label}.plist"
        ),
    }
    for label, expected_path in expected.items():
        if paths[label] != expected_path:
            raise BackendDeployError(f"{label} is outside the configured deployment path")
    for label, path in paths.items():
        if path.is_symlink():
            raise BackendDeployError(f"{label} must not be a symbolic link")
    managed_directories = {
        "runtime directory": config.runtime_root,
        "versions directory": config.versions_dir,
        "data directory": config.zhiji_home / "data",
        "packages directory": config.zhiji_home / "packages",
        "launchd parent directory": config.user_home / "Library",
        "launchd directory": config.user_home / "Library" / "LaunchAgents",
    }
    for label, path in managed_directories.items():
        if path.is_symlink():
            raise BackendDeployError(f"{label} must not be a symbolic link")
    if not re.fullmatch(r"[A-Za-z0-9.-]+", config.launchd_label):
        raise BackendDeployError("launchd label is invalid")
    origin = urllib.parse.urlsplit(config.health_origin)
    if (
        origin.scheme != "http"
        or origin.hostname not in {"127.0.0.1", "localhost", "::1"}
        or origin.username is not None
        or origin.password is not None
        or origin.path not in {"", "/"}
        or origin.query
        or origin.fragment
    ):
        raise BackendDeployError("health origin must be a loopback HTTP origin")

def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _verify_release_artifact(config: BackendDeployConfig) -> None:
    expected_name = f"zhiji_backend-{config.version}-py3-none-any.whl"
    if config.wheel.name != expected_name or not config.wheel.is_file():
        raise BackendDeployError(f"wheel does not match release: {expected_name}")
    if not config.checksums.is_file():
        raise BackendDeployError("SHA256SUMS is missing")
    checksum = None
    for line in config.checksums.read_text(encoding="ascii").splitlines():
        match = re.fullmatch(r"([0-9a-f]{64})  ([^/]+)", line)
        if match and match.group(2) == config.wheel.name:
            checksum = match.group(1)
            break
    if checksum is None or _sha256(config.wheel) != checksum:
        raise BackendDeployError("wheel checksum does not match SHA256SUMS")
    try:
        with zipfile.ZipFile(config.wheel) as archive:
            metadata_names = [name for name in archive.namelist() if name.endswith(".dist-info/METADATA")]
            if len(metadata_names) != 1:
                raise BackendDeployError("wheel metadata is missing or ambiguous")
            metadata = archive.read(metadata_names[0]).decode("utf-8")
    except (OSError, UnicodeDecodeError, zipfile.BadZipFile) as exc:
        raise BackendDeployError(f"wheel is invalid: {type(exc).__name__}") from exc
    version = re.search(r"^Version:\s*(\S+)\s*$", metadata, re.MULTILINE)
    if version is None or version.group(1) != config.version:
        raise BackendDeployError("wheel metadata version does not match release")


def _atomic_write(path: Path, payload: bytes, *, mode: int = 0o600) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        temporary.chmod(mode)
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def write_launchd_plist(config: BackendDeployConfig) -> None:
    _validate_remote_bind_environment(config)
    executable = config.current_link / "venv" / "bin" / "zhiji"
    payload = {
        "Label": config.launchd_label,
        "ProgramArguments": [
            str(executable),
            "serve",
            "--host",
            config.bind_host,
            "--port",
            str(urllib.parse.urlsplit(config.health_origin).port or 9120),
        ],
        "RunAtLoad": True,
        "KeepAlive": True,
        "WorkingDirectory": str(config.zhiji_home),
        "EnvironmentVariables": {"ZHIJI_HOME": str(config.zhiji_home)},
        "StandardOutPath": str(config.zhiji_home / "data" / "logs" / "launchd-stdout.log"),
        "StandardErrorPath": str(config.zhiji_home / "data" / "logs" / "launchd-stderr.log"),
    }
    _atomic_write(config.launchd_plist, plistlib.dumps(payload, sort_keys=False))


def _default_installer(stage: Path, config: BackendDeployConfig) -> None:
    venv = stage / "venv"
    subprocess.run([str(config.python_executable), "-m", "venv", str(venv)], check=True)
    subprocess.run(
        [
            str(venv / "bin" / "python"),
            "-m",
            "pip",
            "install",
            "--disable-pip-version-check",
            str(config.wheel),
        ],
        check=True,
    )


def _prepare_version(
    config: BackendDeployConfig,
    installer: Callable[[Path, BackendDeployConfig], None],
) -> Path:
    target = config.versions_dir / config.release_id
    if target.exists() or target.is_symlink():
        raise BackendDeployError(f"release version already exists: {target}")
    config.versions_dir.mkdir(parents=True, exist_ok=True)
    stage = Path(tempfile.mkdtemp(prefix=f".{config.release_id}.", dir=config.versions_dir))
    try:
        installer(stage, config)
        executable = stage / "venv" / "bin" / "zhiji"
        if not executable.is_file():
            raise BackendDeployError("installed release has no zhiji executable")
        (stage / "release.json").write_text(
            json.dumps(
                {
                    "tag": config.release_tag,
                    "version": config.version,
                    "wheel": config.wheel.name,
                    "sha256": _sha256(config.wheel),
                },
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
        os.replace(stage, target)
    except Exception:
        shutil.rmtree(stage, ignore_errors=True)
        raise
    return target


def _current_target(config: BackendDeployConfig) -> Path | None:
    if not config.current_link.is_symlink():
        if config.current_link.exists():
            raise BackendDeployError("runtime/current must be a symbolic link")
        return None
    target = config.current_link.resolve(strict=True)
    try:
        target.relative_to(config.versions_dir.resolve())
    except ValueError as exc:
        raise BackendDeployError("runtime/current points outside versions directory") from exc
    return target


def _switch_current(config: BackendDeployConfig, target: Path | None) -> None:
    config.current_link.parent.mkdir(parents=True, exist_ok=True)
    if target is None:
        config.current_link.unlink(missing_ok=True)
        return
    temporary = config.current_link.with_name(f".{config.current_link.name}.{os.getpid()}")
    temporary.unlink(missing_ok=True)
    temporary.symlink_to(target)
    os.replace(temporary, config.current_link)


def _create_database_backup(
    database: Path,
    backups_dir: Path,
    now: datetime,
) -> Path:
    if not database.is_file() or database.is_symlink():
        raise BackendDeployError("database must be a regular file")
    backups_dir.mkdir(parents=True, exist_ok=True)
    stamp = now.astimezone(UTC).strftime("%Y%m%d-%H%M%S")
    target = backups_dir / f"deploy-{stamp}.sqlite"
    if target.exists():
        raise BackendDeployError(f"deployment backup already exists: {target.name}")
    descriptor, temporary_name = tempfile.mkstemp(prefix=".deploy-backup.", dir=backups_dir)
    os.close(descriptor)
    temporary = Path(temporary_name)
    try:
        with sqlite3.connect(f"file:{database}?mode=ro", uri=True) as source:
            with sqlite3.connect(temporary) as destination:
                source.backup(destination)
                result = destination.execute("PRAGMA integrity_check").fetchone()[0]
                if result != "ok":
                    raise BackendDeployError("deployment database backup failed integrity check")
        temporary.chmod(0o600)
        os.replace(temporary, target)
    finally:
        temporary.unlink(missing_ok=True)
    return target


def _restore_database(backup: Path, database: Path) -> None:
    descriptor, temporary_name = tempfile.mkstemp(prefix=".deploy-restore.", dir=database.parent)
    os.close(descriptor)
    temporary = Path(temporary_name)
    try:
        with sqlite3.connect(f"file:{backup}?mode=ro", uri=True) as source:
            with sqlite3.connect(temporary) as destination:
                source.backup(destination)
                if destination.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
                    raise BackendDeployError("rollback database failed integrity check")
        temporary.chmod(0o600)
        os.replace(temporary, database)
        for suffix in ("-wal", "-shm"):
            database.with_name(f"{database.name}{suffix}").unlink(missing_ok=True)
    finally:
        temporary.unlink(missing_ok=True)


def default_smoke_check(origin: str, *, timeout_seconds: float = 30) -> None:
    checks = (
        ("/api/health", lambda payload: payload.get("ok") is True),
        (
            "/api/system/health",
            lambda payload: payload.get("ok") is True
            and isinstance(payload.get("database"), dict)
            and payload["database"].get("ok") is True,
        ),
        ("/api/dashboard/summary", lambda payload: isinstance(payload, dict)),
    )
    deadline = time.monotonic() + timeout_seconds
    last_error = "service did not respond"
    while time.monotonic() < deadline:
        try:
            for path, validate in checks:
                with urllib.request.urlopen(f"{origin.rstrip('/')}{path}", timeout=3) as response:
                    payload = json.load(response)
                if not validate(payload):
                    raise BackendDeployError(f"smoke check returned unhealthy payload: {path}")
            return
        except (BackendDeployError, OSError, ValueError, urllib.error.URLError) as exc:
            last_error = str(exc)
            time.sleep(0.5)
    raise BackendDeployError(f"backend smoke checks failed: {last_error}")


def prune_versions(
    versions_dir: Path,
    *,
    current: Path,
    rollback_target: Path | None = None,
    keep_previous: int = 2,
) -> None:
    entries = sorted(
        (path for path in versions_dir.iterdir() if path.is_dir() and not path.is_symlink()),
        key=lambda path: path.stat().st_mtime_ns,
        reverse=True,
    )
    current = current.resolve()
    keep = {current}
    previous_count = 0
    if rollback_target is not None and rollback_target.resolve() != current:
        keep.add(rollback_target.resolve())
        previous_count = 1
    for path in entries:
        resolved = path.resolve()
        if resolved in keep:
            continue
        if previous_count < keep_previous:
            keep.add(resolved)
            previous_count += 1
    for path in entries:
        if path.resolve() not in keep:
            shutil.rmtree(path)


def prune_daily_backups(backups_dir: Path, *, keep_days: int = 7) -> None:
    grouped: dict[str, list[Path]] = {}
    for path in backups_dir.iterdir():
        match = BACKUP_PATTERN.fullmatch(path.name)
        if match and path.is_file() and not path.is_symlink():
            grouped.setdefault(match.group("day"), []).append(path)
    days = sorted(grouped, reverse=True)
    for day_index, day in enumerate(days):
        entries = sorted(grouped[day], key=lambda path: path.name, reverse=True)
        keep = entries[:1] if day_index < keep_days else []
        for path in entries:
            if path not in keep:
                path.unlink()


def deploy_backend(
    config: BackendDeployConfig,
    *,
    service: ServiceController,
    smoke_check: Callable[[], None],
    installer: Callable[[Path, BackendDeployConfig], None] = _default_installer,
    now: Callable[[], datetime] = lambda: datetime.now(UTC),
) -> Path:
    _validate_config(config)
    _verify_release_artifact(config)
    previous = _current_target(config)
    target = _prepare_version(config, installer)
    try:
        write_launchd_plist(config)
    except Exception:
        shutil.rmtree(target, ignore_errors=True)
        raise
    backup: Path | None = None
    try:
        service.stop()
    except Exception as exc:
        shutil.rmtree(target, ignore_errors=True)
        raise BackendDeployError(f"deployment failed before switch: service stop failed: {exc}") from exc
    stopped = True
    switched = False
    try:
        backup = _create_database_backup(config.database_path, config.backups_dir, now())
        _switch_current(config, target)
        switched = True
        service.start()
        stopped = False
        smoke_check()
        prune_versions(
            config.versions_dir,
            current=target,
            rollback_target=previous,
            keep_previous=2,
        )
        prune_daily_backups(config.backups_dir, keep_days=7)
        return target
    except Exception as original:
        rollback_errors: list[str] = []
        if not stopped:
            try:
                service.stop()
                stopped = True
            except Exception as exc:
                rollback_errors.append(f"stop failed: {exc}")
        rollback_ready = stopped
        if rollback_ready and backup is not None:
            try:
                _restore_database(backup, config.database_path)
            except Exception as exc:
                rollback_errors.append(f"database restore failed: {exc}")
                rollback_ready = False
        if rollback_ready and switched:
            try:
                _switch_current(config, previous)
            except Exception as exc:
                rollback_errors.append(f"version switch failed: {exc}")
                rollback_ready = False
        if rollback_ready and previous is not None:
            try:
                service.start()
                stopped = False
                smoke_check()
            except Exception as exc:
                rollback_errors.append(f"previous version recovery failed: {exc}")
                rollback_ready = False
        active_target = _current_target(config)
        if rollback_ready and target.exists() and active_target != target:
            shutil.rmtree(target, ignore_errors=True)
        if rollback_errors:
            raise BackendDeployError(
                f"deployment failed: {original}; rollback incomplete: {'; '.join(rollback_errors)}"
            ) from original
        if isinstance(original, BackendDeployError):
            raise
        raise BackendDeployError(f"deployment failed: {original}") from original


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Atomically deploy a Zhiji backend wheel")
    parser.add_argument("tag")
    parser.add_argument("--runtime-root", type=Path, required=True)
    parser.add_argument("--zhiji-home", type=Path, required=True)
    parser.add_argument("--user-home", type=Path, required=True)
    parser.add_argument("--database", type=Path, required=True)
    parser.add_argument("--backups-dir", type=Path, required=True)
    parser.add_argument("--wheel", type=Path, required=True)
    parser.add_argument("--checksums", type=Path, required=True)
    parser.add_argument("--launchd-plist", type=Path, required=True)
    parser.add_argument("--launchd-label", default="com.zhiji.backend")
    parser.add_argument("--health-origin", default="http://127.0.0.1:9120")
    parser.add_argument("--python", type=Path, default=Path(sys.executable))
    args = parser.parse_args(argv)
    config = BackendDeployConfig(
        release_tag=args.tag,
        runtime_root=args.runtime_root.absolute(),
        zhiji_home=args.zhiji_home.absolute(),
        user_home=args.user_home.absolute(),
        database_path=args.database.absolute(),
        backups_dir=args.backups_dir.absolute(),
        wheel=args.wheel.absolute(),
        checksums=args.checksums.absolute(),
        launchd_plist=args.launchd_plist.absolute(),
        launchd_label=args.launchd_label,
        health_origin=args.health_origin,
        python_executable=args.python,
    )
    try:
        target = deploy_backend(
            config,
            service=LaunchdServiceController(config),
            smoke_check=lambda: default_smoke_check(config.health_origin),
        )
    except (BackendDeployError, OSError, sqlite3.Error, subprocess.CalledProcessError) as exc:
        print(f"backend deployment failed: {exc}", file=sys.stderr)
        return 2
    print(f"backend deployment complete: {target}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
