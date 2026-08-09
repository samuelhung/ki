from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
RETIRED_ENTRYPOINTS = (
    "scripts/release.sh",
    "scripts/release-check.py",
    "scripts/generate_appcast.sh",
    "scripts/install.sh",
    "desktop/scripts/build_release.py",
)
EXPECTED_README_HEADINGS = (
    "核心能力",
    "系统形态",
    "快速开始",
    "配置",
    "项目结构",
    "开发与验证",
    "生产部署",
    "数据与安全",
    "版本与发布",
    "文档",
)
README_PRIVATE_RUNTIME_PATTERN = re.compile(
    r"\b10\.\d{1,3}\.\d{1,3}\.\d{1,3}\b|"
    r"\b172\.(?:1[6-9]|2\d|3[0-1])\.\d{1,3}\.\d{1,3}\b|"
    r"\b192\.168\.\d{1,3}\.\d{1,3}\b|"
    r"\bzhiji-prod\b|\bserver-prod\b|"
    r"(?:^|[\s`(])/(?:Users|home|srv|data|opt|var|etc|root|mnt|Volumes|private|usr|tmp)/|"
    r"launchd|backend\.main:app|v1\.3\.9|当前后端/Web 生产部署|"
    r"server-prod-token|deploy-\d{8}-\d{6}\.sqlite|"
    r"(?<![A-Za-z0-9])v?\d+\.\d+\.\d+\+\d+(?![A-Za-z0-9])|"
    r"app/scripts/(?:dev|start)\.sh|docs/ARCHITECTURE\.md",
    flags=re.MULTILINE,
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


def test_readme_documents_product_workflow_and_private_runtime_boundary() -> None:
    readme = (ROOT / "README.md").read_text(encoding="utf-8")

    headings = re.findall(r"^## (.+)$", readme, flags=re.MULTILINE)
    assert headings == list(EXPECTED_README_HEADINGS)

    for required in (
        "uv sync --frozen --group dev",
        "uv run --frozen zhiji init",
        "uv run --frozen zhiji serve",
        "cd app/frontend",
        "npm ci",
        "npm run dev",
        "ZHIJI_SKIP_RELEASE_CHECK=1 ./scripts/check.sh",
        "PYTHONPATH=src uv run --frozen python -m pytest -q",
        "npm run test:cinematic-scene",
        "npm run test:cinematic-ingest",
        "npm run test:media-transport",
        "npm run typecheck",
        "npm run build",
        "KI_REMOTE_API_TOKEN",
        "启动本地后端不会自动改写该目标",
    ):
        assert required in readme

    production_section = re.search(
        r"^## 生产部署\n(?P<body>.*?)(?=^## |\Z)",
        readme,
        flags=re.MULTILINE | re.DOTALL,
    )
    assert production_section is not None
    production_body = production_section.group("body")
    assert re.search(
        r"切换阶段或 smoke check 失败时.*?尝试恢复数据库和 `current`.*?"
        r"存在上一版本时.*?尝试重启旧服务.*?恢复不完整.*?明确报错",
        production_body,
        flags=re.DOTALL,
    )
    assert re.search(
        r"postflight.*?35 秒稳定观察失败不会自动回滚.*?人工核对",
        production_body,
        flags=re.DOTALL,
    )

    api_token_row = re.search(r"^\| `KI_API_TOKEN` \|.*$", readme, flags=re.MULTILINE)
    assert api_token_row is not None
    assert "非回环监听时必须设置" in api_token_row.group()
    assert "当前标签页 `sessionStorage`" in api_token_row.group()

    remote_token_row = re.search(
        r"^\| `KI_REMOTE_API_TOKEN` \|.*$", readme, flags=re.MULTILINE
    )
    assert remote_token_row is not None
    assert "仅由 Vite 服务端代理注入请求头" in remote_token_row.group()
    assert "不下发至浏览器" in remote_token_row.group()

    links = re.findall(r"\[[^]]+\]\(([^)]+)\)", readme)
    assert {
        "desktop/changelog.json",
        "docs/superpowers/specs/2026-08-09-readme-redesign-design.md",
        "docs/superpowers/plans/2026-08-09-readme-rewrite.md",
        "scripts",
    } <= set(links)
    for target in links:
        if "://" not in target and not target.startswith("#"):
            assert (ROOT / target.split("#", maxsplit=1)[0]).exists(), target

    for retired in (
        "scripts/release-check.py",
        "pip install --force-reinstall",
        "./scripts/release.sh",
    ):
        assert retired not in readme
    assert README_PRIVATE_RUNTIME_PATTERN.search(readme) is None


def test_frontend_remote_token_file_is_ignored() -> None:
    ignored_paths = (ROOT / ".gitignore").read_text(encoding="utf-8").splitlines()

    assert "app/frontend/.env*.local" in ignored_paths


def test_readme_documents_native_production_commands_without_environment_snapshot() -> None:
    readme = (ROOT / "README.md").read_text(encoding="utf-8")

    provision_commands = re.findall(
        r"^\./scripts/provision-production(?: --dry-run)?$",
        readme,
        flags=re.MULTILINE,
    )
    assert provision_commands == [
        "./scripts/provision-production --dry-run",
        "./scripts/provision-production",
    ]
    assert re.findall(
        r"^\./scripts/deploy-production$", readme, flags=re.MULTILINE
    ) == ["./scripts/deploy-production"]

    for required in (
        "版本化 wheel",
        "systemd",
        "current",
        "SQLite 备份",
        "35 秒稳定观察",
        "锁定内部目标",
        "并非通用安装器",
        "来源工作树干净、提交已推送，且与 `origin/main` 完全一致",
    ):
        assert required in readme


@pytest.mark.parametrize(
    ("value", "is_private"),
    (
        ("10.1.2.3", True),
        ("172.16.0.1", True),
        ("172.31.255.254", True),
        ("192.168.1.2", True),
        ("/Users/yuk/project", True),
        ("/home/zhiji/app", True),
        ("/srv/apps/zhiji", True),
        ("/data/backups/zhiji", True),
        ("/etc/zhiji/env", True),
        ("/root/.config/zhiji", True),
        ("/mnt/zhiji/data", True),
        ("/Volumes/zhiji/data", True),
        ("2.1.0+123", True),
        ("v2.0.0+90", True),
        ("server-prod-token", True),
        ("deploy-20260809-120000.sqlite", True),
        ("https://example.com/data/file", False),
        ("https://example.com/Users/guide", False),
        ("产品版本 2.0.0", False),
        ("格式 X.Y.Z+N", False),
        ("desktop/changelog.json", False),
    ),
)
def test_readme_private_runtime_pattern_matches_only_sensitive_values(
    value: str, is_private: bool
) -> None:
    assert bool(README_PRIVATE_RUNTIME_PATTERN.search(value)) is is_private


def test_production_deploy_entrypoint_bootstraps_pinned_frontend_toolchain() -> None:
    source = (ROOT / "scripts" / "deploy-production").read_text(encoding="utf-8")

    assert "node@22.17.0" in source
    assert "npm@10.9.2" in source
    assert "npm exec" in source


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
        ("setuptools", "83.0.0"),
        ("wheel", "0.47.0"),
    ):
        assert f"{package}=={version}" in build_lock
        assert f'name = "{package}"' in uv_lock
        assert f'version = "{version}"' in uv_lock
    hashes = re.findall(r"--hash=sha256:([0-9a-f]{64})", build_lock)
    assert len(hashes) == 6
    assert all(digest in uv_lock for digest in hashes)
