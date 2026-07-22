from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts.check_frontend_toolchain import expected_versions, validate_versions


def test_frontend_toolchain_versions_come_from_package_metadata(tmp_path: Path) -> None:
    package = tmp_path / "package.json"
    package.write_text(
        json.dumps({"engines": {"node": "22.17.0"}, "packageManager": "npm@10.9.2"}),
        encoding="utf-8",
    )

    assert expected_versions(package) == ("22.17.0", "10.9.2")


def test_frontend_toolchain_rejects_node_or_npm_drift() -> None:
    validate_versions("22.17.0", "10.9.2", "22.17.0", "10.9.2")

    with pytest.raises(ValueError, match="expected Node 22.17.0, found 26.4.0"):
        validate_versions("22.17.0", "10.9.2", "26.4.0", "10.9.2")
    with pytest.raises(ValueError, match="expected npm 10.9.2, found 11.17.0"):
        validate_versions("22.17.0", "10.9.2", "22.17.0", "11.17.0")
