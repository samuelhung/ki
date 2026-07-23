from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RETIRED_ENTRYPOINTS = (
    "scripts/release.sh",
    "scripts/release-check.py",
    "scripts/generate_appcast.sh",
    "scripts/install.sh",
    "desktop/scripts/build_release.py",
)


def test_conflicting_release_and_install_entrypoints_are_hard_disabled() -> None:
    for relative in RETIRED_ENTRYPOINTS:
        source = (ROOT / relative).read_text(encoding="utf-8")
        assert "ZHIJI_RETIRED_ENTRYPOINT" in source, relative
        assert "scripts/build_release.py" in source, relative
        assert "scripts/publish_release.py" in source, relative
        assert "scripts/deploy_backend.py" in source, relative
    assert not (ROOT / "desktop" / "deploy" / "com.zhiji.backend.plist").exists()


def test_unified_check_uses_release_preflight_instead_of_legacy_diagnostics() -> None:
    source = (ROOT / "scripts" / "check.sh").read_text(encoding="utf-8")

    assert "scripts/release_preflight.py" in source
    assert "scripts/release-check.py" not in source


def test_readme_documents_only_the_verified_release_and_atomic_deploy_flow() -> None:
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    architecture = (ROOT / "docs" / "ARCHITECTURE.md").read_text(encoding="utf-8")

    for required in (
        "scripts/build_release.py v2.0.0+90",
        "scripts/release_preflight.py v2.0.0+90",
        "scripts/publish_release.py v2.0.0+90",
        "scripts/deploy_backend.py v2.0.0+90",
        "--bind-host 0.0.0.0",
        "KI_ALLOWED_HOSTS=10.8.0.105,127.0.0.1,localhost",
        "app/frontend/.env.local",
        "runtime/versions/legacy-2.0.0-pre-atomic",
        "curl -fsS http://127.0.0.1:9120/api/health",
        "X-API-Key",
        "requirements.lock",
        "--require-hashes",
        "--no-index",
    ):
        assert required in readme
    for retired in (
        "scripts/release-check.py",
        "pip install --force-reinstall",
        "./scripts/release.sh",
    ):
        assert retired not in readme
        assert retired not in architecture

    independent_deploy = re.search(
        r"^### 后端与 Web 独立部署\n(?P<body>.*?)(?=^## )",
        readme,
        flags=re.MULTILINE | re.DOTALL,
    )
    assert independent_deploy is not None
    independent_deploy_body = independent_deploy.group("body")
    for desktop_release_entrypoint in (
        "scripts/publish_release.py",
        "scripts/build_release.py",
        "candidate-appcast",
    ):
        assert desktop_release_entrypoint not in independent_deploy_body
    for protected_remote_deploy_detail in (
        "python3 scripts/provision_remote_access.py",
        "python3 scripts/preflight_backend_deploy.py",
        "scripts/bootstrap_legacy_runtime.py",
        "packages/${SOURCE_SHA}",
        "scripts/deploy_backend.py",
        "--expected-health-version 2.0.0",
        "npm run qa:cinematic-pages -- http://10.8.0.105:9120 tmp/deploy-smoke today,ingest,system",
        "截图和 JSON 报告",
        "legacy-2.0.0-pre-atomic",
        "7 个不同日期",
        "--remote-python /Users/mrh/Documents/KI/runtime/venv/bin/python",
        "--packages-root /Users/mrh/Documents/KI/packages",
        "--source-sha \"${SOURCE_SHA}\"",
        "mkdir -m 700 '$REMOTE_STAGE'",
        "test \"$TOTAL\" = \"$DATES\"",
        "test \"$DATES\" -ge 1",
        "build_remote_wheelhouse.py",
        "--expected-machine x86_64",
        "BOOTSTRAP_SHA256SUMS",
            "plutil -extract ProgramArguments.0",
            "plutil -extract ProgramArguments.1",
            "plutil -extract ProgramArguments.2",
            "plutil -extract ProgramArguments.4",
            "plutil -extract ProgramArguments.5",
            "plutil -extract ProgramArguments.6",
            "plutil -extract ProgramArguments.7",
    ):
        assert protected_remote_deploy_detail in independent_deploy_body
    preflight_position = independent_deploy_body.index(
        "python3 scripts/preflight_backend_deploy.py"
    )
    build_position = independent_deploy_body.index("scripts/build_backend_wheel.py")
    upload_position = independent_deploy_body.index("scp ")
    assert preflight_position < build_position < upload_position
    deploy_command = re.search(
        r"deploy_backend\.py' v2\.0\.0\+90 (?P<arguments>.*?)(?=\n```)",
        independent_deploy_body,
        flags=re.DOTALL,
    )
    assert deploy_command is not None
    assert "--python /Users/mrh/Documents/KI/runtime/venv/bin/python" in deploy_command.group(
        "arguments"
    )
    assert "--wheel '${REMOTE_STAGE}/zhiji_backend-2.0.0-py3-none-any.whl'" in deploy_command.group(
        "arguments"
    )
    assert "--checksums '${REMOTE_STAGE}/SHA256SUMS'" in deploy_command.group("arguments")
    assert "python3 '${REMOTE_STAGE}/deploy_backend.py'" not in independent_deploy_body
    assert "mkdir -p '$REMOTE_STAGE'" not in independent_deploy_body
    assert "cp '${REMOTE_STAGE}/" not in independent_deploy_body
    assert "token 时只运行版本化入口" not in independent_deploy_body
    assert "grep -E -- \"runtime/current/venv/bin/zhiji|" not in independent_deploy_body
    assert "scp -r \"$OUT/wheelhouse\"" not in independent_deploy_body
    for prohibited_inline_implementation in (
        "<<'PY'",
        "secrets.token_urlsafe",
        "shutil.copytree",
        'headers={"X-API-Key": token}',
    ):
        assert prohibited_inline_implementation not in independent_deploy_body
    assert not re.search(
        r"(?m)^\s*curl\b[^\n]*/#/(?:ingest|system)(?:\s|$)",
        independent_deploy_body,
    )
    assert "127.0.0.1:9120/api/system/health" not in independent_deploy_body


def test_frontend_remote_token_file_is_ignored() -> None:
    ignored_paths = (ROOT / ".gitignore").read_text(encoding="utf-8").splitlines()

    assert "app/frontend/.env*.local" in ignored_paths


def test_backend_deployment_tools_support_documented_direct_cli_entrypoints() -> None:
    for script in (
        "scripts/provision_remote_access.py",
        "scripts/bootstrap_legacy_runtime.py",
        "scripts/preflight_backend_deploy.py",
        "scripts/build_remote_wheelhouse.py",
    ):
        subprocess.run([sys.executable, script, "--help"], cwd=ROOT, check=True)


def test_backend_build_requirements_are_hash_locked_to_uv_lock() -> None:
    build_lock = (ROOT / "scripts/backend-build-requirements.lock").read_text(encoding="ascii")
    uv_lock = (ROOT / "uv.lock").read_text(encoding="utf-8")

    for package, version in (
        ("packaging", "26.2"),
        ("setuptools", "80.10.2"),
        ("wheel", "0.47.0"),
    ):
        assert f"{package}=={version}" in build_lock
        assert f'name = "{package}"' in uv_lock
        assert f'version = "{version}"' in uv_lock
    hashes = re.findall(r"--hash=sha256:([0-9a-f]{64})", build_lock)
    assert len(hashes) == 6
    assert all(digest in uv_lock for digest in hashes)
