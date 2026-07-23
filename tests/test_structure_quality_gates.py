from __future__ import annotations

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
