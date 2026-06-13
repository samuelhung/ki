"""Unified DeepSeek API client — single entry point for all backend AI calls.

Reads defaults from system_config.json via config_manager. Every call can
override temperature/max_tokens/model/etc.

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
import threading
import time
import urllib.request
from typing import Any

from .config_manager import get_config

logger = logging.getLogger(__name__)


def _record_usage(
    module: str | None,
    task: str | None,
    model: str,
    status: str,
    usage: dict | None,
    elapsed_ms: int,
    error: str = "",
) -> None:
    """Write an ai_usage row in a background thread — never blocks the caller."""
    try:
        prompt_tokens = usage.get("prompt_tokens", 0) if usage else 0
        completion_tokens = usage.get("completion_tokens", 0) if usage else 0
        total_tokens = usage.get("total_tokens", 0) if usage else 0
        cached_tokens = (usage.get("prompt_tokens_details", {}) or {}).get("cached_tokens", 0) if usage else 0
        reasoning_tokens = (usage.get("completion_tokens_details", {}) or {}).get("reasoning_tokens", 0) if usage else 0

        # Cost: input 3元/M, cache hit 0.025元/M, output 6元/M, reasoning free
        non_cached = prompt_tokens - cached_tokens
        cost = non_cached * 3 / 1_000_000 + cached_tokens * 0.025 / 1_000_000 + completion_tokens * 6 / 1_000_000
    except Exception:
        prompt_tokens = completion_tokens = total_tokens = cached_tokens = reasoning_tokens = 0
        cost = 0

    def _write() -> None:
        try:
            import sqlite3
            from pathlib import Path
            db_path = Path(__file__).resolve().parents[2] / "data" / "intelligence.sqlite"
            conn = sqlite3.connect(str(db_path))
            conn.execute(
                """INSERT INTO ai_usage
                   (module, task, model, status, prompt_tokens, completion_tokens, total_tokens,
                    cached_tokens, reasoning_tokens, cost_rmb, duration_ms, error)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (module or "", task or "", model, status, prompt_tokens, completion_tokens,
                 total_tokens, cached_tokens, reasoning_tokens, round(cost, 6), elapsed_ms, error),
            )
            conn.commit()
            conn.close()
        except Exception:
            pass  # never let usage logging break the caller

    threading.Thread(target=_write, daemon=True).start()


def chat(
    messages: list[dict[str, str]],
    temperature: float | None = None,
    max_tokens: int | None = None,
    response_format: dict[str, str] | None = None,
    timeout: int = 120,
    *,
    module: str | None = None,
    task: str | None = None,
    model: str | None = None,
    thinking: bool | None = None,
    reasoning_effort: str | None = None,
) -> str | None:
    """Call the DeepSeek chat completion API.

    All parameters are optional — falls back to system_config.json defaults, then
    hardcoded fallbacks.

    Args:
        messages: List of message dicts with 'role' and 'content' keys.
        temperature: Sampling temperature (0–2). Lower = more deterministic.
        max_tokens: Maximum tokens in the response.
        response_format: Optional format constraint, e.g. {"type": "json_object"}.
        timeout: Request timeout in seconds.
        module: Config module key (e.g. "series") for per-task defaults.
        task: Config task key within module (e.g. "paper") for per-task defaults.
        model: Override the model name.
        thinking: Override thinking mode (True = enabled).
        reasoning_effort: Override reasoning effort ("high" / "max").

    Returns:
        The assistant's response text, or None on any failure.
    """
    cfg = get_config()
    general = cfg.get("general", {})

    # Resolve from config if module+task provided
    mod_defaults: dict = {}
    if module and module in cfg and isinstance(cfg[module], dict):
        mod_tasks = cfg[module]
        if task and task in mod_tasks and isinstance(mod_tasks[task], dict):
            mod_defaults = mod_tasks[task]
        else:
            mod_defaults = {}

    # Resolve each parameter: explicit arg > module+task config > general config > hardcoded fallback
    _model = model or general.get("model", "deepseek-v4-pro")
    _base_url = general.get("base_url", "https://api.deepseek.com").rstrip("/")
    _temperature = temperature if temperature is not None else mod_defaults.get("temperature", general.get("default_temperature", 0.3))
    _max_tokens = max_tokens if max_tokens is not None else mod_defaults.get("max_tokens", general.get("default_max_tokens", 2048))
    _thinking = thinking if thinking is not None else general.get("thinking", False)
    _reasoning_effort = reasoning_effort or general.get("reasoning_effort", "high")

    # API key: env var (for cron/CLI) overrides config
    _api_key = os.getenv("DEEPSEEK_API_KEY", "") or general.get("api_key", "")
    if not _api_key or _api_key == "***":
        logger.warning("DeepSeek API key not configured")
        return None

    url = f"{_base_url}/chat/completions"

    payload: dict[str, Any] = {
        "model": _model,
        "messages": messages,
        "temperature": _temperature,
        "max_tokens": _max_tokens,
    }
    if response_format:
        payload["response_format"] = response_format
    if _thinking:
        payload["thinking"] = {"type": "enabled"}
        payload["reasoning_effort"] = _reasoning_effort
    else:
        payload["thinking"] = {"type": "disabled"}

    data = json.dumps(payload).encode("utf-8")

    try:
        t0 = time.monotonic()
        req = urllib.request.Request(
            url,
            data=data,
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {_api_key}",
            },
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = json.loads(resp.read().decode("utf-8"))
        elapsed = int((time.monotonic() - t0) * 1000)

        choices = body.get("choices", [])
        if not choices:
            logger.warning("DeepSeek API returned empty choices")
            _record_usage(module, task, _model, "error", body.get("usage"), elapsed, "empty choices")
            return None

        content = choices[0]["message"]["content"].strip()
        _record_usage(module, task, _model, "success", body.get("usage"), elapsed)
        return content
    except Exception as e:
        elapsed = int((time.monotonic() - t0) * 1000)
        logger.warning("DeepSeek API call failed: %s", e)
        _record_usage(module, task, _model, "error", None, elapsed, str(e)[:200])
        return None
