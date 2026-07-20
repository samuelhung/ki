from pathlib import Path
from zipfile import ZipFile

import pytest

from scripts.build_backend_wheel import verify_wheel


def _write_wheel(path: Path, names: list[str]) -> None:
    with ZipFile(path, "w") as archive:
        for name in names:
            archive.writestr(name, "fixture")


def test_verify_wheel_requires_current_production_frontend(tmp_path: Path) -> None:
    wheel = tmp_path / "zhiji_backend-2.0.0-py3-none-any.whl"
    _write_wheel(
        wheel,
        [
            "zhiji_backend/frontend_dist/index.html",
            "zhiji_backend/frontend_dist/assets/three-vendor-hash.js",
            "zhiji_backend/frontend_dist/assets/KiNavigationShell-hash.js",
            "zhiji_backend/frontend_dist/assets/CinematicBriefings-hash.js",
        ],
    )

    verify_wheel(wheel)


def test_verify_wheel_rejects_missing_briefing_workspace(tmp_path: Path) -> None:
    wheel = tmp_path / "zhiji_backend-2.0.0-py3-none-any.whl"
    _write_wheel(
        wheel,
        [
            "zhiji_backend/frontend_dist/index.html",
            "zhiji_backend/frontend_dist/assets/three-vendor-hash.js",
            "zhiji_backend/frontend_dist/assets/KiNavigationShell-hash.js",
        ],
    )

    with pytest.raises(SystemExit, match="CinematicBriefings"):
        verify_wheel(wheel)
