import sys
from pathlib import Path
from zipfile import ZipFile

import pytest

from scripts.build_backend_wheel import (
    FRONTEND_DIR,
    ROOT,
    frontend_build_commands,
    frozen_build_commands,
    select_built_wheel,
    verify_wheel,
)


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
        ],
    )

    verify_wheel(wheel)


def test_verify_wheel_rejects_missing_navigation_shell(tmp_path: Path) -> None:
    wheel = tmp_path / "zhiji_backend-2.0.0-py3-none-any.whl"
    _write_wheel(
        wheel,
        [
            "zhiji_backend/frontend_dist/index.html",
            "zhiji_backend/frontend_dist/assets/three-vendor-hash.js",
        ],
    )

    with pytest.raises(SystemExit, match="KiNavigationShell"):
        verify_wheel(wheel)


def test_frozen_build_commands_validate_and_use_the_root_environment(tmp_path: Path) -> None:
    source = tmp_path / "source"
    outdir = tmp_path / "dist"

    assert frozen_build_commands(source, outdir) == [
        (["uv", "lock", "--check"], ROOT),
        (["uv", "sync", "--frozen", "--group", "dev"], ROOT),
        (
            [
                "uv",
                "run",
                "--frozen",
                "python",
                "-m",
                "build",
                "--wheel",
                "--no-isolation",
                "--outdir",
                str(outdir),
                str(source),
            ],
            ROOT,
        ),
    ]


def test_frontend_build_commands_install_from_lock_before_building() -> None:
    assert frontend_build_commands() == [
        ([sys.executable, str(ROOT / "scripts/check_frontend_toolchain.py")], ROOT),
        (["npm", "ci"], FRONTEND_DIR),
        (["npm", "run", "build"], FRONTEND_DIR),
    ]


def test_select_built_wheel_ignores_unchanged_historical_artifacts(tmp_path: Path) -> None:
    stale = tmp_path / "zhiji_backend-1.0.0-py3-none-any.whl"
    built = tmp_path / "zhiji_backend-2.0.0-py3-none-any.whl"
    stale.write_bytes(b"stale")
    before = {stale: (stale.stat().st_mtime_ns, stale.stat().st_size)}
    built.write_bytes(b"new")

    assert select_built_wheel(tmp_path, before) == built

    with pytest.raises(SystemExit, match="exactly one wheel"):
        select_built_wheel(tmp_path, {**before, built: (built.stat().st_mtime_ns, built.stat().st_size)})
