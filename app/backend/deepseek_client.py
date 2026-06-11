"""Unified DeepSeek API client — single entry point for all backend AI calls.

Usage:
    from .deepseek_client import chat

    content = chat(messages, temperature=0.3, max_tokens=4096)
    if content is None:
        # handle error / fallback
"""

from __future__ import annotations

import json
import logging
import os
import urllib.request
from typing import Any

logger = logging.getLogger(__name__)


def chat(
    messages: list[dict[str, str]],
    temperature: float = 0.3,
    max_tokens: int = 4096,
    response_format: dict[str, str] | None = None,
    timeout: int = 120,
) -> str | None:
    """Call the DeepSeek chat completion API.

    Args:
        messages: List of message dicts with 'role' and 'content' keys.
        temperature: Sampling temperature (0–2). Lower = more deterministic.
        max_tokens: Maximum tokens in the response.
        response_format: Optional format constraint, e.g. {"type": "json_object"}.
        timeout: Request timeout in seconds.

    Returns:
        The assistant's response text, or None on any failure.
    """
    api_key = os.getenv("DEEPSEEK_API_KEY", "")
    if not api_key or api_key == "***":
        logger.warning("DeepSeek API key not configured (DEEPSEEK_API_KEY env var)")
        return None

    base_url = os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com").rstrip("/")
    url = f"{base_url}/v1/chat/completions"

    payload: dict[str, Any] = {
        "model": "deepseek-chat",
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_tokens,
    }
    if response_format:
        payload["response_format"] = response_format

    data = json.dumps(payload).encode("utf-8")

    try:
        req = urllib.request.Request(
            url,
            data=data,
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {api_key}",
            },
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = json.loads(resp.read().decode("utf-8"))
            choices = body.get("choices", [])
            if not choices:
                logger.warning("DeepSeek API returned empty choices")
                return None
            return choices[0]["message"]["content"].strip()
    except Exception as e:
        logger.warning("DeepSeek API call failed: %s", e)
        return None
