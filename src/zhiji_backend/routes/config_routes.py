"""System config API — read/write AI provider parameters and per-module overrides."""

from __future__ import annotations

import os
from fastapi import APIRouter

from ..config_manager import get_config, save_config

router = APIRouter(prefix="/api/system-config", tags=["system-config"])


def _mask_key(key: str) -> str:
    return key[:4] + "****" + key[-4:] if len(key) > 8 else "****"


@router.get("")
def read_config():
    """Return the full system config, masking the API key."""
    cfg = get_config()
    import copy
    result = copy.deepcopy(cfg)
    key = result.get("general", {}).get("api_key", "")
    if key:
        result["general"]["api_key"] = _mask_key(key)
    else:
        env_key = os.getenv("AI_API_KEY", "") or os.getenv("OPENAI_API_KEY", "") or os.getenv("DEEPSEEK_API_KEY", "")
        result["general"]["api_key"] = _mask_key(env_key) if env_key and env_key != "***" else ""
    return result


@router.put("")
def write_config(config: dict):
    """Save the full system config to disk. API key is only written if non-empty
    and not purely asterisks."""
    existing = get_config()
    new_general = config.get("general", {})

    api_key = new_general.get("api_key", "")
    if not api_key or set(api_key) == {"*"} or "****" in api_key:
        config["general"]["api_key"] = existing.get("general", {}).get("api_key", "")
    else:
        _update_env_key(api_key)
        config["general"]["api_key"] = api_key

    save_config(config)
    return {"status": "ok"}


def _replace_or_append_env(lines: list[str], name: str, value: str) -> tuple[list[str], bool]:
    new_lines = []
    found = False
    for line in lines:
        if line.startswith(f"{name}="):
            new_lines.append(f"{name}={value}")
            found = True
        else:
            new_lines.append(line)
    if not found:
        new_lines.append(f"{name}={value}")
    return new_lines, found


def _update_env_key(key: str) -> None:
    """Optionally sync the API key back to .env file."""
    from ..paths import ZHIJI_HOME as _zh
    env_path = _zh / ".env"
    if not env_path.exists():
        return
    lines = env_path.read_text("utf-8").splitlines()
    lines, _ = _replace_or_append_env(lines, "AI_API_KEY", key)
    if any(line.startswith("DEEPSEEK_API_KEY=") for line in lines):
        lines, _ = _replace_or_append_env(lines, "DEEPSEEK_API_KEY", key)
    env_path.write_text("\n".join(lines) + "\n", "utf-8")
