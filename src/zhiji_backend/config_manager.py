"""System configuration manager — single source of truth for AI params.

Reads from data/system_config.json at startup.  ai_client.chat() merges
per-call overrides on top of the module-level settings from this config.
"""

from __future__ import annotations

import copy
import json
import logging
import os
import stat
import tempfile
import threading
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from . import credential_store

logger = logging.getLogger(__name__)

DEFAULT_AI_MODEL = "deepseek-v4-pro-max"
DEFAULT_AI_BASE_URL = "http://10.8.0.13:3000/v1"

from .paths import CONFIG_PATH

_config: dict[str, Any] = {}
_config_lock = threading.RLock()


@dataclass(frozen=True)
class _ConfigFileSnapshot:
    exists: bool
    data: bytes
    mode: int


def _defaults() -> dict:
    return {
        "general": {
            "model": DEFAULT_AI_MODEL,
            "base_url": DEFAULT_AI_BASE_URL,
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


def load_config(*, persist_normalization: bool = True) -> dict[str, Any]:
    """Load config from disk, falling back to defaults if missing/corrupt."""
    with _config_lock:
        return _load_config_unlocked(persist_normalization=persist_normalization)


def _load_config_unlocked(*, persist_normalization: bool = True) -> dict[str, Any]:
    global _config
    _reject_config_symlink()
    if CONFIG_PATH.exists():
        os.chmod(CONFIG_PATH, 0o600)
        try:
            raw = json.loads(CONFIG_PATH.read_text("utf-8"))
            raw, structure_changed = _normalize_persisted_config(raw)
        except Exception:
            logger.exception("Failed to load config, using defaults")
            _config = _defaults()
            return _config

        general = raw.get("general")
        had_legacy_key = isinstance(general, dict) and "api_key" in general
        raw, legacy_key = _scrub_api_key(raw)
        env_base_url = credential_store.resolve_base_url()
        if env_base_url:
            env_base_url = _validate_provider_base_url(env_base_url)
            raw_general = raw.get("general")
            clean_general = dict(raw_general) if isinstance(raw_general, dict) else {}
            if clean_general.get("base_url") != env_base_url:
                clean_general["base_url"] = env_base_url
                raw["general"] = clean_general
                structure_changed = True
        if had_legacy_key and persist_normalization:
            with _config_credential_transaction():
                effective_key = credential_store.resolve_api_key() or legacy_key
                if effective_key:
                    bundle_base_url = env_base_url or _validate_provider_base_url(
                        raw.get("general", {}).get("base_url", DEFAULT_AI_BASE_URL)
                    )
                    credential_store.set_provider_bundle(
                        effective_key,
                        bundle_base_url,
                    )
                    raw_general = raw.get("general")
                    clean_general = (
                        dict(raw_general) if isinstance(raw_general, dict) else {}
                    )
                    clean_general["base_url"] = bundle_base_url
                    raw["general"] = clean_general
                _write_config(raw)
            structure_changed = False

        active = _deep_merge(_defaults(), raw)
        if structure_changed and persist_normalization:
            try:
                _write_config(raw)
            except Exception:
                logger.exception("Failed to persist normalized system config at %s", CONFIG_PATH)
        _config = active
        logger.info("Loaded system config from %s", CONFIG_PATH)
    else:
        _config = _defaults()
        if persist_normalization:
            try:
                _write_config(_config)
                logger.info("Created default system config at %s", CONFIG_PATH)
            except Exception:
                logger.exception("Failed to create default system config at %s", CONFIG_PATH)
    return _config


def get_config() -> dict[str, Any]:
    """Return the current in-memory config (loaded at startup)."""
    return _config


def get_config_and_credential() -> tuple[dict[str, Any], str]:
    """Return a coherent config and credential snapshot for AI consumers."""
    with _config_lock:
        with credential_store.locked():
            result = copy.deepcopy(_config)
            general = result.setdefault("general", {})
            general["base_url"] = _validate_provider_base_url(
                credential_store.resolve_base_url()
                or general.get("base_url", DEFAULT_AI_BASE_URL)
            )
            key = (
                credential_store.resolve_bundle_api_key()
                if credential_store.resolve_base_url()
                else credential_store.resolve_api_key()
            )
            return result, key


def save_config(config: dict | None = None) -> None:
    """Persist config to disk. If config is None, saves the current in-memory copy."""
    with _config_lock:
        _save_config_unlocked(config)


def update_config_and_credential(
    config: dict,
    requested_api_key: str | None,
) -> None:
    """Commit config and credential changes as one serialized transaction."""
    with _config_credential_transaction():
        active = _build_active_config(config)
        base_url = _validate_provider_base_url(
            active.get("general", {}).get("base_url", DEFAULT_AI_BASE_URL)
        )
        effective_key = credential_store.resolve_api_key()
        if (
            requested_api_key is not None
            and not credential_store.preserves_api_key(requested_api_key)
        ):
            effective_key = requested_api_key
        credential_store.set_provider_bundle(effective_key, base_url)
        _write_config(active)
        global _config
        _config = active


@contextmanager
def _config_credential_transaction() -> Iterator[None]:
    global _config
    with _config_lock:
        with credential_store.locked():
            config_snapshot = _snapshot_config_file()
            credential_snapshot = credential_store.snapshot_state()
            active_before = _config
            try:
                yield
            except BaseException as exc:
                rollback_errors: list[BaseException] = []
                try:
                    if not _config_file_matches(config_snapshot):
                        _restore_config_file(config_snapshot)
                except BaseException as rollback_exc:
                    rollback_errors.append(rollback_exc)
                try:
                    if not credential_store.state_matches(credential_snapshot):
                        credential_store.restore_state(credential_snapshot)
                except BaseException as rollback_exc:
                    rollback_errors.append(rollback_exc)
                _config = active_before
                if rollback_errors:
                    raise RuntimeError("system config transaction rollback failed") from exc
                raise


def _save_config_unlocked(config: dict | None = None) -> None:
    global _config
    active = _build_active_config(config)
    _write_config(active)
    _config = active


def _build_active_config(config: dict | None = None) -> dict:
    current, _ = _normalize_persisted_config(_config)
    current, _ = _scrub_api_key(current)
    active = _deep_merge(_defaults(), current)
    if config is not None:
        incoming, _ = _normalize_persisted_config(config)
        incoming, _ = _scrub_api_key(incoming)
        active = _deep_merge(active, incoming)
    return active


def _write_config(config: dict) -> None:
    """Atomically write a config payload without changing in-memory state."""
    _reject_config_symlink()
    config, _ = _scrub_api_key(config)
    CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    temp_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=CONFIG_PATH.parent,
            prefix=f".{CONFIG_PATH.name}.",
            suffix=".tmp",
            delete=False,
        ) as temp_file:
            temp_path = Path(temp_file.name)
            os.fchmod(temp_file.fileno(), 0o600)
            json.dump(config, temp_file, ensure_ascii=False, indent=2)
            temp_file.flush()
            os.fsync(temp_file.fileno())
        os.chmod(temp_path, 0o600)
        os.replace(temp_path, CONFIG_PATH)
        temp_path = None
        _fsync_parent_directory()
        logger.info("Saved system config to %s", CONFIG_PATH)
    finally:
        if temp_path is not None:
            temp_path.unlink(missing_ok=True)


def _snapshot_config_file() -> _ConfigFileSnapshot:
    _reject_config_symlink()
    exists = CONFIG_PATH.exists()
    return _ConfigFileSnapshot(
        exists=exists,
        data=CONFIG_PATH.read_bytes() if exists else b"",
        mode=stat.S_IMODE(CONFIG_PATH.stat().st_mode) if exists else 0o600,
    )


def _config_file_matches(snapshot: _ConfigFileSnapshot) -> bool:
    _reject_config_symlink()
    exists = CONFIG_PATH.exists()
    if exists != snapshot.exists:
        return False
    if not exists:
        return True
    return (
        CONFIG_PATH.read_bytes() == snapshot.data
        and stat.S_IMODE(CONFIG_PATH.stat().st_mode) == snapshot.mode
    )


def _restore_config_file(snapshot: _ConfigFileSnapshot) -> None:
    _reject_config_symlink()
    if not snapshot.exists:
        CONFIG_PATH.unlink(missing_ok=True)
        return

    CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    temp_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="wb",
            dir=CONFIG_PATH.parent,
            prefix=f".{CONFIG_PATH.name}.rollback.",
            suffix=".tmp",
            delete=False,
        ) as temp_file:
            temp_path = Path(temp_file.name)
            os.fchmod(temp_file.fileno(), snapshot.mode)
            temp_file.write(snapshot.data)
            temp_file.flush()
            os.fsync(temp_file.fileno())
        os.replace(temp_path, CONFIG_PATH)
        temp_path = None
    finally:
        if temp_path is not None:
            temp_path.unlink(missing_ok=True)


def _reject_config_symlink() -> None:
    try:
        mode = os.lstat(CONFIG_PATH).st_mode
    except FileNotFoundError:
        return
    if stat.S_ISLNK(mode):
        raise OSError(f"refusing to use symlink system config: {CONFIG_PATH}")


def _fsync_parent_directory() -> None:
    """Durably record the atomic rename on filesystems that support directory fsync."""
    directory_fd: int | None = None
    try:
        flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0)
        directory_fd = os.open(CONFIG_PATH.parent, flags)
        os.fsync(directory_fd)
    except OSError:
        logger.debug("Parent directory fsync is unavailable for %s", CONFIG_PATH.parent, exc_info=True)
    finally:
        if directory_fd is not None:
            try:
                os.close(directory_fd)
            except OSError:
                logger.debug("Failed to close config directory fd", exc_info=True)


def get_module_config(module: str, task: str) -> dict:
    """Get merged config for a specific module+task.

    Returns a dict ready to unpack into chat() kwargs.
    """
    config, _key = get_config_and_credential()
    g = config.get("general", {})
    m = config.get(module, {})
    t = m.get(task, {}) if isinstance(m, dict) else {}

    return {
        "model": g.get("model", DEFAULT_AI_MODEL),
        "base_url": g.get("base_url", DEFAULT_AI_BASE_URL),
        "thinking": t.get("thinking", g.get("default_thinking", False)),
        "reasoning_effort": g.get("reasoning_effort", "high"),
        "disk_cache": g.get("disk_cache", True),
        "temperature": t.get("temperature", g.get("default_temperature", 0.3)),
        "max_tokens": t.get("max_tokens", g.get("default_max_tokens", 2048)),
    }


def _validate_provider_base_url(value: str) -> str:
    from .provider_policy import validate_allowed_base_url

    return validate_allowed_base_url(value)


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
    if not isinstance(raw, dict):
        raise ValueError("System config root must be an object")
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


def _scrub_api_key(raw: dict) -> tuple[dict, str]:
    """Return a copy without the retired plaintext credential field."""
    scrubbed = dict(raw)
    general = scrubbed.get("general")
    if not isinstance(general, dict) or "api_key" not in general:
        return scrubbed, ""
    clean_general = dict(general)
    legacy_key = clean_general.pop("api_key")
    scrubbed["general"] = clean_general
    return scrubbed, legacy_key if isinstance(legacy_key, str) else ""


# Import-time consumers get active in-memory defaults without mutating legacy files.
load_config(persist_normalization=False)
