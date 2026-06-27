"""Shared Pydantic models used across route modules."""
from __future__ import annotations

from typing import List, Optional

from pydantic import BaseModel


class CollectRequest(BaseModel):
    source_ids: Optional[List[str]] = None


class TranslateRequest(BaseModel):
    limit: int = 20


class BriefingRequest(BaseModel):
    type: str = "quick"  # 'quick' or 'daily'
    limit: int = 80
