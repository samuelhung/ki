from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from scripts.deploy_backend import BackendDeployError
from scripts.deploy_backend_systemd import (
    SystemdServiceController,
    build_systemd_deploy_config,
    validate_systemd_service,
)


def _linux_config(tmp_path: Path):
    application_root = tmp_path / "srv/apps/zhiji"
    data_root = tmp_path / "data/apps/zhiji"
    backups_root = tmp_path / "data/backups/zhiji"
    env_file = tmp_path / "etc/zhiji/zhiji.env"
    service_definition = tmp_path / "etc/systemd/system/zhiji.service"
    stage = application_root / "packages" / ("a" * 40)
    stage.mkdir(parents=True)
    data_root.mkdir(parents=True)
    backups_root.mkdir(parents=True)
    env_file.parent.mkdir(parents=True)
    env_file.write_text("KI_API_TOKEN=test-token\n", encoding="utf-8")
    env_file.chmod(0o600)
    service_definition.parent.mkdir(parents=True)
    return build_systemd_deploy_config(
        tag="v2.0.0+112",
        wheel=stage / "zhiji_backend-2.0.0-py3-none-any.whl",
        checksums=stage / "SHA256SUMS",
        python_executable=Path(sys.executable),
        application_root=application_root,
        data_root=data_root,
        backups_root=backups_root,
        env_file=env_file,
        service_definition=service_definition,
    )


def test_systemd_controller_uses_noninteractive_sudo() -> None:
    calls: list[list[str]] = []

    def run(command: list[str], *, check: bool) -> None:
        assert check is True
        calls.append(command)

    controller = SystemdServiceController(run=run)
    controller.stop()
    controller.start()

    assert calls == [
        ["sudo", "-n", "/usr/bin/systemctl", "stop", "zhiji.service"],
        ["sudo", "-n", "/usr/bin/systemctl", "start", "zhiji.service"],
    ]


def test_systemd_layout_uses_separate_program_and_data_disks(tmp_path: Path) -> None:
    config = _linux_config(tmp_path)

    assert config.backend.runtime_root == tmp_path / "srv/apps/zhiji"
    assert config.backend.zhiji_home == tmp_path / "data/apps/zhiji"
    assert config.backend.database_path == (
        tmp_path / "data/apps/zhiji/data/intelligence.sqlite"
    )
    assert config.backend.backups_dir == tmp_path / "data/backups/zhiji"
    assert config.backend.packages_dir == tmp_path / "srv/apps/zhiji/packages"
    assert config.backend.effective_env_file == tmp_path / "etc/zhiji/zhiji.env"


def test_systemd_preparer_rejects_wrong_exec_start(tmp_path: Path) -> None:
    config = _linux_config(tmp_path)
    config.service_definition.write_text(
        "\n".join(
            [
                "[Service]",
                "User=zhiji",
                "EnvironmentFile=/etc/zhiji/zhiji.env",
                "ExecStart=/bin/false",
                "",
            ]
        ),
        encoding="utf-8",
    )

    with pytest.raises(BackendDeployError, match="systemd unit ExecStart"):
        validate_systemd_service(config)


def test_systemd_preparer_accepts_expected_unit(tmp_path: Path) -> None:
    config = _linux_config(tmp_path)
    config.service_definition.write_text(
        "\n".join(
            [
                "[Service]",
                "User=zhiji",
                "EnvironmentFile=/etc/zhiji/zhiji.env",
                (
                    "ExecStart=/srv/apps/zhiji/current/venv/bin/python -m "
                    "zhiji_backend.cli serve --host 0.0.0.0 --port 9120"
                ),
                "",
            ]
        ),
        encoding="utf-8",
    )

    validate_systemd_service(config, enforce_production_paths=False)


def test_flat_staged_systemd_deployer_supports_direct_cli(tmp_path: Path) -> None:
    root = Path(__file__).resolve().parents[1]
    stage = tmp_path / "stage"
    stage.mkdir()
    for name in ("deploy_backend.py", "deploy_backend_systemd.py"):
        shutil.copy2(root / "scripts" / name, stage / name)
    environment = os.environ.copy()
    environment.pop("PYTHONPATH", None)

    result = subprocess.run(
        [sys.executable, str(stage / "deploy_backend_systemd.py"), "--help"],
        cwd=tmp_path,
        env=environment,
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stderr
    assert "--wheel" in result.stdout
