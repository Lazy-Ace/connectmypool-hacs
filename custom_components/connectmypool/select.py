from __future__ import annotations

import asyncio
from typing import Any, Optional

from homeassistant.components.select import SelectEntity
from homeassistant.const import EntityCategory
from homeassistant.exceptions import HomeAssistantError

from .api import ConnectMyPoolApi, ConnectMyPoolError
from .const import DOMAIN, CHANNEL_MODES, TRI_MODES, POOL_SPA, HEAT_COOL
from .entity import ConnectMyPoolEntity

# Action codes (per ConnectMyPool docs)
ACTION_CYCLE_CHANNEL = 1
ACTION_SET_VALVE_MODE = 2
ACTION_SET_POOL_SPA = 3
ACTION_SET_LIGHT_MODE = 6
ACTION_SET_FAVOURITE = 8
ACTION_SET_SOLAR_MODE = 9
ACTION_SET_HEAT_COOL = 12

async def async_setup_entry(hass, entry, async_add_entities):
    data = hass.data[DOMAIN][entry.entry_id]
    coordinator = data["coordinator"]
    api: ConnectMyPoolApi = data["api"]
    cfg: dict[str, Any] = data["config"]
    wait_for_execution: bool = entry.options.get("wait_for_execution", False)

    entities: list[SelectEntity] = []

    # Pool/Spa and Heat/Cool selectors if enabled
    if cfg.get("pool_spa_selection_enabled"):
        entities.append(PoolSpaSelect(coordinator, api, wait_for_execution))
    if cfg.get("heat_cool_selection_enabled"):
        entities.append(HeatCoolSelect(coordinator, api, wait_for_execution))

    # Active favourite
    favs = cfg.get("favourites") or []
    if favs:
        entities.append(ActiveFavouriteSelect(coordinator, api, wait_for_execution, favs))

    # Channels
    for ch in (cfg.get("channels") or []):
        entities.append(ChannelModeSelect(coordinator, api, wait_for_execution, ch))

    # Valves
    for v in (cfg.get("valves") or []):
        entities.append(ValveModeSelect(coordinator, api, wait_for_execution, v))

    # Solar
    for s in (cfg.get("solar_systems") or []):
        entities.append(SolarModeSelect(coordinator, api, wait_for_execution, s))

    # Lighting zone mode
    for lz in (cfg.get("lighting_zones") or []):
        entities.append(LightingZoneModeSelect(coordinator, api, wait_for_execution, lz))

    async_add_entities(entities)

class _BaseSelect(ConnectMyPoolEntity, SelectEntity):
    _attr_entity_category = EntityCategory.CONFIG

    def __init__(self, coordinator, api: ConnectMyPoolApi, wait_for_execution: bool, name: str, unique_suffix: str) -> None:
        super().__init__(coordinator, name, unique_suffix)
        self._api = api
        self._wait = wait_for_execution

    async def _do_action(self, action_code: int, device_number: int = 0, value: str = "") -> None:
        try:
            await self._api.pool_action(
                pool_api_code=self.coordinator.pool_api_code,
                action_code=action_code,
                device_number=device_number,
                value=value,
                wait_for_execution=self._wait,
            )
            # Give the cloud a moment, then refresh
            await asyncio.sleep(1.5)
            await self.coordinator.async_request_refresh()
        except ConnectMyPoolError as err:
            raise HomeAssistantError(str(err)) from err

class ChannelModeSelect(_BaseSelect):
    def __init__(self, coordinator, api, wait_for_execution, ch: dict[str, Any]) -> None:
        self._channel_number = int(ch["channel_number"])
        friendly = ch.get("name") or f"Channel {self._channel_number}"
        super().__init__(coordinator, api, wait_for_execution, f"{friendly} Mode", f"channel_{self._channel_number}_mode")
        # Best-effort options (API cycles channel modes; device may support subset)
        self._attr_options = list(CHANNEL_MODES.values())

    @property
    def current_option(self) -> str | None:
        mode = self._find_mode()
        if mode is None:
            return None
        return CHANNEL_MODES.get(mode, str(mode))

    def _find_mode(self) -> Optional[int]:
        for c in (self.data.get("channels") or []):
            if int(c.get("channel_number")) == self._channel_number:
                try:
                    return int(c.get("mode"))
                except Exception:
                    return None
        return None

    async def async_select_option(self, option: str) -> None:
        # Because API can only *cycle*, we attempt to reach the requested option by cycling.
        desired = None
        for k, v in CHANNEL_MODES.items():
            if v == option:
                desired = k
                break
        if desired is None:
            raise HomeAssistantError(f"Unsupported option: {option}")

        current = self._find_mode()
        if current == desired:
            return

        # Try up to 6 cycles to land on the desired mode
        for _ in range(6):
            await self._do_action(ACTION_CYCLE_CHANNEL, device_number=self._channel_number, value="")
            await asyncio.sleep(0.8)
            await self.coordinator.async_request_refresh()
            current = self._find_mode()
            if current == desired:
                return

        raise HomeAssistantError(
            f"Couldn't reach mode '{option}' by cycling. Device may not support that mode."
        )

class ValveModeSelect(_BaseSelect):
    def __init__(self, coordinator, api, wait_for_execution, valve: dict[str, Any]) -> None:
        self._valve_number = int(valve["valve_number"])
        friendly = valve.get("name") or f"Valve {self._valve_number}"
        super().__init__(coordinator, api, wait_for_execution, f"{friendly} Mode", f"valve_{self._valve_number}_mode")
        self._attr_options = list(TRI_MODES.values())

    @property
    def current_option(self) -> str | None:
        for v in (self.data.get("valves") or []):
            if int(v.get("valve_number")) == self._valve_number:
                return TRI_MODES.get(int(v.get("mode")), None)
        return None

    async def async_select_option(self, option: str) -> None:
        value = None
        for k, v in TRI_MODES.items():
            if v == option:
                value = k
                break
        if value is None:
            raise HomeAssistantError(f"Unsupported option: {option}")
        await self._do_action(ACTION_SET_VALVE_MODE, device_number=self._valve_number, value=str(value))

class LightingZoneModeSelect(_BaseSelect):
    def __init__(self, coordinator, api, wait_for_execution, lz: dict[str, Any]) -> None:
        self._lz_number = int(lz["lighting_zone_number"])
        friendly = lz.get("name") or f"Lighting Zone {self._lz_number}"
        super().__init__(coordinator, api, wait_for_execution, f"{friendly} Mode", f"lightzone_{self._lz_number}_mode")
        self._attr_options = list(TRI_MODES.values())

    @property
    def current_option(self) -> str | None:
        for lz in (self.data.get("lighting_zones") or []):
            if int(lz.get("lighting_zone_number")) == self._lz_number:
                return TRI_MODES.get(int(lz.get("mode")), None)
        return None

    async def async_select_option(self, option: str) -> None:
        value = None
        for k, v in TRI_MODES.items():
            if v == option:
                value = k
                break
        if value is None:
            raise HomeAssistantError(f"Unsupported option: {option}")
        await self._do_action(ACTION_SET_LIGHT_MODE, device_number=self._lz_number, value=str(value))

class SolarModeSelect(_BaseSelect):
    def __init__(self, coordinator, api, wait_for_execution, solar: dict[str, Any]) -> None:
        self._solar_number = int(solar["solar_number"])
        super().__init__(coordinator, api, wait_for_execution, f"Solar {self._solar_number} Mode", f"solar_{self._solar_number}_mode")
        self._attr_options = list(TRI_MODES.values())

    @property
    def current_option(self) -> str | None:
        for s in (self.data.get("solar_systems") or []):
            if int(s.get("solar_number")) == self._solar_number:
                return TRI_MODES.get(int(s.get("mode")), None)
        return None

    async def async_select_option(self, option: str) -> None:
        value = None
        for k, v in TRI_MODES.items():
            if v == option:
                value = k
                break
        if value is None:
            raise HomeAssistantError(f"Unsupported option: {option}")
        await self._do_action(ACTION_SET_SOLAR_MODE, device_number=self._solar_number, value=str(value))

class PoolSpaSelect(_BaseSelect):
    def __init__(self, coordinator, api, wait_for_execution) -> None:
        super().__init__(coordinator, api, wait_for_execution, "Pool/Spa Selection", "pool_spa_selection")
        self._attr_options = list(POOL_SPA.values())

    @property
    def current_option(self) -> str | None:
        sel = self.data.get("pool_spa_selection")
        if sel is None:
            return None
        return POOL_SPA.get(int(sel))

    async def async_select_option(self, option: str) -> None:
        value = None
        for k, v in POOL_SPA.items():
            if v == option:
                value = k
                break
        if value is None:
            raise HomeAssistantError(f"Unsupported option: {option}")
        await self._do_action(ACTION_SET_POOL_SPA, device_number=0, value=str(value))

class HeatCoolSelect(_BaseSelect):
    def __init__(self, coordinator, api, wait_for_execution) -> None:
        super().__init__(coordinator, api, wait_for_execution, "Heat/Cool Selection", "heat_cool_selection")
        self._attr_options = list(HEAT_COOL.values())

    @property
    def current_option(self) -> str | None:
        sel = self.data.get("heat_cool_selection")
        if sel is None:
            return None
        return HEAT_COOL.get(int(sel))

    async def async_select_option(self, option: str) -> None:
        value = None
        for k, v in HEAT_COOL.items():
            if v == option:
                value = k
                break
        if value is None:
            raise HomeAssistantError(f"Unsupported option: {option}")
        await self._do_action(ACTION_SET_HEAT_COOL, device_number=0, value=str(value))

class ActiveFavouriteSelect(_BaseSelect):
    def __init__(self, coordinator, api, wait_for_execution, favourites: list[dict[str, Any]]) -> None:
        super().__init__(coordinator, api, wait_for_execution, "Active Favourite", "active_favourite")
        self._favourites = favourites
        # Add "None" for 255
        self._attr_options = ["None"] + [f.get("name", f"Favourite {f.get('favourite_number')}") for f in favourites]

    @property
    def current_option(self) -> str | None:
        active = self.data.get("active_favourite")
        if active is None:
            return None
        try:
            active = int(active)
        except Exception:
            return None
        if active == 255:
            return "None"
        for fav in self._favourites:
            if int(fav.get("favourite_number")) == active:
                return fav.get("name", f"Favourite {active}")
        return str(active)

    async def async_select_option(self, option: str) -> None:
        if option == "None":
            # No explicit action defined for "None"; users can switch to a favourite like "All Auto/All Off" if present.
            raise HomeAssistantError("ConnectMyPool does not provide an explicit 'clear favourite' action.")
        for fav in self._favourites:
            if fav.get("name") == option:
                fav_num = int(fav["favourite_number"])
                await self._do_action(ACTION_SET_FAVOURITE, device_number=fav_num, value="")
                return
        raise HomeAssistantError(f"Unknown favourite: {option}")
