"""News briefing generation and retrieval endpoints."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query
from ..briefing import (
    generate_briefing,
    get_briefing,
    latest_briefing,
    list_briefings,
)
from ..models import BriefingRequest
from ..security.constraints import MAX_OFFSET, MAX_PAGE_SIZE, SafeIdentifier

router = APIRouter()


@router.post("/api/briefing/generate")
def generate_news_briefing(request: BriefingRequest | None = None) -> dict[str, object]:
    """Generate a structured AI-powered Chinese news briefing."""
    try:
        result = generate_briefing(
            briefing_type=(request.type if request else "quick"),
            limit=(request.limit if request else 80),
        )
        return {
            "ok": True,
            "id": result["id"],
            "type": result["type"],
            "events_used": result["events_used"],
        }
    except RuntimeError as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/api/briefing/latest")
def get_latest_briefing(briefing_type: str = "quick") -> dict[str, object]:
    """Get the latest briefing of the given type."""
    result = latest_briefing(briefing_type)
    if not result:
        raise HTTPException(status_code=404, detail=f"No {briefing_type} briefing found")
    return result


@router.get("/api/briefing")
def get_briefing_history(
    limit: int = Query(30, ge=1, le=MAX_PAGE_SIZE),
    offset: int = Query(default=0, ge=0, le=MAX_OFFSET),
) -> dict[str, object]:
    """List briefings without returning their full topics payloads."""
    return list_briefings(limit=limit, offset=offset)


@router.get("/api/briefing/{briefing_id}")
def get_briefing_detail(briefing_id: SafeIdentifier) -> dict[str, object]:
    """Get one briefing with its parsed topics payload."""
    result = get_briefing(briefing_id)
    if result is None:
        raise HTTPException(status_code=404, detail="Briefing not found")
    return result


# ---------------------------------------------------------------------------
# Tagging endpoints
# ---------------------------------------------------------------------------
