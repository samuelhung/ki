#!/usr/bin/env python3
"""Build a backend wheel that embeds the Vite frontend dist.

The source tree keeps ``src/zhiji_backend/frontend_dist`` as a symlink to the
Vite output for local development. Setuptools can miss that symlink in release
builds, so this script builds the frontend, copies the project to a temporary
tree, replaces the symlink with real package data, builds the wheel there, and
verifies the wheel contains the static frontend.
"""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from zipfile import ZipFile


ROOT = Path(__file__).resolve().parent.parent
FRONTEND_DIR = ROOT / "app" / "frontend"
FRONTEND_DIST = FRONTEND_DIR / "dist"
PACKAGE_FRONTEND_DIST = Path("src/zhiji_backend/frontend_dist")

IGNORE_DIRS = {
    ".git",
    ".pytest_cache",
    ".venv",
    ".venv-verify",
    "__pycache__",
    "build",
    "dist",
    "node_modules",
}


def run(cmd: list[str], cwd: Path) -> None:
    print(f"+ {' '.join(cmd)}", flush=True)
    subprocess.run(cmd, cwd=cwd, check=True)


def ignore_names(_: str, names: list[str]) -> set[str]:
    return {name for name in names if name in IGNORE_DIRS or name.endswith(".egg-info")}


def copy_project_to_temp(temp_root: Path) -> Path:
    build_root = temp_root / "ki"
    shutil.copytree(ROOT, build_root, ignore=ignore_names, symlinks=True)
    return build_root


def embed_frontend_dist(build_root: Path) -> None:
    if not (FRONTEND_DIST / "index.html").is_file():
        raise SystemExit(f"frontend dist missing: {FRONTEND_DIST}")

    package_dist = build_root / PACKAGE_FRONTEND_DIST
    if package_dist.is_symlink() or package_dist.exists():
        if package_dist.is_dir() and not package_dist.is_symlink():
            shutil.rmtree(package_dist)
        else:
            package_dist.unlink()
    shutil.copytree(FRONTEND_DIST, package_dist)


def verify_wheel(wheel: Path) -> None:
    with ZipFile(wheel) as zf:
        names = zf.namelist()

    required = [
        "zhiji_backend/frontend_dist/index.html",
        "three-vendor",
        "KiNavigationShell",
        "CinematicBriefings",
    ]
    missing = [needle for needle in required if not any(needle in name for name in names)]
    if missing:
        raise SystemExit(f"wheel is missing required frontend files: {', '.join(missing)}")

    print(f"verified frontend files in {wheel.name}")


def frozen_build_commands(build_root: Path, outdir: Path) -> list[tuple[list[str], Path]]:
    return [
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
                str(build_root),
            ],
            ROOT,
        ),
    ]


def frontend_build_commands() -> list[tuple[list[str], Path]]:
    return [
        ([sys.executable, str(ROOT / "scripts/check_frontend_toolchain.py")], ROOT),
        (["npm", "ci"], FRONTEND_DIR),
        (["npm", "run", "build"], FRONTEND_DIR),
    ]


def wheel_snapshot(outdir: Path) -> dict[Path, tuple[int, int]]:
    return {path: (path.stat().st_mtime_ns, path.stat().st_size) for path in outdir.glob("zhiji_backend-*.whl")}


def select_built_wheel(outdir: Path, before: dict[Path, tuple[int, int]]) -> Path:
    changed = [
        path
        for path in outdir.glob("zhiji_backend-*.whl")
        if before.get(path) != (path.stat().st_mtime_ns, path.stat().st_size)
    ]
    if len(changed) != 1:
        raise SystemExit(f"expected exactly one wheel from this build, found {len(changed)}")
    return changed[0]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--outdir", default=str(ROOT / "dist"))
    args = parser.parse_args()

    outdir = Path(args.outdir).expanduser().resolve()
    outdir.mkdir(parents=True, exist_ok=True)
    before = wheel_snapshot(outdir)

    for command, cwd in frontend_build_commands():
        run(command, cwd)

    with tempfile.TemporaryDirectory(prefix="zhiji-backend-wheel-") as temp:
        build_root = copy_project_to_temp(Path(temp))
        embed_frontend_dist(build_root)
        for command, cwd in frozen_build_commands(build_root, outdir):
            run(command, cwd)

    wheel = select_built_wheel(outdir, before)
    verify_wheel(wheel)
    print(wheel)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
