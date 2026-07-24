#!/usr/bin/env python3
from __future__ import annotations

import json
import tomllib
from pathlib import Path
from typing import Any

SCHEMA_VERSION = 1
LINE_THRESHOLD = 400
BASELINE_NAME = "structure-baseline.json"
SOURCE_ROOTS = (Path("src/zhiji_backend"), Path("app/frontend/src"))
SOURCE_SUFFIXES = {".py", ".ts", ".tsx"}


class BaselineError(RuntimeError):
    pass


def _is_production_source(path: Path) -> bool:
    return (
        path.suffix in SOURCE_SUFFIXES
        and ".test." not in path.name
        and ".spec." not in path.name
        and "__pycache__" not in path.parts
    )


def _line_count(path: Path) -> int:
    return len(path.read_text(encoding="utf-8").splitlines())


def _normalized_ruff_ignores(root: Path) -> dict[str, list[str]]:
    project = tomllib.loads((root / "pyproject.toml").read_text(encoding="utf-8"))
    raw = project.get("tool", {}).get("ruff", {}).get("lint", {}).get(
        "per-file-ignores", {}
    )
    if not isinstance(raw, dict):
        raise BaselineError("Ruff per-file-ignores must be a table")
    return {
        str(path): sorted(set(rules))
        for path, rules in sorted(raw.items())
        if rules
    }


def scan_structure(root: Path) -> dict[str, Any]:
    oversized: dict[str, int] = {}
    for source_root in SOURCE_ROOTS:
        absolute_root = root / source_root
        if not absolute_root.is_dir():
            continue
        for path in sorted(absolute_root.rglob("*")):
            if not path.is_file() or not _is_production_source(path):
                continue
            count = _line_count(path)
            if count > LINE_THRESHOLD:
                oversized[path.relative_to(root).as_posix()] = count
    return {
        "schema_version": SCHEMA_VERSION,
        "oversized_files": dict(sorted(oversized.items())),
        "ruff_per_file_ignores": _normalized_ruff_ignores(root),
    }


def _validate_baseline(value: Any, label: str) -> dict[str, Any]:
    if not isinstance(value, dict) or value.get("schema_version") != SCHEMA_VERSION:
        raise BaselineError(f"{label} has an invalid schema version")
    oversized = value.get("oversized_files")
    ignores = value.get("ruff_per_file_ignores")
    if not isinstance(oversized, dict) or not isinstance(ignores, dict):
        raise BaselineError(f"{label} must contain baseline mappings")
    for path, count in oversized.items():
        if (
            not isinstance(path, str)
            or not isinstance(count, int)
            or count <= LINE_THRESHOLD
        ):
            raise BaselineError(f"{label} has an invalid oversized file entry")
    for path, rules in ignores.items():
        if (
            not isinstance(path, str)
            or not isinstance(rules, list)
            or not rules
            or any(not isinstance(rule, str) or not rule for rule in rules)
            or rules != sorted(set(rules))
        ):
            raise BaselineError(f"{label} has an invalid Ruff ignore entry")
    return value


def load_baseline(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise BaselineError(f"cannot read {path}") from exc
    return _validate_baseline(value, str(path))


def compare_baselines(
    current: dict[str, Any], reference: dict[str, Any]
) -> list[str]:
    errors: list[str] = []
    reference_files = reference["oversized_files"]
    for path, count in current["oversized_files"].items():
        previous = reference_files.get(path)
        if previous is None:
            errors.append(f"{path}: new oversized file has {count} lines")
        elif count > previous:
            errors.append(f"{path}: oversized file grew {previous} -> {count} lines")
    reference_ignores = reference["ruff_per_file_ignores"]
    for path, rules in current["ruff_per_file_ignores"].items():
        previous = set(reference_ignores.get(path, []))
        for rule in rules:
            if rule not in previous:
                errors.append(f"{path}: new Ruff per-file ignore {rule}")
    return errors
