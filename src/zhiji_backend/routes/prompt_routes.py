"""API endpoint for viewing AI prompt templates per module."""
from __future__ import annotations

import html
from fastapi import APIRouter

from ..prompt_registry import get_all_prompts

router = APIRouter(prefix="/api/system", tags=["system"])


@router.get("/prompts")
def list_prompts() -> dict:
    """Return all prompts grouped by module → task.
    Each task maps to {prompt_name: prompt_content}.
    """
    all_prompts = get_all_prompts()

    # Truncate and escape for safe frontend rendering
    result = {}
    for module, tasks in all_prompts.items():
        result[module] = {}
        for task, prompts in tasks.items():
            result[module][task] = {}
            for name, content in prompts.items():
                # Truncate to 3000 chars for frontend display
                truncated = content[:3000]
                if len(content) > 3000:
                    truncated += "\n\n... (truncated)"
                result[module][task][name] = truncated

    return {"modules": result}
