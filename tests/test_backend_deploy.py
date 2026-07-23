from __future__ import annotations

import hashlib
import json
import os
import plistlib
import sqlite3
import subprocess
import sys
import zipfile
from dataclasses import dataclass, field, replace
from datetime import UTC, datetime
from pathlib import Path

import pytest

from scripts.deploy_backend import (
    BackendDeployConfig,
    BackendDeployError,
    LaunchdServiceController,
    _restore_database,
    _validate_remote_bind_environment,
    default_smoke_check,
    deploy_backend,
    main,
    prune_daily_backups,
    prune_versions,
    write_launchd_plist,
)


def _database(path: Path, value: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(path) as connection:
        connection.execute("CREATE TABLE state (value TEXT NOT NULL)")
        connection.execute("INSERT INTO state VALUES (?)", (value,))


def _read_database(path: Path) -> str:
    with sqlite3.connect(path) as connection:
        return connection.execute("SELECT value FROM state").fetchone()[0]


def _release_files(tmp_path: Path) -> tuple[Path, Path]:
    packages = tmp_path / "packages"
    packages.mkdir(exist_ok=True)
    wheel = packages / "zhiji_backend-2.0.0-py3-none-any.whl"
    with zipfile.ZipFile(wheel, "w") as archive:
        archive.writestr(
            "zhiji_backend-2.0.0.dist-info/METADATA",
            "Metadata-Version: 2.4\nName: zhiji-backend\nVersion: 2.0.0\n",
        )
    checksums = packages / "SHA256SUMS"
    checksums.write_text(
        f"{hashlib.sha256(wheel.read_bytes()).hexdigest()}  {wheel.name}\n",
        encoding="ascii",
    )
    return wheel, checksums


def _config(tmp_path: Path) -> BackendDeployConfig:
    wheel, checksums = _release_files(tmp_path)
    database = tmp_path / "data" / "intelligence.sqlite"
    _database(database, "before")
    return BackendDeployConfig(
        release_tag="v2.0.0+90",
        runtime_root=tmp_path / "runtime",
        zhiji_home=tmp_path,
        user_home=tmp_path / "home",
        database_path=database,
        backups_dir=tmp_path / "backups",
        wheel=wheel,
        checksums=checksums,
        launchd_plist=tmp_path / "home" / "Library" / "LaunchAgents" / "com.test.zhiji.plist",
        launchd_label="com.test.zhiji",
        health_origin="http://127.0.0.1:19120",
        python_executable=Path("/test/python3.12"),
    )


@dataclass
class FakeService:
    events: list[str] = field(default_factory=list)

    def stop(self) -> None:
        self.events.append("stop")

    def start(self) -> None:
        self.events.append("start")


def _install(stage: Path, _config: BackendDeployConfig) -> None:
    executable = stage / "venv" / "bin" / "zhiji"
    executable.parent.mkdir(parents=True)
    executable.write_text("executable", encoding="utf-8")


def _write_secure_api_token(home: Path, value: str = "test-only-token") -> Path:
    env_file = home / ".env"
    env_file.write_text(f"KI_API_TOKEN={value}\n", encoding="utf-8")
    env_file.chmod(0o600)
    return env_file


def _write_secure_env_contents(home: Path, contents: str) -> Path:
    env_file = home / ".env"
    env_file.write_text(contents, encoding="utf-8")
    env_file.chmod(0o600)
    return env_file


def _main_argv(config: BackendDeployConfig) -> list[str]:
    return [
        config.release_tag,
        "--runtime-root",
        str(config.runtime_root),
        "--zhiji-home",
        str(config.zhiji_home),
        "--user-home",
        str(config.user_home),
        "--database",
        str(config.database_path),
        "--backups-dir",
        str(config.backups_dir),
        "--wheel",
        str(config.wheel),
        "--checksums",
        str(config.checksums),
        "--launchd-plist",
        str(config.launchd_plist),
        "--python",
        str(config.python_executable),
    ]


def test_main_propagates_public_bind_host_with_absolute_paths(
    tmp_path: Path,
    monkeypatch,
) -> None:
    config = _config(tmp_path)
    _write_secure_api_token(config.zhiji_home)
    captured: list[BackendDeployConfig] = []

    def capture_deploy(deploy_config: BackendDeployConfig, **_kwargs) -> Path:
        captured.append(deploy_config)
        return deploy_config.versions_dir / deploy_config.release_id

    monkeypatch.setattr("scripts.deploy_backend.deploy_backend", capture_deploy)
    monkeypatch.setattr("scripts.deploy_backend.LaunchdServiceController", lambda _config: object())

    result = main([*_main_argv(config), "--bind-host", "0.0.0.0"])

    assert result == 0
    assert captured[0].bind_host == "0.0.0.0"
    assert all(
        path.is_absolute()
        for path in (
            captured[0].runtime_root,
            captured[0].zhiji_home,
            captured[0].user_home,
            captured[0].database_path,
            captured[0].backups_dir,
            captured[0].wheel,
            captured[0].checksums,
            captured[0].launchd_plist,
            captured[0].python_executable,
        )
    )


@pytest.mark.parametrize("option", ["--api-token", "--ki-api-token", "--remote-api-token"])
@pytest.mark.parametrize("form", ["separated", "equals"])
def test_main_rejects_command_line_secrets_without_echoing_them(
    tmp_path: Path,
    option: str,
    form: str,
    capsys,
) -> None:
    config = _config(tmp_path)
    secret = "sentinel-command-line-secret"
    guarded = [option, secret] if form == "separated" else [f"{option}={secret}"]

    result = main([*_main_argv(config), *guarded])

    stderr = capsys.readouterr().err
    assert result == 2
    assert secret not in stderr
    assert "backend deployment failed:" in stderr
    assert "KI_API_TOKEN" in stderr
    assert "server-side .env" in stderr


def test_deploy_installs_immutable_version_and_atomically_switches_current(tmp_path: Path) -> None:
    config = _config(tmp_path)
    service = FakeService()
    smoke_targets: list[Path] = []

    result = deploy_backend(
        config,
        service=service,
        installer=_install,
        smoke_check=lambda: smoke_targets.append(config.current_link.resolve()),
        now=lambda: datetime(2026, 7, 23, 12, tzinfo=UTC),
    )

    assert result == config.versions_dir / "2.0.0+90"
    assert config.current_link.is_symlink()
    assert config.current_link.resolve() == result
    assert smoke_targets == [result]
    assert service.events == ["stop", "start"]
    assert list(config.backups_dir.glob("deploy-*.sqlite"))
    assert "runtime/current/venv/bin/zhiji" in config.launchd_plist.read_text(encoding="utf-8")


def test_failed_smoke_restores_database_and_previous_version(tmp_path: Path) -> None:
    config = _config(tmp_path)
    old = config.versions_dir / "1.9.0+89"
    (old / "venv" / "bin").mkdir(parents=True)
    (old / "venv" / "bin" / "zhiji").write_text("old", encoding="utf-8")
    config.current_link.parent.mkdir(parents=True, exist_ok=True)
    config.current_link.symlink_to(old)
    service = FakeService()
    smoke_attempts = 0

    def smoke() -> None:
        nonlocal smoke_attempts
        smoke_attempts += 1
        if smoke_attempts == 1:
            with sqlite3.connect(config.database_path) as connection:
                connection.execute("UPDATE state SET value = 'mutated'")
            raise BackendDeployError("new version unhealthy")

    with pytest.raises(BackendDeployError, match="new version unhealthy"):
        deploy_backend(
            config,
            service=service,
            installer=_install,
            smoke_check=smoke,
            now=lambda: datetime(2026, 7, 23, 12, tzinfo=UTC),
        )

    assert config.current_link.resolve() == old
    assert _read_database(config.database_path) == "before"
    assert smoke_attempts == 2
    assert service.events == ["stop", "start", "stop", "start"]


def test_failed_rollback_stop_never_restores_live_database_or_removes_active_version(
    tmp_path: Path,
) -> None:
    config = _config(tmp_path)
    old = config.versions_dir / "1.9.0+89"
    (old / "venv" / "bin").mkdir(parents=True)
    (old / "venv" / "bin" / "zhiji").write_text("old", encoding="utf-8")
    config.current_link.parent.mkdir(parents=True, exist_ok=True)
    config.current_link.symlink_to(old)

    class RollbackStopFailure(FakeService):
        def stop(self) -> None:
            super().stop()
            if self.events.count("stop") == 2:
                raise RuntimeError("still running")

    service = RollbackStopFailure()

    def fail_smoke() -> None:
        with sqlite3.connect(config.database_path) as connection:
            connection.execute("UPDATE state SET value = 'live-new-version'")
        raise BackendDeployError("new version unhealthy")

    with pytest.raises(BackendDeployError, match="rollback incomplete.*stop failed"):
        deploy_backend(
            config,
            service=service,
            installer=_install,
            smoke_check=fail_smoke,
            now=lambda: datetime(2026, 7, 23, 12, tzinfo=UTC),
        )

    active = config.current_link.resolve()
    assert active.name == "2.0.0+90"
    assert active.exists()
    assert _read_database(config.database_path) == "live-new-version"
    assert service.events == ["stop", "start", "stop"]


def test_launchd_plist_keeps_label_and_executes_through_current(tmp_path: Path) -> None:
    config = _config(tmp_path)

    write_launchd_plist(config)

    content = config.launchd_plist.read_text(encoding="utf-8")
    assert "<string>com.test.zhiji</string>" in content
    assert f"<string>{config.current_link}/venv/bin/zhiji</string>" in content
    assert f"<string>{config.zhiji_home}</string>" in content


def test_launchd_defaults_to_loopback_bind_and_health_origin_port(tmp_path: Path) -> None:
    config = _config(tmp_path)

    write_launchd_plist(config)

    payload = plistlib.loads(config.launchd_plist.read_bytes())
    arguments = payload["ProgramArguments"]
    assert arguments[arguments.index("--host") + 1] == "127.0.0.1"
    assert arguments[arguments.index("--port") + 1] == "19120"


@pytest.mark.parametrize("bind_host", ["0.0.0.0", "10.8.0.105", "::", "::1", "localhost"])
def test_bind_host_accepts_ip_literals_and_localhost(tmp_path: Path, bind_host: str) -> None:
    config = replace(_config(tmp_path), bind_host=bind_host)
    if bind_host not in {"::1", "localhost"}:
        _write_secure_api_token(config.zhiji_home)

    deploy_backend(
        config,
        service=FakeService(),
        installer=_install,
        smoke_check=lambda: None,
    )

    payload = plistlib.loads(config.launchd_plist.read_bytes())
    arguments = payload["ProgramArguments"]
    assert arguments[arguments.index("--host") + 1] == bind_host
    assert arguments[arguments.index("--port") + 1] == "19120"


@pytest.mark.parametrize(
    "token",
    [None, "", "   ", '"   "', "'   '"],
    ids=[
        "missing-env",
        "empty-token",
        "whitespace-token",
        "double-quoted-whitespace-token",
        "single-quoted-whitespace-token",
    ],
)
def test_public_bind_requires_secure_env_with_nonempty_api_token(
    tmp_path: Path,
    token: str | None,
) -> None:
    config = replace(_config(tmp_path), bind_host="0.0.0.0")
    if token is not None:
        _write_secure_api_token(config.zhiji_home, token)
    service = FakeService()

    match = (
        r"secure \.env is required for a non-loopback bind"
        if token is None
        else "KI_API_TOKEN"
    )
    with pytest.raises(BackendDeployError, match=match):
        deploy_backend(config, service=service, installer=_install, smoke_check=lambda: None)

    assert service.events == []
    assert not config.current_link.exists()
    assert not config.versions_dir.exists()


@pytest.mark.parametrize(
    "contents",
    [
        'KI_API_TOKEN="" # comment\n',
        'KI_API_TOKEN="" # comment ending with quote "\n',
        "KI_API_TOKEN=first-token\nKI_API_TOKEN=\n",
        "KI_API_TOKEN=${UNSET}\n",
        'KI_API_TOKEN="\\t"\n',
    ],
    ids=[
        "quoted-empty-with-comment",
        "quoted-empty-with-quote-in-comment",
        "duplicate-last-empty",
        "dotenv-interpolation",
        "quoted-backslash-escape",
    ],
)
def test_public_bind_env_parser_rejects_effectively_empty_last_token(
    tmp_path: Path,
    contents: str,
) -> None:
    config = replace(_config(tmp_path), bind_host="0.0.0.0")
    _write_secure_env_contents(config.zhiji_home, contents)
    service = FakeService()

    with pytest.raises(BackendDeployError, match="KI_API_TOKEN"):
        deploy_backend(config, service=service, installer=_install, smoke_check=lambda: None)

    assert service.events == []
    assert not config.current_link.exists()
    assert not config.versions_dir.exists()


@pytest.mark.parametrize(
    "contents",
    [
        'KI_API_TOKEN="quoted-token" # comment\n',
        "export KI_API_TOKEN=exported-token\n",
        "export\tKI_API_TOKEN=tab-exported-token\n",
        "KI_API_TOKEN=token=with=equals\n",
        "KI_API_TOKEN=\nKI_API_TOKEN=last-token\n",
    ],
    ids=[
        "quoted-with-comment",
        "export",
        "tab-export",
        "embedded-equals",
        "duplicate-last-nonempty",
    ],
)
def test_public_bind_env_parser_accepts_runtime_compatible_token_forms(
    tmp_path: Path,
    contents: str,
) -> None:
    config = replace(_config(tmp_path), bind_host="0.0.0.0")
    _write_secure_env_contents(config.zhiji_home, contents)
    service = FakeService()

    deploy_backend(config, service=service, installer=_install, smoke_check=lambda: None)

    assert service.events == ["stop", "start"]
    assert config.current_link.resolve() == config.versions_dir / "2.0.0+90"


def test_public_bind_rejects_non_regular_env_before_service_stop(tmp_path: Path) -> None:
    config = replace(_config(tmp_path), bind_host="0.0.0.0")
    (config.zhiji_home / ".env").mkdir()
    service = FakeService()

    with pytest.raises(BackendDeployError, match="regular non-symlink file"):
        deploy_backend(config, service=service, installer=_install, smoke_check=lambda: None)

    assert service.events == []
    assert not config.current_link.exists()
    assert not config.versions_dir.exists()


def test_public_bind_rejects_fifo_env_promptly(tmp_path: Path) -> None:
    config = replace(_config(tmp_path), bind_host="0.0.0.0")
    env_file = config.zhiji_home / ".env"
    os.mkfifo(env_file, mode=0o600)
    script = """
import sys
from pathlib import Path

from scripts.deploy_backend import (
    BackendDeployConfig,
    BackendDeployError,
    _validate_remote_bind_environment,
)

home = Path(sys.argv[1])
config = BackendDeployConfig(
    release_tag="v1.0.0+1",
    runtime_root=home / "runtime",
    zhiji_home=home,
    user_home=home,
    database_path=home / "database.sqlite",
    backups_dir=home / "backups",
    wheel=home / "package.whl",
    checksums=home / "SHA256SUMS",
    launchd_plist=home / "backend.plist",
    launchd_label="com.test.zhiji",
    health_origin="http://127.0.0.1:9120",
    python_executable=Path(sys.executable),
    bind_host="0.0.0.0",
)
try:
    _validate_remote_bind_environment(config)
except BackendDeployError as exc:
    raise SystemExit(0 if "regular non-symlink file" in str(exc) else 2)
raise SystemExit(3)
"""

    result = subprocess.run(
        [sys.executable, "-c", script, str(config.zhiji_home)],
        check=False,
        capture_output=True,
        text=True,
        timeout=2,
    )

    assert result.returncode == 0, result.stderr


def test_public_bind_validation_uses_opened_inode_without_following_replacement(
    tmp_path: Path,
    monkeypatch,
) -> None:
    config = replace(_config(tmp_path), bind_host="0.0.0.0")
    env_file = _write_secure_api_token(config.zhiji_home)
    replacement = tmp_path / "replacement.env"
    replacement.write_text("KI_API_TOKEN=\n", encoding="utf-8")
    replacement.chmod(0o644)
    real_open = os.open
    descriptors: list[int] = []
    opened_flags: list[int] = []

    def replace_path_after_open(path, flags):
        descriptor = real_open(path, flags)
        descriptors.append(descriptor)
        opened_flags.append(flags)
        env_file.unlink()
        env_file.symlink_to(replacement)
        return descriptor

    monkeypatch.setattr("scripts.deploy_backend.os.open", replace_path_after_open)

    _validate_remote_bind_environment(config)

    assert opened_flags
    assert opened_flags[0] & os.O_NOFOLLOW
    assert opened_flags[0] & os.O_NONBLOCK
    assert env_file.is_symlink()
    with pytest.raises(OSError):
        os.fstat(descriptors[0])


def test_public_bind_rejects_symlinked_env_before_service_stop(tmp_path: Path) -> None:
    config = replace(_config(tmp_path), bind_host="0.0.0.0")
    external = tmp_path.parent / f"{tmp_path.name}-external.env"
    external.write_text("KI_API_TOKEN=test-only-token\n", encoding="utf-8")
    external.chmod(0o600)
    (config.zhiji_home / ".env").symlink_to(external)
    service = FakeService()

    with pytest.raises(BackendDeployError, match="regular non-symlink file"):
        deploy_backend(config, service=service, installer=_install, smoke_check=lambda: None)

    assert service.events == []
    assert not config.current_link.exists()
    assert not config.versions_dir.exists()


@pytest.mark.parametrize("mode", [0o400, 0o640, 0o644, 0o660])
def test_public_bind_rejects_env_mode_other_than_0600_before_service_stop(
    tmp_path: Path,
    mode: int,
) -> None:
    config = replace(_config(tmp_path), bind_host="0.0.0.0")
    env_file = _write_secure_api_token(config.zhiji_home)
    env_file.chmod(mode)
    service = FakeService()

    with pytest.raises(BackendDeployError, match="0600"):
        deploy_backend(config, service=service, installer=_install, smoke_check=lambda: None)

    assert service.events == []
    assert not config.current_link.exists()
    assert not config.versions_dir.exists()


def test_loopback_bind_does_not_require_api_token(tmp_path: Path) -> None:
    config = _config(tmp_path)

    deploy_backend(
        config,
        service=FakeService(),
        installer=_install,
        smoke_check=lambda: None,
    )

    assert config.current_link.resolve() == config.versions_dir / "2.0.0+90"


def test_launchd_refuses_public_bind_without_secure_env(tmp_path: Path) -> None:
    config = replace(_config(tmp_path), bind_host="0.0.0.0")

    with pytest.raises(
        BackendDeployError,
        match=r"secure \.env is required for a non-loopback bind",
    ):
        write_launchd_plist(config)

    assert not config.launchd_plist.exists()


@pytest.mark.parametrize(
    "bind_host",
    ["production.internal", "http://10.8.0.105", "10.8.0.105:9120", "", "10.8.0.999"],
)
def test_bind_host_rejects_non_ip_values_before_service_stop(
    tmp_path: Path,
    bind_host: str,
) -> None:
    config = replace(_config(tmp_path), bind_host=bind_host)
    service = FakeService()

    with pytest.raises(BackendDeployError, match="bind host must be an IP literal or localhost"):
        deploy_backend(config, service=service, installer=_install, smoke_check=lambda: None)

    assert service.events == []


def test_initial_service_stop_failure_keeps_previous_runtime_untouched(tmp_path: Path) -> None:
    config = _config(tmp_path)
    old = config.versions_dir / "1.9.0+89"
    (old / "venv" / "bin").mkdir(parents=True)
    (old / "venv" / "bin" / "zhiji").write_text("old", encoding="utf-8")
    config.current_link.parent.mkdir(parents=True, exist_ok=True)
    config.current_link.symlink_to(old)

    class InitialStopFailure(FakeService):
        def stop(self) -> None:
            super().stop()
            raise RuntimeError("cannot stop")

    service = InitialStopFailure()

    with pytest.raises(BackendDeployError, match="before switch.*service stop failed"):
        deploy_backend(config, service=service, installer=_install, smoke_check=lambda: None)

    assert config.current_link.resolve() == old
    assert _read_database(config.database_path) == "before"
    assert not (config.versions_dir / "2.0.0+90").exists()
    assert service.events == ["stop"]


def test_artifact_mismatch_fails_before_service_is_stopped(tmp_path: Path) -> None:
    config = _config(tmp_path)
    config.wheel.write_bytes(b"tampered")
    service = FakeService()

    with pytest.raises(BackendDeployError, match="checksum"):
        deploy_backend(config, service=service, installer=_install, smoke_check=lambda: None)

    assert service.events == []
    assert not config.current_link.exists()


@pytest.mark.parametrize("field,value", [
    ("runtime_root", Path("outside-runtime")),
    ("backups_dir", Path("outside-backups")),
    ("launchd_plist", Path("other/com.test.zhiji.plist")),
])
def test_destructive_deployment_paths_are_restricted_to_configured_roots(
    tmp_path: Path,
    field: str,
    value: Path,
) -> None:
    config = _config(tmp_path)
    invalid = replace(config, **{field: tmp_path.parent / value})
    service = FakeService()

    with pytest.raises(BackendDeployError, match="path|plist"):
        deploy_backend(invalid, service=service, installer=_install, smoke_check=lambda: None)

    assert service.events == []


def test_database_symlink_is_rejected_before_service_stop(tmp_path: Path) -> None:
    config = _config(tmp_path)
    real_database = tmp_path / "real.sqlite"
    config.database_path.replace(real_database)
    config.database_path.symlink_to(real_database)
    service = FakeService()

    with pytest.raises(BackendDeployError, match="symbolic link"):
        deploy_backend(config, service=service, installer=_install, smoke_check=lambda: None)

    assert service.events == []


def test_managed_directory_symlink_is_rejected_before_service_stop(tmp_path: Path) -> None:
    config = _config(tmp_path)
    packages = tmp_path / "packages"
    real_packages = tmp_path / "real-packages"
    packages.rename(real_packages)
    packages.symlink_to(real_packages, target_is_directory=True)
    service = FakeService()

    with pytest.raises(BackendDeployError, match="packages directory.*symbolic link"):
        deploy_backend(config, service=service, installer=_install, smoke_check=lambda: None)

    assert service.events == []


def test_versions_directory_symlink_is_rejected_before_service_stop(tmp_path: Path) -> None:
    config = _config(tmp_path)
    config.runtime_root.mkdir()
    outside = tmp_path / "outside-versions"
    outside.mkdir()
    config.versions_dir.symlink_to(outside, target_is_directory=True)
    service = FakeService()

    with pytest.raises(BackendDeployError, match="versions directory.*symbolic link"):
        deploy_backend(config, service=service, installer=_install, smoke_check=lambda: None)

    assert service.events == []
    assert list(outside.iterdir()) == []


def test_failed_smoke_rollback_removes_sqlite_wal_sidecars(tmp_path: Path) -> None:
    config = _config(tmp_path)
    old = config.versions_dir / "1.9.0+89"
    (old / "venv" / "bin").mkdir(parents=True)
    (old / "venv" / "bin" / "zhiji").write_text("old", encoding="utf-8")
    config.current_link.parent.mkdir(parents=True, exist_ok=True)
    config.current_link.symlink_to(old)

    def fail_smoke() -> None:
        wal = config.database_path.with_name(f"{config.database_path.name}-wal")
        shm = config.database_path.with_name(f"{config.database_path.name}-shm")
        wal.write_bytes(b"failed-version-wal")
        shm.write_bytes(b"failed-version-shm")
        raise BackendDeployError("new version unhealthy")

    smoke_attempts = 0

    def fail_once() -> None:
        nonlocal smoke_attempts
        smoke_attempts += 1
        if smoke_attempts == 1:
            fail_smoke()

    with pytest.raises(BackendDeployError, match="new version unhealthy"):
        deploy_backend(
            config,
            service=FakeService(),
            installer=_install,
            smoke_check=fail_once,
        )

    assert not config.database_path.with_name(f"{config.database_path.name}-wal").exists()
    assert not config.database_path.with_name(f"{config.database_path.name}-shm").exists()
    assert _read_database(config.database_path) == "before"


def test_failed_database_replace_preserves_existing_wal_sidecars(
    tmp_path: Path,
    monkeypatch,
) -> None:
    database = tmp_path / "intelligence.sqlite"
    backup = tmp_path / "backup.sqlite"
    _database(database, "live")
    _database(backup, "backup")
    wal = database.with_name(f"{database.name}-wal")
    shm = database.with_name(f"{database.name}-shm")
    wal.write_bytes(b"live-wal")
    shm.write_bytes(b"live-shm")

    def fail_replace(_source: Path, _destination: Path) -> None:
        raise OSError("replace failed")

    monkeypatch.setattr("scripts.deploy_backend.os.replace", fail_replace)

    with pytest.raises(OSError, match="replace failed"):
        _restore_database(backup, database)

    assert wal.read_bytes() == b"live-wal"
    assert shm.read_bytes() == b"live-shm"
    assert _read_database(database) == "live"


def test_successful_deploy_retains_actual_previous_version_even_when_older_by_mtime(
    tmp_path: Path,
) -> None:
    config = _config(tmp_path)
    versions = config.versions_dir
    versions.mkdir(parents=True)
    previous = versions / "1.7.0+70"
    newer_stale = [versions / "1.8.0+80", versions / "1.9.0+89"]
    for index, entry in enumerate([previous, *newer_stale]):
        (entry / "venv" / "bin").mkdir(parents=True)
        (entry / "venv" / "bin" / "zhiji").write_text("old", encoding="utf-8")
        os.utime(entry, (1_700_000_000 + index, 1_700_000_000 + index))
    config.current_link.symlink_to(previous)

    target = deploy_backend(
        config,
        service=FakeService(),
        installer=_install,
        smoke_check=lambda: None,
        now=lambda: datetime(2026, 7, 23, 12, tzinfo=UTC),
    )

    assert previous.exists()
    assert target.exists()
    assert len([path for path in versions.iterdir() if path.is_dir()]) == 3


def test_retention_keeps_current_previous_two_and_seven_daily_backups(tmp_path: Path) -> None:
    versions = tmp_path / "versions"
    versions.mkdir()
    entries = []
    for index in range(6):
        entry = versions / f"2.0.{index}+{90 + index}"
        entry.mkdir()
        timestamp = 1_700_000_000 + index
        entry.touch()
        entry.chmod(0o755)
        os.utime(entry, (timestamp, timestamp))
        entries.append(entry)
    current = entries[-1]
    rollback = entries[1]

    prune_versions(versions, current=current, rollback_target=rollback, keep_previous=2)

    assert current.exists()
    assert rollback.exists()
    assert entries[-2].exists()
    assert not entries[-3].exists()
    assert not entries[0].exists()

    backups = tmp_path / "backups"
    backups.mkdir()
    for day in range(10):
        (backups / f"deploy-202607{day + 1:02d}-120000.sqlite").write_bytes(b"db")
        (backups / f"deploy-202607{day + 1:02d}-130000.sqlite").write_bytes(b"db")
    unrelated = backups / "rollback-manifest-keep.json"
    unrelated.write_text("{}", encoding="utf-8")

    prune_daily_backups(backups, keep_days=7)

    remaining = sorted(backups.glob("deploy-*.sqlite"))
    assert len(remaining) == 7
    assert remaining[0].name.startswith("deploy-20260704")
    assert all("130000" in path.name for path in remaining)
    assert unrelated.exists()


def test_launchd_controller_uses_configured_test_label_and_plist(tmp_path: Path) -> None:
    config = _config(tmp_path)
    commands: list[list[str]] = []

    def record(command: list[str], **kwargs) -> None:
        assert kwargs == {"check": True}
        commands.append(command)

    service = LaunchdServiceController(config, run=record, uid=501)
    service.stop()
    service.start()

    assert commands == [
        ["launchctl", "bootout", "gui/501/com.test.zhiji"],
        ["launchctl", "bootstrap", "gui/501", str(config.launchd_plist)],
    ]


def test_default_smoke_checks_liveness_database_and_core_api(monkeypatch) -> None:
    requested: list[str] = []
    payloads = {
        "/api/health": {"ok": True},
        "/api/system/health": {"ok": True, "database": {"ok": True}},
        "/api/dashboard/summary": {"today_new": 1},
    }

    class Response:
        def __init__(self, payload: dict[str, object]):
            self.payload = payload

        def __enter__(self):
            return self

        def __exit__(self, *_args) -> None:
            return None

        def read(self) -> bytes:
            return json.dumps(self.payload).encode()

    def open_url(url: str, *, timeout: int):
        assert timeout == 3
        path = url.removeprefix("http://127.0.0.1:19120")
        requested.append(path)
        return Response(payloads[path])

    monkeypatch.setattr("scripts.deploy_backend.urllib.request.urlopen", open_url)

    default_smoke_check("http://127.0.0.1:19120", timeout_seconds=1)

    assert requested == ["/api/health", "/api/system/health", "/api/dashboard/summary"]
