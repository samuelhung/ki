"""KI project paths — single source of truth for data directories.

In Tauri release: KI_HOME env var is set by Rust to ~/Documents/KI/
In dev: falls back to project root (the app/ directory containing data/).
"""
from __future__ import annotations

import os
from pathlib import Path

_KI_HOME = os.getenv("KI_HOME", "").strip()
if _KI_HOME:
    PROJECT_ROOT = Path(_KI_HOME).expanduser().resolve()
else:
    # app/backend/paths.py → parents[1] = app/backend/ → parents[1] = app/
    PROJECT_ROOT = Path(__file__).resolve().parents[1]

DATA_DIR = PROJECT_ROOT / "data"
STUDY_DATA_DIR = DATA_DIR / "study"
INGEST_ROOT = DATA_DIR / "ingest"
BRAINSTORM_DIR = DATA_DIR / "brainstorm"
LOG_DIR = DATA_DIR / "logs"
CONFIG_PATH = DATA_DIR / "system_config.json"
DEFAULT_DB_PATH = DATA_DIR / "intelligence.sqlite"

# In Tauri: frontend dist is bundled alongside the backend
_IS_TAURI = os.getenv("KI_TAURI", "").strip() == "1"
if _IS_TAURI:
    FRONTEND_DIST = PROJECT_ROOT / "frontend" / "dist"
else:
    # dev: app/backend/paths.py → parents[1] = app/backend/ → parents[1]/frontend/dist
    FRONTEND_DIST = PROJECT_ROOT / "frontend" / "dist"
