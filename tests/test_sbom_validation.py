from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from scripts.validate_sbom import validate_sbom


def _write_sbom(path: Path, purls: list[str]) -> Path:
    path.write_text(
        json.dumps(
            {
                "bomFormat": "CycloneDX",
                "specVersion": "1.6",
                "components": [{"name": f"component-{index}", "purl": purl} for index, purl in enumerate(purls)],
            }
        ),
        encoding="utf-8",
    )
    return path


def test_sbom_requires_every_locked_ecosystem(tmp_path: Path) -> None:
    complete = _write_sbom(
        tmp_path / "complete.json",
        [
            "pkg:pypi/a@1",
            "pkg:npm/b@1",
            "pkg:pub/c@1",
            "pkg:gem/d@1",
            "pkg:cocoapods/e@1",
            "pkg:maven/com.example/f@1",
        ],
    )
    assert validate_sbom(complete) == 6

    without_maven = _write_sbom(
        tmp_path / "without-maven.json",
        ["pkg:pypi/a@1", "pkg:npm/b@1", "pkg:pub/c@1", "pkg:gem/d@1", "pkg:cocoapods/e@1"],
    )
    try:
        validate_sbom(without_maven)
    except ValueError as exc:
        assert "maven" in str(exc)
    else:
        raise AssertionError("SBOM without Maven/Gradle evidence was accepted")

    incomplete = _write_sbom(tmp_path / "incomplete.json", ["pkg:npm/b@1"])
    try:
        validate_sbom(incomplete)
    except ValueError as exc:
        assert "missing ecosystems" in str(exc)
    else:
        raise AssertionError("incomplete SBOM was accepted")


def test_sbom_can_combine_source_and_gradle_evidence(tmp_path: Path) -> None:
    source = _write_sbom(
        tmp_path / "source.json",
        ["pkg:pypi/a@1", "pkg:npm/b@1", "pkg:pub/c@1", "pkg:gem/d@1", "pkg:cocoapods/e@1"],
    )
    gradle = _write_sbom(tmp_path / "gradle.json", ["pkg:maven/com.example/f@1"])

    assert validate_sbom(source, gradle) == 6


def test_sbom_rejects_missing_locked_component(tmp_path: Path) -> None:
    sbom = _write_sbom(
        tmp_path / "partial.json",
        [
            "pkg:pypi/a@1",
            "pkg:npm/b@1",
            "pkg:pub/c@1",
            "pkg:gem/d@1",
            "pkg:cocoapods/e@1",
            "pkg:maven/com.example/f@1",
        ],
    )

    try:
        validate_sbom(sbom, required_purls={"pkg:gem/d@1", "pkg:gem/missing@2"})
    except ValueError as exc:
        assert "pkg:gem/missing@2" in str(exc)
    else:
        raise AssertionError("SBOM missing a locked component was accepted")


def test_validator_cli_runs_directly_without_pythonpath(tmp_path: Path) -> None:
    root = Path(__file__).resolve().parents[1]
    sbom = _write_sbom(
        tmp_path / "complete.json",
        [
            "pkg:pypi/a@1",
            "pkg:npm/b@1",
            "pkg:pub/c@1",
            "pkg:gem/d@1",
            "pkg:cocoapods/e@1",
            "pkg:maven/com.example/f@1",
        ],
    )

    result = subprocess.run(
        [sys.executable, "scripts/validate_sbom.py", str(sbom)],
        cwd=root,
        capture_output=True,
        text=True,
        check=False,
        env={},
    )

    assert result.returncode == 0, result.stderr
