"""Unified OpenAI-compatible AI client — single entry point for backend LLM calls.

Reads defaults from system_config.json via config_manager. Every call can
override temperature/max_tokens/model/etc.
"""

from __future__ import annotations

import json
import logging
import time
import urllib.request
from typing import Any

from .config_manager import (
    DEFAULT_AI_BASE_URL,
    DEFAULT_AI_MODEL,
    get_config_and_credential,
)
from .credential_store import resolve_api_key
from .security.redaction import classify_task_error
from .usage_writer import UsageRecord, enqueue_usage

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
    """Calculate usage telemetry and enqueue it without affecting the AI result."""
    try:
        prompt_tokens = usage.get("prompt_tokens", 0) if usage else 0
        completion_tokens = usage.get("completion_tokens", 0) if usage else 0
        total_tokens = usage.get("total_tokens", 0) if usage else 0
        cached_tokens = (usage.get("prompt_tokens_details", {}) or {}).get("cached_tokens", 0) if usage else 0
        reasoning_tokens = (usage.get("completion_tokens_details", {}) or {}).get("reasoning_tokens", 0) if usage else 0

        non_cached = prompt_tokens - cached_tokens
        cost = non_cached * 3 / 1_000_000 + cached_tokens * 0.025 / 1_000_000 + completion_tokens * 6 / 1_000_000
    except Exception:
        prompt_tokens = completion_tokens = total_tokens = cached_tokens = reasoning_tokens = 0
        cost = 0

    try:
        enqueue_usage(
            UsageRecord(
                module=module or "",
                task=task or "",
                model=model,
                status=status,
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
                total_tokens=total_tokens,
                cached_tokens=cached_tokens,
                reasoning_tokens=reasoning_tokens,
                cost_rmb=round(cost, 6),
                duration_ms=elapsed_ms,
                error=error,
            )
        )
    except Exception as exc:
        logger.error(
            "AI usage enqueue failed module=%s task=%s status=%s exception=%s",
            module or "",
            task or "",
            status,
            type(exc).__name__,
        )


def _resolve_api_key(_general: dict[str, Any] | None = None) -> str:
    """Resolve API key exclusively from the server environment."""
    return resolve_api_key()


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
    """Call an OpenAI-compatible chat completion API.

    All parameters are optional — falls back to system_config.json defaults, then
    project defaults.
    """
    cfg, _api_key = get_config_and_credential()
    general = cfg.get("general", {})

    mod_defaults: dict = {}
    if module and module in cfg and isinstance(cfg[module], dict):
        mod_tasks = cfg[module]
        if task and task in mod_tasks and isinstance(mod_tasks[task], dict):
            mod_defaults = mod_tasks[task]

    _model = model or general.get("model", DEFAULT_AI_MODEL)
    _base_url = general.get("base_url", DEFAULT_AI_BASE_URL).rstrip("/")
    _temperature = temperature if temperature is not None else mod_defaults.get("temperature", general.get("default_temperature", 0.3))
    _max_tokens = max_tokens if max_tokens is not None else mod_defaults.get("max_tokens", general.get("default_max_tokens", 2048))
    _thinking = thinking if thinking is not None else mod_defaults.get("thinking", general.get("default_thinking", False))
    _reasoning_effort = reasoning_effort or general.get("reasoning_effort", "high")

    if not _api_key or _api_key == "***":
        logger.warning("AI API key not configured")
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
    t0 = time.monotonic()

    try:
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
            logger.warning("AI API returned empty choices")
            _record_usage(module, task, _model, "error", body.get("usage"), elapsed, "empty choices")
            return None

        message = choices[0].get("message", {})
        content = (message.get("content") or "").strip()
        if not content:
            finish_reason = choices[0].get("finish_reason", "")
            error = f"empty content; finish_reason={finish_reason}"
            logger.warning("AI API returned empty content: %s", error)
            _record_usage(module, task, _model, "error", body.get("usage"), elapsed, error)
            return None

        _record_usage(module, task, _model, "success", body.get("usage"), elapsed)
        return content
    except Exception as e:
        elapsed = int((time.monotonic() - t0) * 1000)
        logger.warning(
            "module=%s task=%s status=error error_class=%s error_code=%s",
            module,
            task,
            type(e).__name__,
            classify_task_error(e),
        )
        _record_usage(module, task, _model, "error", None, elapsed, str(e)[:200])
        return None
