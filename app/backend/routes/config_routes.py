"""System config API — read/write DeepSeek parameters and per-module overrides."""

from __future__ import annotations

import os
from fastapi import APIRouter

from ..config_manager import get_config, save_config

router = APIRouter(prefix="/api/system-config", tags=["system-config"])


@router.get("")
def read_config():
    """Return the full system config, masking the API key."""
    cfg = get_config()
    # Deep-copy and mask key
    import copy
    result = copy.deepcopy(cfg)
    key = result.get("general", {}).get("api_key", "")
    if key:
        result["general"]["api_key"] = key[:4] + "****" + key[-4:] if len(key) > 8 else "****"
    else:
        # If not in config, check env
        env_key = os.getenv("DEEPSEEK_API_KEY", "")
        if env_key and env_key != "***":
            result["general"]["api_key"] = env_key[:4] + "****" + env_key[-4:] if len(env_key) > 8 else "****"
        else:
            result["general"]["api_key"] = ""
    return result


@router.put("")
def write_config(config: dict):
    """Save the full system config to disk. API key is only written if non-empty
    and not purely asterisks."""
    existing = get_config()
    new_general = config.get("general", {})

    # Preserve existing API key if the incoming one is masked or empty
    api_key = new_general.get("api_key", "")
    if not api_key or set(api_key) == {"*"} or "****" in api_key:
        config["general"]["api_key"] = existing.get("general", {}).get("api_key", "")
    else:
        # Write to .env as well for backward compatibility
        _update_env_key(api_key)
        config["general"]["api_key"] = api_key

    save_config(config)
    return {"status": "ok"}


def _update_env_key(key: str) -> None:
    """Optionally sync the API key back to .env file."""
    env_path = __import__("pathlib").Path(__file__).resolve().parents[3] / ".env"
    if not env_path.exists():
        return
    lines = env_path.read_text("utf-8").splitlines()
    new_lines = []
    found = False
    for line in lines:
        if line.startswith("DEEPSEEK_API_KEY="):
            new_lines.append(f"DEEPSEEK_API_KEY={key}")
            found = True
        else:
            new_lines.append(line)
    if not found:
        new_lines.append(f"DEEPSEEK_API_KEY={key}")
    env_path.write_text("\n".join(new_lines) + "\n", "utf-8")
