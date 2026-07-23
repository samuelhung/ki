from __future__ import annotations

import json
import shutil
import sqlite3
import subprocess
import sys
import urllib.error
import urllib.request
from dataclasses import replace
from pathlib import Path

import pytest

from scripts.preflight_backend_deploy import (
    PreflightConfig,
    PreflightError,
    SshPreflightRunner,
    _default_open_url,
    _NoRedirect,
    main,
    preflight_backend_deploy,
    remote_preflight,
)

TOKEN = "local_remote_matching_token"


def _secure_env(path: Path, contents: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(contents, encoding="utf-8")
    path.chmod(0o600)


def _remote_tree(tmp_path: Path) -> PreflightConfig:
    runtime = tmp_path / "runtime"
    versions = runtime / "versions"
    legacy = versions / "legacy-2.0.0-pre-atomic"
    legacy.mkdir(parents=True)
    (runtime / "current").symlink_to(legacy)
    database = tmp_path / "data/intelligence.sqlite"
    database.parent.mkdir()
    with sqlite3.connect(database) as connection:
        connection.execute("CREATE TABLE check_table (value INTEGER)")
    remote_env = tmp_path / ".env"
    _secure_env(
        remote_env,
        f"OTHER=kept\nKI_API_TOKEN={TOKEN}\n"
        "KI_ALLOWED_HOSTS=10.8.0.105,127.0.0.1,localhost\n",
    )
    (tmp_path / "packages").mkdir()
    return PreflightConfig(
        local_env=tmp_path / "local.env",
        remote_env=remote_env,
        runtime_root=runtime,
        database=database,
        python_executable=Path(sys.executable),
        legacy_name="legacy-2.0.0-pre-atomic",
        target_name="2.0.0+90",
        minimum_free_bytes=1024,
        packages_root=tmp_path / "packages",
        source_sha="a" * 40,
        expect_legacy="present",
        expect_current="present",
        expect_target="absent",
    )


def test_remote_preflight_success_returns_only_safe_facts(tmp_path: Path) -> None:
    config = _remote_tree(tmp_path)

    facts = remote_preflight(
        config, TOKEN, disk_free=4096, python_version=(3, 12, 0)
    )

    assert facts["token_match"] is True
    assert facts["database"] == "ok"
    assert TOKEN not in json.dumps(facts)


def test_remote_token_mismatch_is_rejected(tmp_path: Path) -> None:
    config = _remote_tree(tmp_path)

    with pytest.raises(PreflightError, match="token mismatch"):
        remote_preflight(config, "different_token", disk_free=4096)


@pytest.mark.parametrize("unsafe", ["mode", "symlink"])
def test_remote_env_mode_or_symlink_is_rejected(tmp_path: Path, unsafe: str) -> None:
    config = _remote_tree(tmp_path)
    if unsafe == "mode":
        config.remote_env.chmod(0o644)
    else:
        real = config.remote_env.with_name("real.env")
        config.remote_env.rename(real)
        config.remote_env.symlink_to(real)

    with pytest.raises(PreflightError):
        remote_preflight(config, TOKEN, disk_free=4096)


def test_remote_allowed_hosts_must_match_exactly(tmp_path: Path) -> None:
    config = _remote_tree(tmp_path)
    _secure_env(config.remote_env, f"KI_API_TOKEN={TOKEN}\nKI_ALLOWED_HOSTS=localhost\n")

    with pytest.raises(PreflightError, match="allowed hosts"):
        remote_preflight(config, TOKEN, disk_free=4096)


def test_remote_disk_and_python_requirements_are_enforced(tmp_path: Path) -> None:
    config = _remote_tree(tmp_path)

    with pytest.raises(PreflightError, match="disk"):
        remote_preflight(config, TOKEN, disk_free=100)
    with pytest.raises(PreflightError, match="Python"):
        remote_preflight(config, TOKEN, disk_free=4096, python_version=(3, 11, 9))


def test_remote_target_expectation_can_require_published_version(tmp_path: Path) -> None:
    config = _remote_tree(tmp_path)
    target = config.versions / config.target_name
    target.mkdir()
    config = replace(config, expect_target="present")

    facts = remote_preflight(config, TOKEN, disk_free=4096, python_version=(3, 12, 0))

    assert facts["target"] == "present"


def test_first_migration_allows_missing_versions_when_all_paths_are_absent(
    tmp_path: Path,
) -> None:
    config = _remote_tree(tmp_path)
    config.current.unlink()
    shutil.rmtree(config.versions)
    config = replace(
        config,
        expect_legacy="absent",
        expect_current="absent",
        expect_target="absent",
    )

    facts = remote_preflight(config, TOKEN, disk_free=4096, python_version=(3, 12, 0))

    assert facts["legacy"] == "absent"
    assert facts["current"] == "absent"
    assert facts["target"] == "absent"


@pytest.mark.parametrize(
    ("legacy", "current", "target"),
    [("present", "absent", "absent"), ("either", "either", "either")],
)
def test_missing_versions_is_rejected_outside_first_migration_mode(
    tmp_path: Path, legacy: str, current: str, target: str
) -> None:
    config = _remote_tree(tmp_path)
    config.current.unlink()
    shutil.rmtree(config.versions)
    config = replace(
        config,
        expect_legacy=legacy,
        expect_current=current,
        expect_target=target,
    )

    with pytest.raises(PreflightError, match="versions"):
        remote_preflight(config, TOKEN, disk_free=4096, python_version=(3, 12, 0))


@pytest.mark.parametrize("unsafe", ["symlink", "file"])
def test_existing_versions_must_be_a_real_directory(tmp_path: Path, unsafe: str) -> None:
    config = _remote_tree(tmp_path)
    config.current.unlink()
    real_versions = config.runtime_root / "real-versions"
    config.versions.rename(real_versions)
    if unsafe == "symlink":
        config.versions.symlink_to(real_versions, target_is_directory=True)
    else:
        config.versions.write_text("not a directory", encoding="utf-8")
    config = replace(
        config,
        expect_legacy="absent",
        expect_current="absent",
        expect_target="absent",
    )

    with pytest.raises(PreflightError, match="versions"):
        remote_preflight(config, TOKEN, disk_free=4096, python_version=(3, 12, 0))


@pytest.mark.parametrize("unsafe", ["corrupt", "symlink"])
def test_remote_database_must_be_regular_and_pass_quick_check(
    tmp_path: Path, unsafe: str
) -> None:
    config = _remote_tree(tmp_path)
    if unsafe == "corrupt":
        config.database.write_bytes(b"not sqlite")
    else:
        real = config.database.with_name("real.sqlite")
        config.database.rename(real)
        config.database.symlink_to(real)

    with pytest.raises(PreflightError, match="database"):
        remote_preflight(config, TOKEN, disk_free=4096)


def test_local_preflight_rejects_unsafe_or_empty_token_file(tmp_path: Path) -> None:
    config = _remote_tree(tmp_path)
    _secure_env(config.local_env, "KI_REMOTE_API_TOKEN=\n")

    with pytest.raises(PreflightError, match="non-empty"):
        preflight_backend_deploy(config, lambda _payload: {})
    config.local_env.chmod(0o644)
    with pytest.raises(PreflightError, match="0600"):
        preflight_backend_deploy(config, lambda _payload: {})


def test_local_authenticated_health_uses_token_in_memory_and_checks_json(tmp_path: Path) -> None:
    config = _remote_tree(tmp_path)
    config = replace(
        config,
        health_url="http://10.8.0.105:9120/api/system/health",
        expected_health_version="2.0.0",
    )
    _secure_env(config.local_env, f"KI_REMOTE_API_TOKEN={TOKEN}\n")
    requests: list[urllib.request.Request] = []

    class Response:
        status = 200

        def __enter__(self):
            return self

        def __exit__(self, *_args) -> None:
            return None

        def read(self) -> bytes:
            return b'{"ok":true,"version":"2.0.0","database":{"ok":true}}'

    def open_request(request: urllib.request.Request, *, timeout: int):
        assert timeout == 10
        requests.append(request)
        return Response()

    facts = preflight_backend_deploy(
        config,
        lambda _payload: {"database": "ok"},
        open_url=open_request,
    )

    assert facts["authenticated_health"] == "ok"
    assert requests[0].full_url == config.health_url
    assert requests[0].headers["X-api-key"] == TOKEN


@pytest.mark.parametrize(
    "url",
    [
        "https://10.8.0.105:9120/api/system/health",
        "http://10.8.0.106:9120/api/system/health",
        "http://10.8.0.105:9121/api/system/health",
        "http://10.8.0.105:9120/api/health",
        "http://user@10.8.0.105:9120/api/system/health",
        "http://10.8.0.105:9120/api/system/health?token=x",
        "http://10.8.0.105:9120/api/system/health#fragment",
    ],
)
def test_invalid_authenticated_health_url_is_rejected_before_token_is_sent(
    tmp_path: Path, url: str
) -> None:
    config = replace(
        _remote_tree(tmp_path), health_url=url, expected_health_version="2.0.0"
    )
    _secure_env(config.local_env, f"KI_REMOTE_API_TOKEN={TOKEN}\n")
    requests: list[urllib.request.Request] = []

    with pytest.raises(PreflightError, match="health URL"):
        preflight_backend_deploy(
            config,
            lambda _payload: pytest.fail("remote runner received token"),
            open_url=lambda request, timeout: requests.append(request),
        )

    assert requests == []


def test_default_health_opener_rejects_redirects() -> None:
    handler = _NoRedirect()

    with pytest.raises(urllib.error.HTTPError):
        handler.redirect_request(
            urllib.request.Request("http://10.8.0.105:9120/api/system/health"),
            None,
            302,
            "Found",
            {"Location": "http://example.invalid/steal"},
            "http://example.invalid/steal",
        )


def test_default_health_opener_disables_proxies(monkeypatch) -> None:
    handlers: list[object] = []

    class Opener:
        def open(self, _request, *, timeout: int):
            assert timeout == 10
            return object()

    def build_opener(*configured_handlers):
        handlers.extend(configured_handlers)
        return Opener()

    monkeypatch.setattr(urllib.request, "build_opener", build_opener)

    _default_open_url(
        urllib.request.Request("http://10.8.0.105:9120/api/system/health"), timeout=10
    )

    proxy = next(handler for handler in handlers if isinstance(handler, urllib.request.ProxyHandler))
    assert proxy.proxies == {}
    assert any(isinstance(handler, _NoRedirect) for handler in handlers)


def test_authenticated_health_rejects_missing_or_mismatched_expected_version(
    tmp_path: Path,
) -> None:
    config = _remote_tree(tmp_path)
    _secure_env(config.local_env, f"KI_REMOTE_API_TOKEN={TOKEN}\n")

    class Response:
        status = 200

        def __enter__(self):
            return self

        def __exit__(self, *_args) -> None:
            return None

        def read(self) -> bytes:
            return b'{"ok":true,"version":"2.0.0","database":{"ok":true}}'

    with pytest.raises(PreflightError, match="expected health version"):
        preflight_backend_deploy(
            replace(config, health_url="http://10.8.0.105:9120/api/system/health"),
            lambda _payload: {},
            open_url=lambda _request, timeout: Response(),
        )
    with pytest.raises(PreflightError, match="version mismatch"):
        preflight_backend_deploy(
            replace(
                config,
                health_url="http://10.8.0.105:9120/api/system/health",
                expected_health_version="2.0.1",
            ),
            lambda _payload: {},
            open_url=lambda _request, timeout: Response(),
        )


def test_local_preflight_rejects_symlink_env(tmp_path: Path) -> None:
    config = _remote_tree(tmp_path)
    real = config.local_env.with_name("real.local.env")
    _secure_env(real, f"KI_REMOTE_API_TOKEN={TOKEN}\n")
    config.local_env.symlink_to(real)

    with pytest.raises(PreflightError, match="symlink"):
        preflight_backend_deploy(config, lambda _payload: {})


def test_ssh_runner_keeps_secret_out_of_argv_and_output(tmp_path: Path, capsys) -> None:
    config = _remote_tree(tmp_path)
    _secure_env(config.local_env, f"KI_REMOTE_API_TOKEN={TOKEN}\n")
    commands: list[list[str]] = []

    def fake_run(command: list[str], **kwargs):
        commands.append(command)
        assert TOKEN in kwargs["input"].decode()
        assert command[:2] == ["ssh", "test-host"]
        assert len(command) == 3
        return subprocess.CompletedProcess(command, 0, stdout=b'{"database":"ok"}', stderr=b"")

    facts = preflight_backend_deploy(
        config,
        SshPreflightRunner("test-host", config, run=fake_run),
    )

    captured = capsys.readouterr()
    assert facts == {"database": "ok"}
    assert TOKEN not in captured.out
    assert TOKEN not in captured.err
    assert all(TOKEN not in argument for command in commands for argument in command)
    assert commands[0][-1].startswith(f"{config.python_executable} -c ")


def test_ssh_stdin_worker_executes_full_remote_preflight_locally(tmp_path: Path) -> None:
    config = _remote_tree(tmp_path)
    _secure_env(config.local_env, f"KI_REMOTE_API_TOKEN={TOKEN}\n")

    def execute_loader(command: list[str], **kwargs):
        assert command[:2] == ["ssh", "test-host"]
        assert len(command) == 3
        result = subprocess.run(
            ["/bin/sh", "-c", command[-1]],
            input=kwargs["input"],
            capture_output=True,
            check=False,
        )
        assert result.returncode == 0, result.stderr.decode()
        return result

    facts = preflight_backend_deploy(
        config,
        SshPreflightRunner("test-host", config, run=execute_loader),
    )

    assert facts["database"] == "ok"
    assert facts["token_match"] is True


@pytest.mark.parametrize("python", [Path("python3"), Path("/bad\npython")])
def test_ssh_preflight_rejects_unsafe_remote_python(tmp_path: Path, python: Path) -> None:
    config = replace(_remote_tree(tmp_path), python_executable=python)

    with pytest.raises(PreflightError, match="remote Python"):
        SshPreflightRunner("test-host", config)


def test_preflight_requires_real_packages_root_and_expected_stage_state(tmp_path: Path) -> None:
    config = _remote_tree(tmp_path)

    facts = remote_preflight(config, TOKEN, disk_free=4096, python_version=(3, 12, 0))
    assert facts["artifact_stage"] == "absent"

    config.stage.mkdir()
    with pytest.raises(PreflightError, match="artifact stage.*absent"):
        remote_preflight(config, TOKEN, disk_free=4096, python_version=(3, 12, 0))

    postdeploy = replace(config, expect_stage="present")
    facts = remote_preflight(postdeploy, TOKEN, disk_free=4096, python_version=(3, 12, 0))
    assert facts["artifact_stage"] == "present"


def test_preflight_rejects_symlink_packages_root(tmp_path: Path) -> None:
    config = _remote_tree(tmp_path)
    real = tmp_path / "real-packages"
    config.packages_root.rename(real)
    config.packages_root.symlink_to(real, target_is_directory=True)

    with pytest.raises(PreflightError, match="packages"):
        remote_preflight(config, TOKEN, disk_free=4096, python_version=(3, 12, 0))


def test_cli_rejects_token_options_without_echoing_value(capsys) -> None:
    assert main(["--api-token", TOKEN]) == 2

    captured = capsys.readouterr()
    assert TOKEN not in captured.out
    assert TOKEN not in captured.err
