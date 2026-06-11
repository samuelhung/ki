"""News briefing generation and retrieval endpoints."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException
from ..db import connect
from ..briefing import generate_briefing, latest_briefing
from ..models import BriefingRequest

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


# ---------------------------------------------------------------------------
# Tagging endpoints
# ---------------------------------------------------------------------------

