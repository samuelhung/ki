"""System config API — read/write AI provider parameters and per-module overrides."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException

from .. import credential_store
from ..config_manager import get_config, save_config
from ..provider_policy import validate_allowed_base_url
from ..system_config_schema import SystemConfigUpdate

router = APIRouter(prefix="/api/system-config", tags=["system-config"])


def _mask_key(key: str) -> str:
    return key[:4] + "****" + key[-4:] if len(key) > 8 else "****"


@router.get("")
def read_config():
    """Return the full system config, masking the API key."""
    cfg = get_config()
    import copy
    result = copy.deepcopy(cfg)
    key = credential_store.resolve_api_key()
    result["general"]["api_key"] = _mask_key(key) if key and key != "***" else ""
    return result


@router.put("")
def write_config(config: SystemConfigUpdate):
    """Validate and merge a full frontend payload or a known sparse update."""
    payload = config.model_dump(exclude_unset=True, exclude_none=True)
    new_general = payload.get("general", {})

    if "base_url" in new_general:
        try:
            new_general["base_url"] = validate_allowed_base_url(new_general["base_url"])
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

    if "api_key" in new_general:
        api_key = new_general["api_key"]
        existing_key = credential_store.resolve_api_key()
        existing_mask = _mask_key(existing_key) if existing_key and existing_key != "***" else ""
        if api_key not in {"", existing_mask}:
            try:
                credential_store.set_api_key(api_key)
            except ValueError as exc:
                raise HTTPException(status_code=422, detail=str(exc)) from exc
    new_general.pop("api_key", None)
    if not new_general:
        payload.pop("general", None)

    save_config(payload)
    return {"status": "ok"}
