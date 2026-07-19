"""Shared Pydantic models used across route modules."""
from __future__ import annotations

from typing import List, Literal, Optional

from pydantic import BaseModel, Field


class CollectRequest(BaseModel):
    source_ids: Optional[List[str]] = None


class TranslateRequest(BaseModel):
    limit: int = 20


class BriefingRequest(BaseModel):
    type: Literal["quick", "daily"] = "quick"
    limit: int = Field(default=80, ge=1, le=200)
