from __future__ import annotations

import os
import stat
import subprocess
from pathlib import Path

import pytest

from scripts.production_target import ProductionDeployError
from scripts.provision_production import provision_production

ROOT = Path(__file__).resolve().parents[1]


class FakeRemoteRunner:
    def __init__(
        self,
        *,
        confirm: str,
        legacy_env: str = "",
    ) -> None:
        self.confirm = confirm
        self.legacy_env = legacy_env.encode("utf-8")
        self.events: list[str] = []
        self.mutations: list[str] = []
        self.new_env_payload = b""

    def identity_preflight(self) -> None:
        self.events.append("identity-preflight")

    def request_confirmation(self, expected: str) -> str:
        assert expected == "server-prod 10.8.0.45"
        return self.confirm

    def read_legacy_environment(self) -> bytes:
        return self.legacy_env

    def upload_provision_helper(self) -> None:
        self.events.append("upload-provision-helper")
        self.mutations.append("upload-provision-helper")

    def execute_provision_helper(self) -> None:
        self.events.append("execute-provision-helper-as-root")
        self.mutations.append("execute-provision-helper-as-root")

    def publish_environment(self, payload: bytes) -> None:
        self.events.append("publish-environment")
        self.mutations.append("publish-environment")
        self.new_env_payload = payload

    def verify(self) -> None:
        self.events.append("verify-provisioned-runtime")


def test_provision_requires_exact_confirmation(tmp_path: Path) -> None:
    runner = FakeRemoteRunner(confirm="wrong-host")

    with pytest.raises(ProductionDeployError, match="confirmation"):
        provision_production(runner=runner, token_file=tmp_path / "token")

    assert runner.mutations == []
    assert not (tmp_path / "token").exists()


def test_provision_uploads_helper_before_root_execution(tmp_path: Path) -> None:
    runner = FakeRemoteRunner(confirm="server-prod 10.8.0.45")

    provision_production(runner=runner, token_file=tmp_path / "token")

    assert runner.events[:3] == [
        "identity-preflight",
        "upload-provision-helper",
        "execute-provision-helper-as-root",
    ]


def test_provision_migrates_allowlisted_config_without_printing_values(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    sentinel = "sentinel-volc-secret"
    runner = FakeRemoteRunner(
        confirm="server-prod 10.8.0.45",
        legacy_env=f"VOLC_API_KEY={sentinel}\nOTHER=not-migrated\n",
    )
    token_file = tmp_path / "token"

    provision_production(
        runner=runner,
        token_file=token_file,
        token_factory=lambda _length: "generated-server-prod-token",
    )

    captured = capsys.readouterr()
    assert sentinel not in captured.out + captured.err
    assert b"VOLC_API_KEY=" + sentinel.encode() in runner.new_env_payload
    assert b"OTHER=" not in runner.new_env_payload
    assert b"KI_API_TOKEN=generated-server-prod-token" in runner.new_env_payload
    assert stat.S_IMODE(token_file.stat().st_mode) == 0o600
    assert "generated-server-prod-token" not in captured.out + captured.err


def test_provision_dry_run_has_no_mutations_or_local_token(tmp_path: Path) -> None:
    runner = FakeRemoteRunner(confirm="server-prod 10.8.0.45")
    token_file = tmp_path / "token"

    provision_production(runner=runner, token_file=token_file, dry_run=True)

    assert runner.events == ["identity-preflight"]
    assert runner.mutations == []
    assert not token_file.exists()


def test_provision_reuses_existing_secure_token(tmp_path: Path) -> None:
    token_file = tmp_path / "token"
    token_file.write_text("existing-server-prod-token\n", encoding="ascii")
    token_file.chmod(0o600)
    runner = FakeRemoteRunner(confirm="server-prod 10.8.0.45")

    provision_production(
        runner=runner,
        token_file=token_file,
        token_factory=lambda _length: (_ for _ in ()).throw(
            AssertionError("token must not rotate")
        ),
    )

    assert b"KI_API_TOKEN=existing-server-prod-token" in runner.new_env_payload


def test_provision_shell_entrypoint_supports_help() -> None:
    environment = os.environ.copy()
    environment.pop("PYTHONPATH", None)
    result = subprocess.run(
        [str(ROOT / "scripts/provision-production"), "--help"],
        cwd=ROOT,
        env=environment,
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stderr
    assert "--dry-run" in result.stdout
