"""Shared Pydantic models used across route modules."""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from .security.constraints import SafeIdentifierList


class CollectRequest(BaseModel):
    source_ids: SafeIdentifierList | None = None


class TranslateRequest(BaseModel):
    limit: int = Field(default=20, ge=1, le=100)


class BriefingRequest(BaseModel):
    type: Literal["quick", "daily"] = "quick"
    limit: int = Field(default=80, ge=1, le=100)
