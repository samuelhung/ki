"""System log viewer API — reads ki.log with level filter and pagination."""
from __future__ import annotations

import os
import re
import stat
from pathlib import Path

from fastapi import APIRouter, Query
from fastapi.responses import JSONResponse

router = APIRouter(prefix="/api/logs", tags=["logs"])

from ..paths import LOG_DIR
from ..security.redaction import redact_text
LOG_FILE = LOG_DIR / "ki.log"

# Log line pattern: 2026-06-13 14:05:30 [WARNING] module:line | message
_LOG_RE = re.compile(
    r"^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}) "
    r"\[(\w+)\s*\]\s+"
    r"(\S+?):(\d+)\s*\|\s*"
    r"(.*)$"
)

LEVEL_ORDER = {"DEBUG": 10, "INFO": 20, "WARNING": 30, "ERROR": 40, "CRITICAL": 50}


def _parse_log_lines(filepath: Path, min_level: str, limit: int) -> list[dict]:
    """Read log file backwards, parse matching lines, return newest first."""
    min_rank = LEVEL_ORDER.get(min_level.upper(), 0)
    entries: list[dict] = []

    fd: int | None = None
    try:
        nofollow = getattr(os, "O_NOFOLLOW", None)
        if nofollow is None:
            return entries
        flags = os.O_RDONLY | nofollow
        if hasattr(os, "O_CLOEXEC"):
            flags |= os.O_CLOEXEC
        fd = os.open(filepath, flags)
        if not stat.S_ISREG(os.fstat(fd).st_mode):
            return entries
        with os.fdopen(fd, "r", encoding="utf-8", closefd=True) as f:
            fd = None
            lines = f.readlines()
    except OSError:
        return entries
    finally:
        if fd is not None:
            os.close(fd)

    # Walk backwards for newest-first
    for line in reversed(lines):
        line = line.rstrip("\n")
        if not line.strip():
            continue
        m = _LOG_RE.match(line)
        if not m:
            # fallback: include as INFO with raw text
            entries.append({
                "timestamp": "",
                "level": "INFO",
                "module": "",
                "line_no": 0,
                "message": redact_text(line),
            })
            if len(entries) >= limit:
                break
            continue

        level = m.group(2)
        if LEVEL_ORDER.get(level, 0) < min_rank:
            continue

        entries.append({
            "timestamp": m.group(1),
            "level": level,
            "module": m.group(3),
            "line_no": int(m.group(4)),
            "message": redact_text(m.group(5)),
        })

        if len(entries) >= limit:
            break

    return entries


@router.get("")
async def get_logs(
    level: str = Query("INFO", description="Minimum log level (DEBUG/INFO/WARNING/ERROR)"),
    limit: int = Query(200, ge=10, le=2000, description="Max entries to return"),
    search: str = Query("", description="Filter by message substring"),
):
    """Return recent log entries, newest first. Supports level filter and text search."""
    entries = _parse_log_lines(LOG_FILE, level, limit)

    # Text search filter
    if search:
        q = search.lower()
        entries = [e for e in entries if q in e["message"].lower()]

    return JSONResponse({
        "total": len(entries),
        "level": level.upper(),
        "entries": entries,
    })
