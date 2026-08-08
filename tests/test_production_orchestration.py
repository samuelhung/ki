from __future__ import annotations

import os
import stat
import subprocess
from pathlib import Path

import pytest

from scripts.deploy_production import (
    SubprocessDeployRunner,
    deploy_production,
    next_release_tag,
    remote_artifact_paths,
)
from scripts.production_target import TARGET, ProductionDeployError
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


class FakeDeployRunner:
    def __init__(
        self,
        *,
        remote_versions: list[str] | None = None,
        checksum_ok: bool = True,
    ) -> None:
        self._remote_versions = remote_versions or []
        self.checksum_ok = checksum_ok
        self.events: list[str] = []

    def verify_origin_main(self) -> str:
        self.events.append("verify-origin-main")
        return "a" * 40

    def remote_preflight(self) -> list[str]:
        self.events.append("remote-preflight")
        return self._remote_versions

    def run_focused_tests(self) -> None:
        self.events.append("run-focused-tests")

    def build_wheel(self, source_sha: str) -> None:
        assert source_sha == "a" * 40
        self.events.append("build-wheel")

    def stage_sha_directory(self, source_sha: str) -> None:
        assert source_sha == "a" * 40
        self.events.append("stage-sha-directory")

    def upload_artifacts(self) -> None:
        self.events.append("upload-artifacts")

    def verify_checksums(self) -> None:
        self.events.append("verify-checksums")
        if not self.checksum_ok:
            raise ProductionDeployError("checksum verification failed")

    def build_linux_wheelhouse(self) -> None:
        self.events.append("build-linux-wheelhouse")

    def atomic_systemd_deploy(self, tag: str) -> None:
        assert tag.startswith("v2.0.0+")
        self.events.append("atomic-systemd-deploy")

    def postflight(self, tag: str) -> None:
        assert tag.startswith("v2.0.0+")
        self.events.append("postflight")

    def stability_observation(self, seconds: int) -> None:
        assert seconds == 35
        self.events.append("stability-observation")


class FakeClock:
    def __init__(self) -> None:
        self._values = iter((100.0, 314.0))

    def __call__(self) -> float:
        return next(self._values)


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


def test_provision_identity_preflight_accepts_point_to_point_overlay_address() -> None:
    source = (ROOT / "scripts/provision_production.py").read_text(encoding="utf-8")

    assert "ip -o -4 addr show to 10.8.0.45" in source
    assert "ip -o -4 addr show to 192.168.100.163" in source
    assert "grep -F '10.8.0.45/'" not in source


def test_deploy_runs_verified_pipeline_in_order() -> None:
    runner = FakeDeployRunner(remote_versions=["2.0.0+115", "2.0.0+116"])

    result = deploy_production(runner=runner, clock=FakeClock())

    assert result.tag == "v2.0.0+117"
    assert result.duration_seconds == 214
    assert runner.events == [
        "verify-origin-main",
        "remote-preflight",
        "run-focused-tests",
        "build-wheel",
        "stage-sha-directory",
        "upload-artifacts",
        "verify-checksums",
        "build-linux-wheelhouse",
        "atomic-systemd-deploy",
        "postflight",
        "stability-observation",
    ]


def test_bad_checksum_never_stops_service() -> None:
    runner = FakeDeployRunner(checksum_ok=False)

    with pytest.raises(ProductionDeployError, match="checksum"):
        deploy_production(runner=runner, clock=FakeClock())

    assert "atomic-systemd-deploy" not in runner.events


def test_empty_new_server_continues_after_previous_production_build() -> None:
    assert next_release_tag("2.0.0", []) == "v2.0.0+115"


def test_existing_release_number_above_migration_floor_is_never_reused() -> None:
    assert next_release_tag("2.0.0", ["2.0.0+115"]) == "v2.0.0+116"


def test_release_number_floor_is_locked_to_migration_target() -> None:
    assert TARGET.previous_production_build == 114


def test_postflight_reads_service_pid_without_ungranted_sudo() -> None:
    runner = SubprocessDeployRunner()
    commands: list[str] = []
    runner._ssh = lambda command, *, stage: commands.append(command)  # type: ignore[method-assign]

    runner.postflight("v2.0.0+115")

    assert "sudo -n /usr/bin/systemctl show" not in commands[0]
    assert "/usr/bin/systemctl show -p MainPID --value zhiji.service" in commands[0]


def test_remote_artifacts_are_uploaded_to_hidden_stage_before_promotion() -> None:
    source_sha = "a" * 40

    paths = remote_artifact_paths(source_sha)

    assert paths.upload == Path("/srv/apps/zhiji/packages") / f".{source_sha}.upload"
    assert paths.final == Path("/srv/apps/zhiji/packages") / source_sha


def test_deploy_shell_entrypoint_supports_help() -> None:
    environment = os.environ.copy()
    environment.pop("PYTHONPATH", None)

    result = subprocess.run(
        [str(ROOT / "scripts/deploy-production"), "--help"],
        cwd=ROOT.parent,
        env=environment,
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stderr
    assert "deploy-production" in result.stdout
