from __future__ import annotations

import asyncio
from typing import Any, Optional

from homeassistant.components.select import SelectEntity
from homeassistant.exceptions import HomeAssistantError

from .api import ConnectMyPoolApi, ConnectMyPoolError
from .const import (
    DOMAIN,
    CHANNEL_MODES,
    TRI_MODES,
    POOL_SPA,
    HEAT_COOL,
    ACTION_CYCLE_CHANNEL,
    ACTION_SET_VALVE_MODE,
    ACTION_SET_POOL_SPA,
    ACTION_SET_LIGHT_MODE,
    ACTION_SET_ACTIVE_FAVOURITE,
    ACTION_SET_SOLAR_MODE,
    ACTION_SET_HEAT_COOL,
)
from .entity import ConnectMyPoolEntity


async def async_setup_entry(hass, entry, async_add_entities):
    data = hass.data[DOMAIN][entry.entry_id]
    coordinator = data["coordinator"]
    api: ConnectMyPoolApi = data["api"]
    cfg: dict[str, Any] = data["config"]
    wait_for_execution: bool = data.get("wait_for_execution", True)

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

    # Channels (mode select)
    for ch in (cfg.get("channels") or []):
        entities.append(ChannelModeSelect(coordinator, api, wait_for_execution, ch))

    # Valves
    for v in (cfg.get("valves") or []):
        entities.append(ValveModeSelect(coordinator, api, wait_for_execution, v))

    # Solar mode (solar setpoint handled by water_heater entity)
    for s in (cfg.get("solar_systems") or []):
        entities.append(SolarModeSelect(coordinator, api, wait_for_execution, s))

    # Lighting zone mode (Off/Auto/On). On/off + effects handled by light entity.
    for lz in (cfg.get("lighting_zones") or []):
        entities.append(LightingZoneModeSelect(coordinator, api, wait_for_execution, lz))

    async_add_entities(entities)


class _BaseSelect(ConnectMyPoolEntity, SelectEntity):
    def __init__(
        self,
        coordinator,
        api: ConnectMyPoolApi,
        wait_for_execution: bool,
        name: str,
        unique_suffix: str,
    ) -> None:
        super().__init__(coordinator, name, unique_suffix)
        self._api = api
        self._wait = bool(wait_for_execution)

    async def _do_action(self, action_code: int, device_number: int = 0, value: str = "") -> None:
        try:
            await self._api.pool_action(
                pool_api_code=self.coordinator.pool_api_code,
                action_code=action_code,
                device_number=device_number,
                value=value,
                temperature_scale=self.coordinator.temperature_scale,
                wait_for_execution=self._wait,
            )
            await asyncio.sleep(1.0)
            await self.coordinator.async_request_refresh()
        except ConnectMyPoolError as err:
            raise HomeAssistantError(str(err)) from err


class PoolSpaSelect(_BaseSelect):
    _attr_options = list(POOL_SPA.values())

    def __init__(self, coordinator, api, wait_for_execution) -> None:
        super().__init__(coordinator, api, wait_for_execution, "Pool/Spa Selection", "pool_spa_selection")

    @property
    def current_option(self) -> str | None:
        val = self.data.get("pool_spa_selection")
        if val is None:
            return None
        try:
            return POOL_SPA.get(int(val), str(val))
        except Exception:
            return None

    async def async_select_option(self, option: str) -> None:
        desired = next((k for k, v in POOL_SPA.items() if v == option), None)
        if desired is None:
            raise HomeAssistantError(f"Unsupported option: {option}")
        await self._do_action(ACTION_SET_POOL_SPA, value=str(desired))


class HeatCoolSelect(_BaseSelect):
    _attr_options = list(HEAT_COOL.values())

    def __init__(self, coordinator, api, wait_for_execution) -> None:
        super().__init__(coordinator, api, wait_for_execution, "Heat/Cool Selection", "heat_cool_selection")

    @property
    def current_option(self) -> str | None:
        val = self.data.get("heat_cool_selection")
        if val is None:
            return None
        try:
            return HEAT_COOL.get(int(val), str(val))
        except Exception:
            return None

    async def async_select_option(self, option: str) -> None:
        desired = next((k for k, v in HEAT_COOL.items() if v == option), None)
        if desired is None:
            raise HomeAssistantError(f"Unsupported option: {option}")
        await self._do_action(ACTION_SET_HEAT_COOL, value=str(desired))


class ActiveFavouriteSelect(_BaseSelect):
    def __init__(self, coordinator, api, wait_for_execution, favs: list[dict[str, Any]]) -> None:
        self._by_number: dict[int, str] = {}
        for f in favs:
            try:
                num = int(f.get("favourite_number"))
                name = str(f.get("name") or f"Favourite {num}")
                self._by_number[num] = name
            except Exception:
                continue
        super().__init__(coordinator, api, wait_for_execution, "Active Favourite", "active_favourite")
        self._attr_options = list(self._by_number.values())

    @property
    def current_option(self) -> str | None:
        val = self.data.get("active_favourite")
        if val is None:
            return None
        try:
            num = int(val)
        except Exception:
            return None
        # 255 indicates no active favourite (per guide)
        if num == 255:
            return None
        return self._by_number.get(num)

    async def async_select_option(self, option: str) -> None:
        desired_num = next((k for k, v in self._by_number.items() if v == option), None)
        if desired_num is None:
            raise HomeAssistantError(f"Unknown favourite: {option}")
        await self._do_action(ACTION_SET_ACTIVE_FAVOURITE, value=str(desired_num))


class ChannelModeSelect(_BaseSelect):
    def __init__(self, coordinator, api, wait_for_execution, ch: dict[str, Any]) -> None:
        self._channel_number = int(ch["channel_number"])
        self._function = ch.get("function")
        friendly = ch.get("name") or f"Channel {self._channel_number}"
        super().__init__(coordinator, api, wait_for_execution, f"{friendly} Mode", f"channel_{self._channel_number}_mode")

        # Best-effort options (API cycles channel modes; device may support a subset).
        self._attr_options = list(CHANNEL_MODES.values())

    def _find_mode(self) -> Optional[int]:
        for c in (self.data.get("channels") or []):
            if int(c.get("channel_number")) == self._channel_number:
                try:
                    return int(c.get("mode"))
                except Exception:
                    return None
        return None

    @property
    def current_option(self) -> str | None:
        mode = self._find_mode()
        if mode is None:
            return None
        return CHANNEL_MODES.get(mode, str(mode))

    async def async_select_option(self, option: str) -> None:
        desired = next((k for k, v in CHANNEL_MODES.items() if v == option), None)
        if desired is None:
            raise HomeAssistantError(f"Unsupported option: {option}")

        # Cycle until we hit the requested mode (up to 8 attempts).
        for _ in range(8):
            current = self._find_mode()
            if current == desired:
                return
            await self._do_action(ACTION_CYCLE_CHANNEL, device_number=self._channel_number, value="")
            await asyncio.sleep(0.8)
            await self.coordinator.async_request_refresh()

        raise HomeAssistantError(
            f"Couldn't reach mode '{option}' by cycling. This channel may not support that mode."
        )

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        return {
            "channel_number": self._channel_number,
            "function": self._function,
        }


class ValveModeSelect(_BaseSelect):
    _attr_options = list(TRI_MODES.values())

    def __init__(self, coordinator, api, wait_for_execution, valve: dict[str, Any]) -> None:
        self._valve_number = int(valve["valve_number"])
        self._function = valve.get("function")
        friendly = valve.get("name") or f"Valve {self._valve_number}"
        super().__init__(coordinator, api, wait_for_execution, f"{friendly} Mode", f"valve_{self._valve_number}_mode")

    def _find_mode(self) -> Optional[int]:
        for v in (self.data.get("valves") or []):
            if int(v.get("valve_number")) == self._valve_number:
                try:
                    return int(v.get("mode"))
                except Exception:
                    return None
        return None

    @property
    def current_option(self) -> str | None:
        mode = self._find_mode()
        if mode is None:
            return None
        return TRI_MODES.get(mode, str(mode))

    async def async_select_option(self, option: str) -> None:
        desired = next((k for k, v in TRI_MODES.items() if v == option), None)
        if desired is None:
            raise HomeAssistantError(f"Unsupported option: {option}")
        await self._do_action(ACTION_SET_VALVE_MODE, device_number=self._valve_number, value=str(desired))

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        return {
            "valve_number": self._valve_number,
            "function": self._function,
        }


class SolarModeSelect(_BaseSelect):
    _attr_options = list(TRI_MODES.values())

    def __init__(self, coordinator, api, wait_for_execution, solar: dict[str, Any]) -> None:
        self._solar_number = int(solar["solar_number"])
        friendly = solar.get("name") or f"Solar {self._solar_number}"
        super().__init__(coordinator, api, wait_for_execution, f"{friendly} Mode", f"solar_{self._solar_number}_mode")

    def _find_mode(self) -> Optional[int]:
        for s in (self.data.get("solar_systems") or []):
            if int(s.get("solar_number")) == self._solar_number:
                try:
                    return int(s.get("mode"))
                except Exception:
                    return None
        return None

    @property
    def current_option(self) -> str | None:
        mode = self._find_mode()
        if mode is None:
            return None
        return TRI_MODES.get(mode, str(mode))

    async def async_select_option(self, option: str) -> None:
        desired = next((k for k, v in TRI_MODES.items() if v == option), None)
        if desired is None:
            raise HomeAssistantError(f"Unsupported option: {option}")
        await self._do_action(ACTION_SET_SOLAR_MODE, device_number=self._solar_number, value=str(desired))

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        return {"solar_number": self._solar_number}


class LightingZoneModeSelect(_BaseSelect):
    _attr_options = list(TRI_MODES.values())

    def __init__(self, coordinator, api, wait_for_execution, lz: dict[str, Any]) -> None:
        self._lz_number = int(lz["lighting_zone_number"])
        friendly = lz.get("name") or f"Lighting Zone {self._lz_number}"
        super().__init__(coordinator, api, wait_for_execution, f"{friendly} Mode", f"lightzone_{self._lz_number}_mode")

    def _find_mode(self) -> Optional[int]:
        for lz in (self.data.get("lighting_zones") or []):
            if int(lz.get("lighting_zone_number")) == self._lz_number:
                try:
                    return int(lz.get("mode"))
                except Exception:
                    return None
        return None

    @property
    def current_option(self) -> str | None:
        mode = self._find_mode()
        if mode is None:
            return None
        return TRI_MODES.get(mode, str(mode))

    async def async_select_option(self, option: str) -> None:
        desired = next((k for k, v in TRI_MODES.items() if v == option), None)
        if desired is None:
            raise HomeAssistantError(f"Unsupported option: {option}")
        await self._do_action(ACTION_SET_LIGHT_MODE, device_number=self._lz_number, value=str(desired))

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        return {"lighting_zone_number": self._lz_number}
