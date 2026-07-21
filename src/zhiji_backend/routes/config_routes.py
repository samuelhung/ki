"""System config API — read/write AI provider parameters and per-module overrides."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException

from .. import credential_store
from ..config_manager import get_config_and_credential, update_config_and_credential
from ..provider_policy import validate_allowed_base_url
from ..system_config_schema import SystemConfigUpdate

router = APIRouter(prefix="/api/system-config", tags=["system-config"])


def _mask_key(key: str) -> str:
    return credential_store.mask_api_key(key)


@router.get("")
def read_config():
    """Return the full system config, masking the API key."""
    result, key = get_config_and_credential()
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

    requested_api_key = new_general.get("api_key") if "api_key" in new_general else None
    new_general.pop("api_key", None)
    if not new_general:
        payload.pop("general", None)

    try:
        update_config_and_credential(payload, requested_api_key)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return {"status": "ok"}
