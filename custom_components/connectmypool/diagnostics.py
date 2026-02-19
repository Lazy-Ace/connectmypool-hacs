from __future__ import annotations

from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .const import DOMAIN, CONF_POOL_API_CODE


def _redact(obj: Any) -> Any:
    if isinstance(obj, dict):
        out = {}
        for k, v in obj.items():
            if k in (CONF_POOL_API_CODE, "pool_api_code"):
                out[k] = "***REDACTED***"
            else:
                out[k] = _redact(v)
        return out
    if isinstance(obj, list):
        return [_redact(x) for x in obj]
    return obj


async def async_get_config_entry_diagnostics(hass: HomeAssistant, entry: ConfigEntry) -> dict[str, Any]:
    data = hass.data.get(DOMAIN, {}).get(entry.entry_id, {})
    coordinator = data.get("coordinator")

    diag: dict[str, Any] = {
        "entry": {
            "title": entry.title,
            "data": _redact(dict(entry.data)),
            "options": dict(entry.options),
        },
        "api": {
            "base_url": getattr(data.get("api"), "base_url", None),
        },
        "config": _redact(data.get("config")),
        "last_status": _redact(getattr(coordinator, "data", None)) if coordinator else None,
    }
    return diag
