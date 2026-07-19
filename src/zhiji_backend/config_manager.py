"""System configuration manager — single source of truth for AI params.

Reads from data/system_config.json at startup.  ai_client.chat() merges
per-call overrides on top of the module-level settings from this config.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

DEFAULT_AI_MODEL = "deepseek-v4-pro-max"
DEFAULT_AI_BASE_URL = "http://10.8.0.13:3000/v1"

from .paths import CONFIG_PATH
_config: dict[str, Any] = {}


def _defaults() -> dict:
    return {
        "general": {
            "model": DEFAULT_AI_MODEL,
            "base_url": DEFAULT_AI_BASE_URL,
            "api_key": "",
            "disk_cache": True,
            "default_temperature": 0.3,
            "default_max_tokens": 2048,
            "default_thinking": False,
            "reasoning_effort": "high",
        },
        "ingest_pipeline": {
            "summarize":  {"temperature": 0.3, "max_tokens": 3072, "thinking": False},
            "classify":   {"temperature": 0.1, "max_tokens": 256,  "thinking": False},
            "tag":        {"temperature": 0.1, "max_tokens": 512,  "thinking": False},
            "translate":  {"temperature": 0.1, "max_tokens": 2048, "thinking": False},
        },
        "series": {
            "discover":     {"temperature": 0.4, "max_tokens": 4096,  "thinking": False},
            "intro":        {"temperature": 0.5, "max_tokens": 1024,  "thinking": False},
            "summary":      {"temperature": 0.3, "max_tokens": 3072,  "thinking": False},
            "paper":        {"temperature": 0.5, "max_tokens": 16384, "thinking": True},
            "auto_suggest": {"temperature": 0.1, "max_tokens": 256,   "thinking": False},
        },
        "brainstorm": {
            "answer":          {"temperature": 0.3, "max_tokens": 8192,  "thinking": True},
            "summary":         {"temperature": 0.3, "max_tokens": 3000,  "thinking": False},
            "contemplate":     {"temperature": 0.3, "max_tokens": 800,   "thinking": False},
            "concept_extract": {"temperature": 0.1, "max_tokens": 2048,  "thinking": False},
        },
        "briefing": {
            "briefing_quick": {"temperature": 0.3, "max_tokens": 3072,  "thinking": False},
            "briefing_daily": {"temperature": 0.3, "max_tokens": 8192,  "thinking": False},
        },
        "tasks": {
            "judge":     {"temperature": 0.4, "max_tokens": 16384, "thinking": False},
        },
        "concept": {
            "auto_complete": {"temperature": 0.3, "max_tokens": 1500, "thinking": False},
        },
        "study": {
            "math_应用题":        {"temperature": 0.3, "max_tokens": 16384, "thinking": False},
            "英语_阅读理解":      {"temperature": 0.3, "max_tokens": 16384, "thinking": False},
            "语文_阅读理解":      {"temperature": 0.3, "max_tokens": 16384, "thinking": False},
            "study_mistake_review": {"temperature": 0.3, "max_tokens": 4096,  "thinking": False},
        },
    }


def load_config() -> dict[str, Any]:
    """Load config from disk, falling back to defaults if missing/corrupt."""
    global _config
    try:
        if CONFIG_PATH.exists():
            raw = json.loads(CONFIG_PATH.read_text("utf-8"))
            raw, structure_changed = _normalize_persisted_config(raw)
            defaults = _defaults()
            _config = _deep_merge(defaults, raw)
            if structure_changed:
                _write_config(raw)
            logger.info("Loaded system config from %s", CONFIG_PATH)
        else:
            _config = _defaults()
            save_config()
            logger.info("Created default system config at %s", CONFIG_PATH)
    except Exception:
        logger.exception("Failed to load config, using defaults")
        _config = _defaults()
    return _config


def get_config() -> dict[str, Any]:
    """Return the current in-memory config (loaded at startup)."""
    return _config


def save_config(config: dict | None = None) -> None:
    """Persist config to disk. If config is None, saves the current in-memory copy."""
    global _config
    if config is not None:
        _config = config
    _write_config(_config)


def _write_config(config: dict) -> None:
    """Write a config payload without changing the active in-memory config."""
    CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    CONFIG_PATH.write_text(json.dumps(config, ensure_ascii=False, indent=2), "utf-8")
    logger.info("Saved system config to %s", CONFIG_PATH)


def get_module_config(module: str, task: str) -> dict:
    """Get merged config for a specific module+task.

    Returns a dict ready to unpack into chat() kwargs.
    """
    g = _config.get("general", {})
    m = _config.get(module, {})
    t = m.get(task, {}) if isinstance(m, dict) else {}

    return {
        "model": g.get("model", DEFAULT_AI_MODEL),
        "base_url": g.get("base_url", DEFAULT_AI_BASE_URL),
        "thinking": t.get("thinking", g.get("default_thinking", False)),
        "reasoning_effort": g.get("reasoning_effort", "high"),
        "disk_cache": g.get("disk_cache", True),
        "temperature": t.get("temperature", g.get("default_temperature", 0.3)),
        "max_tokens": t.get("max_tokens", g.get("default_max_tokens", 2048)),
        "api_key": g.get("api_key", ""),
    }


def _deep_merge(base: dict, override: dict) -> dict:
    """Recursively merge override into base, returning a new dict."""
    result = dict(base)
    for k, v in override.items():
        if k in result and isinstance(result[k], dict) and isinstance(v, dict):
            result[k] = _deep_merge(result[k], v)
        else:
            result[k] = v
    return result


def _normalize_persisted_config(raw: dict) -> tuple[dict, bool]:
    """Migrate retired module keys while preserving sparse user overrides."""
    normalized = dict(raw)
    legacy = normalized.pop("digest_briefing", None)
    normalized.pop("knowledge_graph", None)

    current = normalized.get("briefing")
    legacy_tasks = legacy if isinstance(legacy, dict) else {}
    current_tasks = current if isinstance(current, dict) else {}
    briefing: dict[str, Any] = {}

    for task in ("briefing_quick", "briefing_daily"):
        legacy_override = legacy_tasks.get(task)
        current_override = current_tasks.get(task)
        if isinstance(legacy_override, dict) and isinstance(current_override, dict):
            briefing[task] = _deep_merge(legacy_override, current_override)
        elif isinstance(current_override, dict):
            briefing[task] = dict(current_override)
        elif isinstance(legacy_override, dict):
            briefing[task] = dict(legacy_override)

    if briefing:
        normalized["briefing"] = briefing
    elif "briefing" in normalized:
        normalized.pop("briefing")

    return normalized, normalized != raw


# Auto-load at import time
load_config()
