"""System-level info API — database stats, file counts, health."""
from __future__ import annotations

import os
from pathlib import Path

from fastapi import APIRouter

from ..db import connect

router = APIRouter(prefix="/api/system", tags=["system"])

from ..paths import DATA_DIR as DATA_ROOT

TABLE_DESCRIPTIONS: dict[str, str] = {
    "events": "采集事件",
    "brainstorm_contemplate_cache": "凝神静思缓存",
    "brainstorm_questions": "头脑风暴问题",
    "brainstorm_messages": "多轮对话消息",
    "brainstorm_event_links": "问题-事件关联",
    "series": "专题系列",
    "tasks": "待办事务",
    "briefings": "情报快报",
    "digests": "每日摘要",
    "ingest_tasks": "摄入任务队列",
    "ai_usage": "AI 调用记录",
    "sources": "信息源",
    "topics": "认知分类主题",
}

FILE_LABELS: dict[str, str] = {
    "transcripts": "转写",
    "summaries": "AI 总结",
    "videos": "视频",
    "audio": "音频",
    "documents": "文档",
    "brainstorm": "脑暴问答",
    "digests": "每日摘要",
    "concepts": "概念文档",
}


def _count_files(subdir: str) -> int:
    """Count files in a data/ subdirectory (non-recursive)."""
    d = DATA_ROOT / subdir
    if not d.is_dir():
        return 0
    return sum(1 for f in d.iterdir() if f.is_file())


def _fmt_size(n_bytes: int) -> str:
    """Human-readable file size."""
    for unit in ("B", "KB", "MB", "GB"):
        if n_bytes < 1024:
            return f"{n_bytes} {unit}"
        n_bytes //= 1024
    return f"{n_bytes} TB"


@router.get("/database")
async def database_info():
    """Return database metadata + table stats + file system counts."""
    db_path = DATA_ROOT / "intelligence.sqlite"
    size_bytes = db_path.stat().st_size if db_path.exists() else 0

    # Table row counts
    tables: dict[str, dict] = {}
    try:
        with connect() as conn:
            # DB metadata
            cur = conn.execute("PRAGMA journal_mode")
            journal = cur.fetchone()[0]
            cur = conn.execute("PRAGMA page_count")
            pages = cur.fetchone()[0]
            cur = conn.execute("PRAGMA page_size")
            page_size = cur.fetchone()[0]

            # Row counts per table
            cur = conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' AND name NOT LIKE '%_fts%' ORDER BY name"
            )
            table_names = [r[0] for r in cur.fetchall()]
            for t in table_names:
                try:
                    cur = conn.execute(f'SELECT COUNT(*) FROM "{t}"')
                    tables[t] = {
                        "count": cur.fetchone()[0],
                        "desc": TABLE_DESCRIPTIONS.get(t, ""),
                    }
                except Exception:
                    tables[t] = {"count": 0, "desc": TABLE_DESCRIPTIONS.get(t, "")}
    except Exception:
        journal = "unknown"
        pages = 0
        page_size = 0

    db_size_mb = size_bytes / (1024 * 1024)

    return {
        "database": {
            "path": str(db_path),
            "file": db_path.name,
            "size_bytes": size_bytes,
            "size_display": _fmt_size(size_bytes),
            "size_mb": round(db_size_mb, 2),
            "journal_mode": journal,
            "page_count": pages,
            "page_size": page_size,
            "total_mb": round((pages * page_size) / (1024 * 1024), 2) if pages and page_size else 0,
            "tables": tables,
        },
        "files": {
            "transcripts": {"count": _count_files("ingest/transcripts"), "label": FILE_LABELS["transcripts"]},
            "summaries":   {"count": _count_files("ingest/summaries"),   "label": FILE_LABELS["summaries"]},
            "videos":      {"count": _count_files("ingest/videos"),      "label": FILE_LABELS["videos"]},
            "audio":       {"count": _count_files("ingest/audio"),       "label": FILE_LABELS["audio"]},
            "documents":   {"count": _count_files("ingest/documents"),   "label": FILE_LABELS["documents"]},
            "brainstorm":  {"count": _count_files("brainstorm"),         "label": FILE_LABELS["brainstorm"]},
            "digests":     {"count": _count_files("digests"),            "label": FILE_LABELS["digests"]},
            "concepts":    {"count": _count_files("concepts"),           "label": FILE_LABELS["concepts"]},
        },
    }
