"""知几路径 — 代码目录与数据目录彻底分离。

设计原则:
  - 代码目录: src/zhiji_backend/ → pip install 进 site-packages
  - 数据目录: ~/.zhiji/ → 用户数据，与代码完全隔离
  - 前端静态文件: 随包分发（frontend_dist/），不走数据目录

环境变量:
  ZHIJI_HOME — 数据根目录（默认 ~/.zhiji/）
"""
from __future__ import annotations

import os
from pathlib import Path


def _get_zhiji_home() -> Path:
    """数据根目录。优先 ZHIJI_HOME 环境变量，否则 ~/.zhiji/"""
    env = os.getenv("ZHIJI_HOME", "").strip()
    if env:
        return Path(env).expanduser().resolve()
    return Path.home() / ".zhiji"


# ---- 数据目录（用户数据） ----
ZHIJI_HOME = _get_zhiji_home()
DATA_DIR = ZHIJI_HOME / "data"
STUDY_DATA_DIR = DATA_DIR / "study"
INGEST_ROOT = DATA_DIR / "ingest"
BRAINSTORM_DIR = DATA_DIR / "brainstorm"
LOG_DIR = DATA_DIR / "logs"
CONFIG_PATH = DATA_DIR / "system_config.json"
RELEASES_DIR = DATA_DIR / "releases"
DEFAULT_DB_PATH = DATA_DIR / "intelligence.sqlite"

# ---- 前端静态文件（随包分发） ----
_PACKAGE_DIR = Path(__file__).resolve().parent
FRONTEND_DIST = _PACKAGE_DIR / "frontend_dist"


def ensure_data_dirs() -> None:
    """创建所有数据子目录（幂等）。数据目录不存在时自动初始化。"""
    dirs = [
        DATA_DIR,
        STUDY_DATA_DIR,
        INGEST_ROOT,
        INGEST_ROOT / "videos",
        BRAINSTORM_DIR,
        LOG_DIR,
    ]
    for d in dirs:
        d.mkdir(parents=True, exist_ok=True)
