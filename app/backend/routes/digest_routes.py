"""Daily digest generation and retrieval endpoints."""
from __future__ import annotations

from fastapi import APIRouter
from ..digest_ai import generate_ai_digest, latest_digest

router = APIRouter()

@router.post("/api/digest/generate")
def generate_digest() -> dict[str, object]:
    return generate_ai_digest()


@router.get("/api/digest/latest")
def get_latest_digest() -> dict[str, object]:
    return latest_digest()


