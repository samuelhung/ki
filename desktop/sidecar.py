#!/usr/bin/env python3
"""KI Desktop sidecar — 由 Tauri 启动 Python 后端"""

import os
import sys
import json
import signal
import subprocess
from pathlib import Path


def find_python():
    """Find the Python interpreter in the project's venv"""
    project_root = Path(__file__).resolve().parents[3]  # desktop/sidecar.py -> project root
    venv_python = project_root / "app" / ".venv" / "bin" / "python3"
    if venv_python.exists():
        return str(venv_python)
    return sys.executable


def main():
    project_root = Path(__file__).resolve().parents[3]
    backend_dir = project_root / "app" / "backend"
    python = find_python()

    # Set environment for the backend
    env = os.environ.copy()
    env.setdefault("KI_DATA_DIR", str(project_root / "data"))
    env.setdefault("KI_PORT", "9120")
    env.setdefault("KI_HOST", "127.0.0.1")

    # Signal handling: forward SIGTERM/SIGINT to child
    proc = subprocess.Popen(
        [python, "-m", "uvicorn", "backend.main:app",
         "--host", env["KI_HOST"],
         "--port", env["KI_PORT"]],
        cwd=str(backend_dir.parent),  # app/
        env=env,
        stdout=sys.stdout,
        stderr=sys.stderr,
    )

    def handle_signal(signum, frame):
        proc.terminate()
        proc.wait()
        sys.exit(0)

    signal.signal(signal.SIGTERM, handle_signal)
    signal.signal(signal.SIGINT, handle_signal)

    # Write ready signal to stdout (Tauri reads this)
    print(f"KI_BACKEND_READY port={env['KI_PORT']}", flush=True)

    proc.wait()
    sys.exit(proc.returncode)


if __name__ == "__main__":
    main()
