from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from scripts.check_structure_baseline import (
    BASELINE_NAME,
    BaselineError,
    _baseline_at_reference,
    compare_baselines,
    load_baseline,
    main,
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
        '[tool.ruff.lint.per-file-ignores]\n'
        '"src/zhiji_backend/large.py" = ["F401", "E402"]\n',
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
        {
            "schema_version": 2,
            "oversized_files": {},
            "ruff_per_file_ignores": {},
        },
        {
            "schema_version": 1,
            "oversized_files": {"bad.py": 400},
            "ruff_per_file_ignores": {},
        },
        {
            "schema_version": 1,
            "oversized_files": {},
            "ruff_per_file_ignores": {"bad.py": []},
        },
    ],
)
def test_load_baseline_rejects_malformed_data(
    tmp_path: Path, payload: object
) -> None:
    path = tmp_path / "baseline.json"
    path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(BaselineError):
        load_baseline(path)


def test_main_requires_exact_checked_baseline(tmp_path: Path, capsys) -> None:
    _write(tmp_path / "src/zhiji_backend/large.py", "line\n" * 401)
    _write(tmp_path / "pyproject.toml", "[tool.ruff.lint.per-file-ignores]\n")
    (tmp_path / "structure-baseline.json").write_text(
        json.dumps(
            {
                "schema_version": 1,
                "oversized_files": {},
                "ruff_per_file_ignores": {},
            }
        ),
        encoding="utf-8",
    )

    assert main(["--root", str(tmp_path)]) == 1
    assert "structure baseline is stale" in capsys.readouterr().err


def test_main_writes_deterministic_baseline(tmp_path: Path) -> None:
    _write(tmp_path / "src/zhiji_backend/large.py", "line\n" * 401)
    _write(tmp_path / "pyproject.toml", "[tool.ruff.lint.per-file-ignores]\n")

    assert main(["--root", str(tmp_path), "--write-baseline"]) == 0
    assert load_baseline(tmp_path / "structure-baseline.json")[
        "oversized_files"
    ] == {"src/zhiji_backend/large.py": 401}


def test_scan_rejects_non_list_ruff_ignores(tmp_path: Path) -> None:
    _write(
        tmp_path / "pyproject.toml",
        '[tool.ruff.lint.per-file-ignores]\n"bad.py" = "E402"\n',
    )

    with pytest.raises(BaselineError, match="must be a list of rules"):
        scan_structure(tmp_path)


def test_reference_lookup_rejects_show_failure_for_tracked_baseline(
    tmp_path: Path, monkeypatch
) -> None:
    results = iter(
        [
            SimpleNamespace(returncode=0, stdout="commit\n", stderr=""),
            SimpleNamespace(returncode=0, stdout=f"{BASELINE_NAME}\n", stderr=""),
            SimpleNamespace(returncode=1, stdout="", stderr="read failed"),
        ]
    )
    monkeypatch.setattr(
        "scripts.check_structure_baseline.subprocess.run",
        lambda *args, **kwargs: next(results),
    )

    with pytest.raises(BaselineError, match="cannot read structure baseline"):
        _baseline_at_reference(tmp_path, "base")
