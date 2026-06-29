"""Compatibility wrapper for the unified AI client.

Historically callers imported zhiji_backend.deepseek_client.chat. Keep that
import path stable while routing all calls through the OpenAI-compatible client.
"""

from __future__ import annotations

from .ai_client import chat

__all__ = ["chat"]
