#!/usr/bin/env python3
"""Deploy a verified Zhiji wheel through the provisioned systemd service."""

from __future__ import annotations

import argparse
import stat
import subprocess
import sys
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from scripts.deploy_backend import (
    BackendDeployConfig,
    BackendDeployError,
    default_smoke_check,
    deploy_backend,
)

APPLICATION_ROOT = Path("/srv/apps/zhiji")
DATA_ROOT = Path("/data/apps/zhiji")
BACKUPS_ROOT = Path("/data/backups/zhiji")
ENV_FILE = Path("/etc/zhiji/zhiji.env")
SERVICE_DEFINITION = Path("/etc/systemd/system/zhiji.service")
SERVICE_NAME = "zhiji.service"
PYTHON_EXECUTABLE = APPLICATION_ROOT / "toolchains/python/bin/python3.12"
HEALTH_ORIGIN = "http://127.0.0.1:9120"


@dataclass(frozen=True)
class SystemdDeployConfig:
    backend: BackendDeployConfig
    service_definition: Path = SERVICE_DEFINITION
    service_name: str = SERVICE_NAME


class SystemdServiceController:
    def __init__(
        self,
        *,
        service_name: str = SERVICE_NAME,
        run: Callable[..., object] = subprocess.run,
    ) -> None:
        self._service_name = service_name
        self._run = run

    def stop(self) -> None:
        self._run(
            ["sudo", "-n", "/usr/bin/systemctl", "stop", self._service_name],
            check=True,
        )

    def start(self) -> None:
        self._run(
            ["sudo", "-n", "/usr/bin/systemctl", "start", self._service_name],
            check=True,
        )


def build_systemd_deploy_config(
    *,
    tag: str,
    wheel: Path,
    checksums: Path,
    python_executable: Path = PYTHON_EXECUTABLE,
    application_root: Path = APPLICATION_ROOT,
    data_root: Path = DATA_ROOT,
    backups_root: Path = BACKUPS_ROOT,
    env_file: Path = ENV_FILE,
    service_definition: Path = SERVICE_DEFINITION,
) -> SystemdDeployConfig:
    backend = BackendDeployConfig(
        release_tag=tag,
        runtime_root=application_root,
        zhiji_home=data_root,
        user_home=application_root,
        database_path=data_root / "data/intelligence.sqlite",
        backups_dir=backups_root,
        wheel=wheel,
        checksums=checksums,
        launchd_plist=service_definition,
        launchd_label=SERVICE_NAME,
        health_origin=HEALTH_ORIGIN,
        python_executable=python_executable,
        bind_host="0.0.0.0",
        preserve_history=True,
        application_root=application_root,
        env_file=env_file,
    )
    return SystemdDeployConfig(backend=backend, service_definition=service_definition)


def validate_systemd_service(
    config: SystemdDeployConfig,
    *,
    enforce_production_paths: bool = False,
) -> None:
    try:
        metadata = config.service_definition.lstat()
    except FileNotFoundError as exc:
        raise BackendDeployError("systemd unit is missing") from exc
    if stat.S_ISLNK(metadata.st_mode) or not stat.S_ISREG(metadata.st_mode):
        raise BackendDeployError("systemd unit must be a regular non-symlink file")
    content = config.service_definition.read_text(encoding="utf-8")
    required = (
        "User=zhiji",
        "EnvironmentFile=/etc/zhiji/zhiji.env",
        (
            "ExecStart=/srv/apps/zhiji/current/venv/bin/python -m "
            "zhiji_backend.cli serve --host 0.0.0.0 --port 9120"
        ),
    )
    for line in required:
        label = "ExecStart" if line.startswith("ExecStart=") else line.split("=", 1)[0]
        if line not in content.splitlines():
            raise BackendDeployError(f"systemd unit {label} is invalid")
    if enforce_production_paths:
        expected = build_systemd_deploy_config(
            tag=config.backend.release_tag,
            wheel=config.backend.wheel,
            checksums=config.backend.checksums,
        )
        if config != expected:
            raise BackendDeployError("systemd deployment paths do not match production")


def _reject_command_line_secrets(argv: list[str]) -> None:
    forbidden = {"--api-token", "--ki-api-token", "--remote-api-token"}
    for argument in argv:
        if argument.partition("=")[0] in forbidden:
            raise BackendDeployError("secrets must come from /etc/zhiji/zhiji.env")


def main(argv: list[str] | None = None) -> int:
    raw_argv = list(sys.argv[1:] if argv is None else argv)
    try:
        _reject_command_line_secrets(raw_argv)
    except BackendDeployError as exc:
        print(f"systemd deployment failed: {exc}", file=sys.stderr)
        return 2
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("tag")
    parser.add_argument("--wheel", type=Path, required=True)
    parser.add_argument("--checksums", type=Path, required=True)
    args = parser.parse_args(raw_argv)
    config = build_systemd_deploy_config(
        tag=args.tag,
        wheel=args.wheel.absolute(),
        checksums=args.checksums.absolute(),
    )
    try:
        target = deploy_backend(
            config.backend,
            service=SystemdServiceController(service_name=config.service_name),
            prepare_service=lambda _backend: validate_systemd_service(
                config,
                enforce_production_paths=True,
            ),
            smoke_check=lambda: default_smoke_check(HEALTH_ORIGIN),
            rollback_smoke_check=lambda: default_smoke_check(
                HEALTH_ORIGIN,
                require_system_health=False,
            ),
        )
    except (BackendDeployError, OSError, subprocess.CalledProcessError) as exc:
        print(f"systemd deployment failed: {exc}", file=sys.stderr)
        return 2
    print(f"systemd deployment complete: {target}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
