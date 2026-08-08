from __future__ import annotations

import hashlib
import sqlite3
import stat
from pathlib import Path

from scripts.provision_backend_systemd import (
    ProvisionConfig,
    provision,
    render_ufw_commands,
)


class FakeRootRunner:
    def __init__(self) -> None:
        self.events: list[tuple[str, object]] = []

    def ensure_user(self, user: str, home: Path) -> None:
        self.events.append(("ensure-user", (user, home)))

    def set_owner(self, path: Path, user: str, group: str, *, recursive: bool = False) -> None:
        self.events.append(("set-owner", (path, user, group, recursive)))

    def validate_sudoers(self, path: Path) -> None:
        assert path.read_text(encoding="utf-8").startswith("zhiji ALL=")
        self.events.append(("validate-sudoers", path))

    def run(self, command: list[str]) -> None:
        self.events.append(("run", command))


class FakeToolchains:
    def install(self, config: ProvisionConfig, runner: FakeRootRunner) -> None:
        python = config.python_executable
        ffmpeg = config.ffmpeg_executable
        python.parent.mkdir(parents=True, exist_ok=True)
        ffmpeg.parent.mkdir(parents=True, exist_ok=True)
        python.write_text("python", encoding="utf-8")
        ffmpeg.write_text("ffmpeg", encoding="utf-8")
        python.chmod(0o755)
        ffmpeg.chmod(0o755)
        runner.events.append(("install-toolchains", config.toolchains_root))


def _config_under(tmp_path: Path) -> ProvisionConfig:
    return ProvisionConfig(
        application_root=tmp_path / "srv/apps/zhiji",
        data_root=tmp_path / "data/apps/zhiji",
        backups_root=tmp_path / "data/backups/zhiji",
        env_file=tmp_path / "etc/zhiji/zhiji.env",
        unit_file=tmp_path / "etc/systemd/system/zhiji.service",
        sudoers_file=tmp_path / "etc/sudoers.d/zhiji",
        authorized_key="ssh-ed25519 " + "A" * 48 + " test@host",
    )


def _tree_digest(root: Path) -> str:
    digest = hashlib.sha256()
    for path in sorted(root.rglob("*")):
        digest.update(path.relative_to(root).as_posix().encode("utf-8"))
        if path.is_file():
            digest.update(path.read_bytes())
            digest.update(stat.S_IMODE(path.stat().st_mode).to_bytes(2, "big"))
    return digest.hexdigest()


def test_provision_plan_separates_program_data_and_secrets(tmp_path: Path) -> None:
    config = _config_under(tmp_path)

    provision(config, runner=FakeRootRunner(), toolchains=FakeToolchains())

    assert config.application_root.is_dir()
    assert config.data_root.is_dir()
    assert config.backups_root.is_dir()
    assert stat.S_IMODE(config.env_file.stat().st_mode) == 0o600
    unit = config.unit_file.read_text(encoding="utf-8")
    assert unit.count("User=zhiji") == 1
    assert f"Environment=ZHIJI_HOME={config.data_root}" in unit
    assert f"Environment=KI_ENV_FILE={config.env_file}" in unit
    assert "--host 0.0.0.0 --port 9120" in unit


def test_provision_is_idempotent(tmp_path: Path) -> None:
    config = _config_under(tmp_path)
    runner = FakeRootRunner()

    provision(config, runner=runner, toolchains=FakeToolchains())
    first = _tree_digest(tmp_path)
    provision(config, runner=runner, toolchains=FakeToolchains())

    assert _tree_digest(tmp_path) == first


def test_provision_creates_valid_empty_sqlite_database(tmp_path: Path) -> None:
    config = _config_under(tmp_path)

    provision(config, runner=FakeRootRunner(), toolchains=FakeToolchains())

    assert stat.S_IMODE(config.database_path.stat().st_mode) == 0o600
    with sqlite3.connect(config.database_path) as connection:
        assert connection.execute("PRAGMA quick_check").fetchone()[0] == "ok"
        assert (
            connection.execute(
                "SELECT count(*) FROM sqlite_master WHERE type = 'table'"
            ).fetchone()[0]
            == 0
        )


def test_ufw_rules_allow_only_confirmed_networks() -> None:
    assert render_ufw_commands() == [
        [
            "ufw",
            "allow",
            "from",
            "10.8.0.0/24",
            "to",
            "any",
            "port",
            "9120",
            "proto",
            "tcp",
            "comment",
            "zhiji-overlay",
        ],
        [
            "ufw",
            "allow",
            "from",
            "192.168.100.0/24",
            "to",
            "any",
            "port",
            "9120",
            "proto",
            "tcp",
            "comment",
            "zhiji-lan",
        ],
    ]
