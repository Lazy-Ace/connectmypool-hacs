from __future__ import annotations

import asyncio
import logging
from typing import Any

import voluptuous as vol

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.exceptions import ConfigEntryNotReady, ConfigEntryAuthFailed

from .api import ConnectMyPoolApi, ConnectMyPoolAuthError, ConnectMyPoolError
from .const import (
    DOMAIN,
    PLATFORMS,
    CONF_POOL_API_CODE,
    CONF_BASE_URL,
    CONF_TEMPERATURE_SCALE,
    CONF_SCAN_INTERVAL,
    CONF_WAIT_FOR_EXECUTION,
    DEFAULT_BASE_URL,
    DEFAULT_TEMPERATURE_SCALE,
    DEFAULT_SCAN_INTERVAL,
    DEFAULT_WAIT_FOR_EXECUTION,
)
from .coordinator import ConnectMyPoolCoordinator

_LOGGER = logging.getLogger(__name__)

SERVICE_SEND_ACTION = "send_action"


async def async_setup(hass: HomeAssistant, config: dict[str, Any]) -> bool:
    """Set up the integration (service registration)."""
    hass.data.setdefault(DOMAIN, {})
    _async_setup_services(hass)
    return True


def _async_setup_services(hass: HomeAssistant) -> None:
    if hass.data[DOMAIN].get("_services_setup"):
        return

    schema = vol.Schema(
        {
            vol.Optional("config_entry_id"): str,
            vol.Required("action_code"): int,
            vol.Optional("device_number", default=0): int,
            vol.Optional("value", default=""): str,
            vol.Optional("wait_for_execution"): bool,
        }
    )

    async def _handle_send_action(call: ServiceCall) -> None:
        entry_id = call.data.get("config_entry_id")
        entries = hass.data.get(DOMAIN, {})
        if entry_id is None:
            # If only one pool configured, use it.
            configured = [k for k in entries.keys() if not str(k).startswith("_")]
            if len(configured) == 1:
                entry_id = configured[0]
            else:
                raise ValueError("Multiple ConnectMyPool entries; provide config_entry_id")

        data = hass.data[DOMAIN].get(entry_id)
        if not data:
            raise ValueError(f"Unknown config_entry_id: {entry_id}")

        coordinator: ConnectMyPoolCoordinator = data["coordinator"]
        api: ConnectMyPoolApi = data["api"]
        wait = call.data.get("wait_for_execution", data.get("wait_for_execution", DEFAULT_WAIT_FOR_EXECUTION))

        await api.pool_action(
            pool_api_code=coordinator.pool_api_code,
            action_code=int(call.data["action_code"]),
            device_number=int(call.data.get("device_number", 0)),
            value=str(call.data.get("value", "")),
            temperature_scale=coordinator.temperature_scale,
            wait_for_execution=bool(wait),
        )

        await asyncio.sleep(1.5)
        await coordinator.async_request_refresh()

    hass.services.async_register(DOMAIN, SERVICE_SEND_ACTION, _handle_send_action, schema=schema)
    hass.data[DOMAIN]["_services_setup"] = True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    hass.data.setdefault(DOMAIN, {})

    pool_api_code: str = entry.data[CONF_POOL_API_CODE]

    base_url: str = entry.options.get(CONF_BASE_URL, entry.data.get(CONF_BASE_URL, DEFAULT_BASE_URL))
    temperature_scale: int = entry.options.get(
        CONF_TEMPERATURE_SCALE, entry.data.get(CONF_TEMPERATURE_SCALE, DEFAULT_TEMPERATURE_SCALE)
    )
    scan_interval: int = entry.options.get(
        CONF_SCAN_INTERVAL, entry.data.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL)
    )
    wait_for_execution: bool = entry.options.get(CONF_WAIT_FOR_EXECUTION, DEFAULT_WAIT_FOR_EXECUTION)

    session = async_get_clientsession(hass)
    api = ConnectMyPoolApi(session, base_url=base_url, min_poll_seconds=60)

    # Load config once (used to build entities)
    try:
        pool_config = await api.pool_config(pool_api_code)
    except ConnectMyPoolAuthError as err:
        raise ConfigEntryAuthFailed(str(err)) from err
    except ConnectMyPoolError as err:
        raise ConfigEntryNotReady(str(err)) from err
    except Exception as err:  # noqa: BLE001
        raise ConfigEntryNotReady(str(err)) from err

    coordinator = ConnectMyPoolCoordinator(
        hass,
        api=api,
        pool_api_code=pool_api_code,
        temperature_scale=temperature_scale,
        scan_interval=scan_interval,
    )
    await coordinator.async_config_entry_first_refresh()

    hass.data[DOMAIN][entry.entry_id] = {
        "api": api,
        "config": pool_config,
        "coordinator": coordinator,
        "wait_for_execution": wait_for_execution,
    }

    _async_setup_services(hass)

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        hass.data[DOMAIN].pop(entry.entry_id, None)
    return unload_ok
