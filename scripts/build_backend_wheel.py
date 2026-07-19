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


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--outdir", default=str(ROOT / "dist"))
    parser.add_argument("--python", default=sys.executable)
    parser.add_argument("--skip-frontend-build", action="store_true")
    args = parser.parse_args()

    outdir = Path(args.outdir).expanduser().resolve()
    outdir.mkdir(parents=True, exist_ok=True)

    if not args.skip_frontend_build:
        run(["npm", "run", "build"], FRONTEND_DIR)

    with tempfile.TemporaryDirectory(prefix="zhiji-backend-wheel-") as temp:
        build_root = copy_project_to_temp(Path(temp))
        embed_frontend_dist(build_root)
        run([args.python, "-m", "build", "--wheel", "--no-isolation", "--outdir", str(outdir)], build_root)

    wheels = sorted(outdir.glob("zhiji_backend-*.whl"), key=lambda path: path.stat().st_mtime)
    if not wheels:
        raise SystemExit(f"no wheel produced in {outdir}")
    verify_wheel(wheels[-1])
    print(wheels[-1])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
