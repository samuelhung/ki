from __future__ import annotations

import json
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_repository_check_enforces_the_pinned_ruff_baseline() -> None:
    project = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    dev_dependencies = project["dependency-groups"]["dev"]
    assert any(dependency.startswith("ruff>=0.14") for dependency in dev_dependencies)

    ruff = project["tool"]["ruff"]
    assert ruff["target-version"] == "py312"
    assert ruff["lint"]["select"] == ["E4", "E7", "E9", "F", "I", "UP"]

    check_script = (ROOT / "scripts" / "check.sh").read_text(encoding="utf-8")
    assert 'ruff check src tests scripts' in check_script


def test_repository_check_prevents_explicit_any_regressions() -> None:
    package = json.loads(
        (ROOT / "app" / "frontend" / "package.json").read_text(encoding="utf-8")
    )
    assert package["scripts"]["lint:explicit-any"] == "node scripts/check-explicit-any.mjs"

    check_script = (ROOT / "scripts" / "check.sh").read_text(encoding="utf-8")
    assert "npm run lint:explicit-any" in check_script
    assert "npm run test:quality-gates" in check_script

    workflow = (ROOT / ".github" / "workflows" / "zhiji-check.yml").read_text(
        encoding="utf-8"
    )
    assert "fetch-depth: 0" in workflow
    assert "ZHIJI_EXPLICIT_ANY_BASE_REF: ${{ github.event.pull_request.base.sha }}" in workflow

    baseline = json.loads(
        (ROOT / "app" / "frontend" / "explicit-any-baseline.json").read_text(
            encoding="utf-8"
        )
    )
    assert baseline
    assert all(path.startswith("src/") and count > 0 for path, count in baseline.items())
