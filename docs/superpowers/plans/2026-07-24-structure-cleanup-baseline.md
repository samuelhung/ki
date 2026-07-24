# Structure Cleanup Baseline Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a deterministic structural-debt baseline that prevents oversized production files and Ruff per-file suppressions from increasing while preserving all runtime behavior.

**Architecture:** A standard-library Python scanner inventories production Python/TypeScript files above 400 physical lines and normalizes Ruff per-file ignores into a checked JSON baseline. Local checks require exact baseline-to-tree equality; pull-request checks additionally compare the baseline with the target branch and reject structural regressions while allowing reductions.

**Tech Stack:** Python 3.12, `tomllib`, `json`, `subprocess`, pytest, Bash, GitHub Actions.

---

### Task 1: Structural Scanner Domain Logic

**Files:**
- Create: `scripts/check_structure_baseline.py`
- Create: `tests/test_structure_baseline.py`

- [ ] **Step 1: Write failing scanner tests**

Create `tests/test_structure_baseline.py` with focused fixtures and assertions:

```python
from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts.check_structure_baseline import (
    BaselineError,
    compare_baselines,
    load_baseline,
    scan_structure,
)


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def test_scan_records_only_oversized_production_sources_and_ruff_ignores(
    tmp_path: Path,
) -> None:
    _write(tmp_path / "src/zhiji_backend/large.py", "line\n" * 401)
    _write(tmp_path / "src/zhiji_backend/small.py", "line\n" * 400)
    _write(tmp_path / "app/frontend/src/Large.tsx", "line\n" * 402)
    _write(tmp_path / "app/frontend/src/Large.test.tsx", "line\n" * 900)
    _write(
        tmp_path / "pyproject.toml",
        '[tool.ruff.lint.per-file-ignores]\n"src/zhiji_backend/large.py" = ["F401", "E402"]\n',
    )

    assert scan_structure(tmp_path) == {
        "schema_version": 1,
        "oversized_files": {
            "app/frontend/src/Large.tsx": 402,
            "src/zhiji_backend/large.py": 401,
        },
        "ruff_per_file_ignores": {
            "src/zhiji_backend/large.py": ["E402", "F401"],
        },
    }


def test_compare_allows_reductions_and_removals() -> None:
    reference = {
        "schema_version": 1,
        "oversized_files": {"large.py": 800, "removed.py": 500},
        "ruff_per_file_ignores": {"large.py": ["E402", "F401"]},
    }
    current = {
        "schema_version": 1,
        "oversized_files": {"large.py": 700},
        "ruff_per_file_ignores": {"large.py": ["E402"]},
    }

    assert compare_baselines(current, reference) == []


def test_compare_rejects_growth_new_oversized_files_and_new_suppressions() -> None:
    reference = {
        "schema_version": 1,
        "oversized_files": {"large.py": 800},
        "ruff_per_file_ignores": {"large.py": ["E402"]},
    }
    current = {
        "schema_version": 1,
        "oversized_files": {"large.py": 801, "new.tsx": 401},
        "ruff_per_file_ignores": {
            "large.py": ["E402", "F401"],
            "new.py": ["E501"],
        },
    }

    assert compare_baselines(current, reference) == [
        "large.py: oversized file grew 800 -> 801 lines",
        "new.tsx: new oversized file has 401 lines",
        "large.py: new Ruff per-file ignore F401",
        "new.py: new Ruff per-file ignore E501",
    ]


@pytest.mark.parametrize(
    "payload",
    [
        [],
        {"schema_version": 2, "oversized_files": {}, "ruff_per_file_ignores": {}},
        {"schema_version": 1, "oversized_files": {"bad.py": 400}, "ruff_per_file_ignores": {}},
        {"schema_version": 1, "oversized_files": {}, "ruff_per_file_ignores": {"bad.py": []}},
    ],
)
def test_load_baseline_rejects_malformed_data(tmp_path: Path, payload: object) -> None:
    path = tmp_path / "baseline.json"
    path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(BaselineError):
        load_baseline(path)
```

- [ ] **Step 2: Run focused tests and verify RED**

Run:

```bash
UV_CACHE_DIR=/private/tmp/ki-uv-cache uv run --frozen pytest -q tests/test_structure_baseline.py
```

Expected: collection fails because `scripts.check_structure_baseline` does not exist.

- [ ] **Step 3: Implement the scanner domain logic**

Create `scripts/check_structure_baseline.py` with:

```python
#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
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
        if not isinstance(path, str) or not isinstance(count, int) or count <= LINE_THRESHOLD:
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


def compare_baselines(current: dict[str, Any], reference: dict[str, Any]) -> list[str]:
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
```

- [ ] **Step 4: Run focused tests and verify GREEN**

Run the focused pytest command again. Expected: all tests pass.

- [ ] **Step 5: Commit scanner domain logic**

```bash
git add scripts/check_structure_baseline.py tests/test_structure_baseline.py
git commit -m "test: define structural baseline policy"
```

### Task 2: Baseline File And Command Behavior

**Files:**
- Modify: `scripts/check_structure_baseline.py`
- Modify: `tests/test_structure_baseline.py`
- Create: `structure-baseline.json`

- [ ] **Step 1: Add failing command-behavior tests**

Extend `tests/test_structure_baseline.py` to verify:

```python
from scripts.check_structure_baseline import main


def test_main_requires_exact_checked_baseline(tmp_path: Path, capsys) -> None:
    _write(tmp_path / "src/zhiji_backend/large.py", "line\n" * 401)
    _write(tmp_path / "pyproject.toml", "[tool.ruff.lint.per-file-ignores]\n")
    (tmp_path / "structure-baseline.json").write_text(
        json.dumps({"schema_version": 1, "oversized_files": {}, "ruff_per_file_ignores": {}}),
        encoding="utf-8",
    )

    assert main(["--root", str(tmp_path)]) == 1
    assert "structure baseline is stale" in capsys.readouterr().err


def test_main_writes_deterministic_baseline(tmp_path: Path) -> None:
    _write(tmp_path / "src/zhiji_backend/large.py", "line\n" * 401)
    _write(tmp_path / "pyproject.toml", "[tool.ruff.lint.per-file-ignores]\n")

    assert main(["--root", str(tmp_path), "--write-baseline"]) == 0
    assert load_baseline(tmp_path / "structure-baseline.json")["oversized_files"] == {
        "src/zhiji_backend/large.py": 401
    }
```

- [ ] **Step 2: Run focused tests and verify RED**

Expected: import or assertion failure because `main()` is not implemented.

- [ ] **Step 3: Implement command behavior and Git comparison**

Append the following command layer. It uses `ZHIJI_STRUCTURE_BASE_REF` as the only reference environment variable. A missing baseline at a valid old commit returns no historical constraint; an invalid Git reference fails closed.

```python
def _json_text(value: dict[str, Any]) -> str:
    return f"{json.dumps(value, indent=2, sort_keys=True)}\n"


def _baseline_at_reference(root: Path, reference: str) -> dict[str, Any] | None:
    verified = subprocess.run(
        ["git", "rev-parse", "--verify", f"{reference}^{{commit}}"],
        cwd=root,
        capture_output=True,
        check=False,
        text=True,
    )
    if verified.returncode != 0:
        raise BaselineError(f"invalid structure baseline reference: {reference}")
    shown = subprocess.run(
        ["git", "show", f"{reference}:{BASELINE_NAME}"],
        cwd=root,
        capture_output=True,
        check=False,
        text=True,
    )
    if shown.returncode != 0:
        return None
    try:
        value = json.loads(shown.stdout)
    except json.JSONDecodeError as exc:
        raise BaselineError(f"invalid structure baseline at {reference}") from exc
    return _validate_baseline(value, f"structure baseline at {reference}")


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--write-baseline", action="store_true")
    return parser


def _run(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    root = args.root.resolve()
    baseline_path = root / BASELINE_NAME
    current = scan_structure(root)
    if args.write_baseline:
        baseline_path.write_text(_json_text(current), encoding="utf-8")
        print(f"wrote structure baseline: {len(current['oversized_files'])} oversized files")
        return 0

    checked = load_baseline(baseline_path)
    if checked != current:
        raise BaselineError(
            "structure baseline is stale; run "
            "python scripts/check_structure_baseline.py --write-baseline"
        )

    reference_name = os.environ.get("ZHIJI_STRUCTURE_BASE_REF", "").strip()
    if reference_name:
        reference = _baseline_at_reference(root, reference_name)
        if reference is not None:
            regressions = compare_baselines(checked, reference)
            if regressions:
                raise BaselineError("\n".join(regressions))

    ignore_count = sum(len(rules) for rules in checked["ruff_per_file_ignores"].values())
    print(
        "structure baseline ok: "
        f"{len(checked['oversized_files'])} oversized files, "
        f"{ignore_count} Ruff ignores"
    )
    return 0


def main(argv: list[str] | None = None) -> int:
    try:
        return _run(argv)
    except BaselineError as exc:
        print(f"FAIL: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 4: Run focused tests and verify GREEN**

Run:

```bash
UV_CACHE_DIR=/private/tmp/ki-uv-cache uv run --frozen pytest -q tests/test_structure_baseline.py
```

- [ ] **Step 5: Generate and verify the real baseline**

Run:

```bash
UV_CACHE_DIR=/private/tmp/ki-uv-cache uv run --frozen python scripts/check_structure_baseline.py --write-baseline
UV_CACHE_DIR=/private/tmp/ki-uv-cache uv run --frozen python scripts/check_structure_baseline.py
```

Expected: the first command writes a deterministic baseline and the second reports it is current.

- [ ] **Step 6: Commit command behavior and baseline**

```bash
git add scripts/check_structure_baseline.py tests/test_structure_baseline.py structure-baseline.json
git commit -m "build: add structural debt baseline"
```

### Task 3: Unified Gate And CI Wiring

**Files:**
- Modify: `tests/test_structure_quality_gates.py`
- Modify: `scripts/check.sh`
- Modify: `.github/workflows/zhiji-check.yml`

- [ ] **Step 1: Write failing integration assertions**

Extend `tests/test_structure_quality_gates.py`:

```python
def test_repository_check_prevents_structural_regressions() -> None:
    check_script = (ROOT / "scripts" / "check.sh").read_text(encoding="utf-8")
    assert "scripts/check_structure_baseline.py" in check_script

    workflow = (ROOT / ".github" / "workflows" / "zhiji-check.yml").read_text(
        encoding="utf-8"
    )
    assert "ZHIJI_STRUCTURE_BASE_REF: ${{ github.event.pull_request.base.sha }}" in workflow

    baseline = json.loads((ROOT / "structure-baseline.json").read_text(encoding="utf-8"))
    assert baseline["schema_version"] == 1
    assert baseline["oversized_files"]
```

- [ ] **Step 2: Run the integration test and verify RED**

Run:

```bash
UV_CACHE_DIR=/private/tmp/ki-uv-cache uv run --frozen pytest -q tests/test_structure_quality_gates.py
```

Expected: failure because `scripts/check.sh` and the workflow do not invoke the new gate.

- [ ] **Step 3: Wire the gate into local and CI checks**

Immediately after Ruff in `scripts/check.sh`, add:

```bash
echo "== Structure baseline =="
"${PYTHON_BIN[@]}" scripts/check_structure_baseline.py
```

In the existing `Run unified check` environment block, add:

```yaml
ZHIJI_STRUCTURE_BASE_REF: ${{ github.event.pull_request.base.sha }}
```

- [ ] **Step 4: Run integration and focused tests and verify GREEN**

Run both structure test files. Expected: all pass.

- [ ] **Step 5: Commit integration**

```bash
git add tests/test_structure_quality_gates.py scripts/check.sh .github/workflows/zhiji-check.yml
git commit -m "ci: enforce structural baseline"
```

### Task 4: Full Verification And Delivery

**Files:**
- Verify only; no intended source changes.

- [ ] **Step 1: Run the unified project gate**

```bash
UV_CACHE_DIR=/private/tmp/ki-uv-cache ./scripts/check.sh
```

Expected: Ruff, structure baseline, backend checks, frontend tests, typecheck, and production build all pass.

- [ ] **Step 2: Run full backend tests**

```bash
PYTHONPATH=src UV_CACHE_DIR=/private/tmp/ki-uv-cache uv run --frozen pytest -q
```

Expected: all backend tests pass with only documented pre-existing warnings.

- [ ] **Step 3: Verify diff hygiene and branch scope**

```bash
git diff --check main...HEAD
git status --short
git log --oneline main..HEAD
```

Expected: no whitespace errors, a clean worktree, and only the design, scanner, baseline, tests, and gate integration commits.

- [ ] **Step 4: Request independent code review**

Review against the approved design, focusing on baseline bypasses, Git-reference failure behavior, malformed JSON/TOML handling, path exclusions, and CI event compatibility. Fix findings with tests before delivery.

- [ ] **Step 5: Push and create a Draft PR**

```bash
git push -u origin codex/structure-cleanup-baseline
gh pr create --draft --fill --base main
```

Do not merge or deploy automatically.
