from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.exceptions import ConfigEntryNotReady, ConfigEntryAuthFailed

from .api import ConnectMyPoolApi, ConnectMyPoolError, ConnectMyPoolAuthError
from .const import (
    DOMAIN,
    PLATFORMS,
    CONF_POOL_API_CODE,
    CONF_BASE_URL,
    CONF_TEMPERATURE_SCALE,
    CONF_SCAN_INTERVAL,
    DEFAULT_BASE_URL,
    DEFAULT_TEMPERATURE_SCALE,
    DEFAULT_SCAN_INTERVAL,
)
from .coordinator import ConnectMyPoolCoordinator

async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    hass.data.setdefault(DOMAIN, {})

    pool_api_code: str = entry.data[CONF_POOL_API_CODE]
    base_url: str = entry.options.get(CONF_BASE_URL, entry.data.get(CONF_BASE_URL, DEFAULT_BASE_URL))
    temperature_scale: int = entry.options.get(CONF_TEMPERATURE_SCALE, entry.data.get(CONF_TEMPERATURE_SCALE, DEFAULT_TEMPERATURE_SCALE))
    scan_interval: int = entry.options.get(CONF_SCAN_INTERVAL, entry.data.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL))

    session = async_get_clientsession(hass)
    api = ConnectMyPoolApi(session, base_url=base_url)

    # Load config once per entry (used to build entities)
    try:
        pool_config = await api.pool_config(pool_api_code)
    except ConnectMyPoolAuthError as err:
        raise ConfigEntryAuthFailed(str(err)) from err
    except ConnectMyPoolError as err:
        raise ConfigEntryNotReady(str(err)) from err
    except Exception as err:
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
    }

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True

async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        hass.data[DOMAIN].pop(entry.entry_id, None)
    return unload_ok
