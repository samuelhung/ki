#!/usr/bin/env python3
"""Idempotently provision the native Zhiji systemd runtime on Ubuntu."""

from __future__ import annotations

import argparse
import os
import pwd
import re
import sqlite3
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

SERVICE_USER = "zhiji"
SERVICE_GROUP = "zhiji"
PYTHON_VERSION = "3.12.13"
UV_VERSION = "0.11.32"
IMAGEIO_FFMPEG_VERSION = "0.6.0"


class ProvisionError(RuntimeError):
    pass


@dataclass(frozen=True)
class ProvisionConfig:
    application_root: Path = Path("/srv/apps/zhiji")
    data_root: Path = Path("/data/apps/zhiji")
    backups_root: Path = Path("/data/backups/zhiji")
    env_file: Path = Path("/etc/zhiji/zhiji.env")
    unit_file: Path = Path("/etc/systemd/system/zhiji.service")
    sudoers_file: Path = Path("/etc/sudoers.d/zhiji")
    authorized_key: str = ""

    @property
    def toolchains_root(self) -> Path:
        return self.application_root / "toolchains"

    @property
    def python_executable(self) -> Path:
        return self.toolchains_root / "python/bin/python3.12"

    @property
    def ffmpeg_executable(self) -> Path:
        return self.toolchains_root / "ffmpeg/bin/ffmpeg"

    @property
    def database_path(self) -> Path:
        return self.data_root / "data/intelligence.sqlite"


class RootRunner(Protocol):
    def ensure_user(self, user: str, home: Path) -> None: ...

    def set_owner(
        self,
        path: Path,
        user: str,
        group: str,
        *,
        recursive: bool = False,
    ) -> None: ...

    def validate_sudoers(self, path: Path) -> None: ...

    def run(self, command: list[str]) -> None: ...


class ToolchainInstaller(Protocol):
    def install(self, config: ProvisionConfig, runner: RootRunner) -> None: ...


class SubprocessRootRunner:
    def ensure_user(self, user: str, home: Path) -> None:
        try:
            account = pwd.getpwnam(user)
        except KeyError:
            subprocess.run(
                [
                    "/usr/sbin/useradd",
                    "--create-home",
                    "--home-dir",
                    str(home),
                    "--shell",
                    "/bin/bash",
                    "--user-group",
                    user,
                ],
                check=True,
            )
            return
        if Path(account.pw_dir) != home or account.pw_shell != "/bin/bash":
            raise ProvisionError("existing zhiji user has an unexpected home or shell")

    def set_owner(
        self,
        path: Path,
        user: str,
        group: str,
        *,
        recursive: bool = False,
    ) -> None:
        command = ["/usr/bin/chown"]
        if recursive:
            command.append("-R")
        subprocess.run([*command, f"{user}:{group}", str(path)], check=True)

    def validate_sudoers(self, path: Path) -> None:
        subprocess.run(["/usr/sbin/visudo", "-cf", str(path)], check=True)

    def run(self, command: list[str]) -> None:
        subprocess.run(command, check=True)


class PinnedToolchainInstaller:
    def install(self, config: ProvisionConfig, runner: RootRunner) -> None:
        if config.python_executable.is_file() and config.ffmpeg_executable.is_file():
            runner.run([str(config.python_executable), "--version"])
            runner.run([str(config.ffmpeg_executable), "-version"])
            return

        bootstrap = config.toolchains_root / "bootstrap"
        bootstrap_python = bootstrap / "bin/python"
        runner.run(["/usr/bin/apt-get", "update"])
        runner.run(
            [
                "/usr/bin/apt-get",
                "install",
                "-y",
                "ca-certificates",
                "python3-venv",
            ]
        )
        runner.run(["/usr/bin/python3", "-m", "venv", str(bootstrap)])
        runner.run(
            [
                str(bootstrap_python),
                "-m",
                "pip",
                "install",
                "--disable-pip-version-check",
                f"uv=={UV_VERSION}",
            ]
        )
        managed = config.toolchains_root / "python-managed"
        runner.run(
            [
                str(bootstrap / "bin/uv"),
                "python",
                "install",
                PYTHON_VERSION,
                "--install-dir",
                str(managed),
                "--no-bin",
                "--no-progress",
            ]
        )
        python_candidates = sorted(managed.glob("cpython-3.12.13-*/bin/python3.12"))
        if len(python_candidates) != 1:
            raise ProvisionError("managed Python 3.12.13 executable is missing or ambiguous")
        _replace_symlink(config.python_executable, python_candidates[0])

        ffmpeg_environment = config.toolchains_root / "ffmpeg-python"
        ffmpeg_python = ffmpeg_environment / "bin/python"
        runner.run(
            [
                str(bootstrap / "bin/uv"),
                "venv",
                "--clear",
                "--python",
                str(python_candidates[0]),
                str(ffmpeg_environment),
            ]
        )
        runner.run(
            [
                str(bootstrap / "bin/uv"),
                "pip",
                "install",
                "--python",
                str(ffmpeg_python),
                f"imageio-ffmpeg=={IMAGEIO_FFMPEG_VERSION}",
            ]
        )

        result = subprocess.run(
            [
                str(ffmpeg_python),
                "-c",
                "import imageio_ffmpeg; print(imageio_ffmpeg.get_ffmpeg_exe())",
            ],
            check=True,
            capture_output=True,
            text=True,
        )
        ffmpeg_source = Path(result.stdout.strip())
        if not ffmpeg_source.is_file() or not os.access(ffmpeg_source, os.X_OK):
            raise ProvisionError("bundled FFmpeg executable is missing")
        _replace_symlink(config.ffmpeg_executable, ffmpeg_source)
        runner.run([str(config.python_executable), "--version"])
        runner.run([str(config.ffmpeg_executable), "-version"])


def _replace_symlink(link: Path, target: Path) -> None:
    link.parent.mkdir(parents=True, exist_ok=True)
    temporary = link.with_name(f".{link.name}.{os.getpid()}")
    temporary.unlink(missing_ok=True)
    temporary.symlink_to(target)
    os.replace(temporary, link)


def _ensure_directory(path: Path, mode: int) -> None:
    if path.is_symlink():
        raise ProvisionError(f"managed directory must not be a symlink: {path}")
    path.mkdir(parents=True, exist_ok=True)
    if not path.is_dir():
        raise ProvisionError(f"managed path is not a directory: {path}")
    path.chmod(mode)


def _atomic_write(path: Path, payload: bytes, mode: int) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.is_symlink():
        raise ProvisionError(f"managed file must not be a symlink: {path}")
    if path.is_file() and path.read_bytes() == payload:
        path.chmod(mode)
        return
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


def _validate_authorized_key(value: str) -> str:
    value = value.strip()
    if "\n" in value or "\r" in value or "\x00" in value:
        raise ProvisionError("authorized key must be one line")
    parts = value.split()
    if len(parts) < 2 or parts[0] not in {"ssh-ed25519", "ssh-rsa", "ecdsa-sha2-nistp256"}:
        raise ProvisionError("authorized key format is invalid")
    if re.fullmatch(r"[A-Za-z0-9+/]+={0,2}", parts[1]) is None:
        raise ProvisionError("authorized key payload is invalid")
    return value


def render_systemd_unit(config: ProvisionConfig) -> str:
    return "\n".join(
        (
            "[Unit]",
            "Description=Zhiji Backend",
            "After=network-online.target",
            "Wants=network-online.target",
            "",
            "[Service]",
            "Type=simple",
            "User=zhiji",
            "Group=zhiji",
            f"WorkingDirectory={config.data_root}",
            f"Environment=ZHIJI_HOME={config.data_root}",
            f"Environment=KI_ENV_FILE={config.env_file}",
            (
                f"Environment=PATH={config.ffmpeg_executable.parent}:"
                "/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin"
            ),
            f"EnvironmentFile={config.env_file}",
            (
                f"ExecStart={config.application_root}/current/venv/bin/python -m "
                "zhiji_backend.cli serve --host 0.0.0.0 --port 9120"
            ),
            "Restart=on-failure",
            "RestartSec=2",
            "NoNewPrivileges=true",
            "PrivateTmp=true",
            "ProtectSystem=strict",
            "ProtectHome=true",
            f"ReadWritePaths={config.data_root} {config.backups_root}",
            "",
            "[Install]",
            "WantedBy=multi-user.target",
            "",
        )
    )


def render_sudoers() -> str:
    commands = (
        "/usr/bin/systemctl start zhiji.service",
        "/usr/bin/systemctl stop zhiji.service",
        "/usr/bin/systemctl is-active zhiji.service",
    )
    return f"zhiji ALL=(root) NOPASSWD: {', '.join(commands)}\n"


def render_ufw_commands() -> list[list[str]]:
    commands: list[list[str]] = []
    for network, comment in (
        ("10.8.0.0/24", "zhiji-overlay"),
        ("192.168.100.0/24", "zhiji-lan"),
    ):
        commands.append(
            [
                "ufw",
                "allow",
                "from",
                network,
                "to",
                "any",
                "port",
                "9120",
                "proto",
                "tcp",
                "comment",
                comment,
            ]
        )
    return commands


def _initialize_database(path: Path) -> None:
    if path.is_symlink():
        raise ProvisionError("database must not be a symlink")
    path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(path) as connection:
        if connection.execute("PRAGMA quick_check").fetchone()[0] != "ok":
            raise ProvisionError("empty database failed quick_check")
    path.chmod(0o600)


def _install_sudoers(config: ProvisionConfig, runner: RootRunner) -> None:
    config.sudoers_file.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=".zhiji-sudoers.",
        dir=config.sudoers_file.parent,
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w", encoding="ascii") as handle:
            handle.write(render_sudoers())
            handle.flush()
            os.fsync(handle.fileno())
        temporary.chmod(0o440)
        runner.validate_sudoers(temporary)
        if config.sudoers_file.is_symlink():
            raise ProvisionError("sudoers destination must not be a symlink")
        os.replace(temporary, config.sudoers_file)
    finally:
        temporary.unlink(missing_ok=True)


def provision(
    config: ProvisionConfig,
    *,
    runner: RootRunner,
    toolchains: ToolchainInstaller,
) -> None:
    key = _validate_authorized_key(config.authorized_key)
    runner.ensure_user(SERVICE_USER, config.application_root)
    for path in (
        config.application_root,
        config.application_root / "packages",
        config.application_root / "versions",
        config.application_root / "cache",
        config.toolchains_root,
        config.data_root,
        config.data_root / "data",
        config.data_root / "data/logs",
        config.backups_root,
    ):
        _ensure_directory(path, 0o750)

    ssh_dir = config.application_root / ".ssh"
    _ensure_directory(ssh_dir, 0o700)
    _atomic_write(ssh_dir / "authorized_keys", f"{key}\n".encode("ascii"), 0o600)
    if not config.env_file.exists():
        _atomic_write(config.env_file, b"", 0o600)
    elif config.env_file.is_symlink() or not config.env_file.is_file():
        raise ProvisionError("environment file must be a regular non-symlink file")
    else:
        config.env_file.chmod(0o600)
    _initialize_database(config.database_path)
    toolchains.install(config, runner)
    _atomic_write(config.unit_file, render_systemd_unit(config).encode("utf-8"), 0o644)
    _install_sudoers(config, runner)

    for path in (config.application_root, config.data_root, config.backups_root):
        runner.set_owner(path, SERVICE_USER, SERVICE_GROUP, recursive=True)
    runner.set_owner(config.env_file, SERVICE_USER, SERVICE_GROUP)
    runner.run(["/usr/bin/systemctl", "daemon-reload"])
    runner.run(["/usr/bin/systemctl", "enable", "zhiji.service"])
    for command in render_ufw_commands():
        runner.run(command)


def _read_authorized_key(path: Path) -> str:
    if path.is_symlink() or not path.is_file():
        raise ProvisionError("authorized key file must be a regular non-symlink file")
    return _validate_authorized_key(path.read_text(encoding="ascii"))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--authorized-key-file", type=Path, required=True)
    args = parser.parse_args(argv)
    if os.geteuid() != 0:
        print("systemd provisioning failed: root is required", file=sys.stderr)
        return 2
    try:
        provision(
            ProvisionConfig(authorized_key=_read_authorized_key(args.authorized_key_file)),
            runner=SubprocessRootRunner(),
            toolchains=PinnedToolchainInstaller(),
        )
    except (ProvisionError, OSError, sqlite3.Error, subprocess.CalledProcessError) as exc:
        print(f"systemd provisioning failed: {exc}", file=sys.stderr)
        return 2
    print("systemd provisioning complete")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
