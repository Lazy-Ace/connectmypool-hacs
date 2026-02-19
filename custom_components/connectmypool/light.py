from __future__ import annotations

import asyncio
from typing import Any

from homeassistant.components.light import LightEntity, ColorMode
from homeassistant.const import EntityCategory
from homeassistant.exceptions import HomeAssistantError

from .api import ConnectMyPoolApi, ConnectMyPoolError
from .const import DOMAIN, TRI_MODES
from .entity import ConnectMyPoolEntity

ACTION_SET_LIGHT_MODE = 6
ACTION_SET_LIGHT_COLOR = 7

async def async_setup_entry(hass, entry, async_add_entities):
    data = hass.data[DOMAIN][entry.entry_id]
    coordinator = data["coordinator"]
    api: ConnectMyPoolApi = data["api"]
    cfg: dict[str, Any] = data["config"]
    wait_for_execution: bool = entry.options.get("wait_for_execution", False)

    entities: list[LightEntity] = []
    for lz in (cfg.get("lighting_zones") or []):
        entities.append(LightingZoneLight(coordinator, api, wait_for_execution, lz))
    async_add_entities(entities)

class LightingZoneLight(ConnectMyPoolEntity, LightEntity):
    _attr_color_mode = ColorMode.ONOFF
    _attr_supported_color_modes = {ColorMode.ONOFF}
    _attr_entity_category = EntityCategory.NONE

    def __init__(self, coordinator, api: ConnectMyPoolApi, wait_for_execution: bool, lz: dict[str, Any]) -> None:
        self._api = api
        self._wait = wait_for_execution
        self._lz_number = int(lz["lighting_zone_number"])
        self._color_enabled = bool(lz.get("color_enabled", False))

        name = lz.get("name") or f"Lighting Zone {self._lz_number}"
        super().__init__(coordinator, name, f"lightzone_{self._lz_number}")

        self._effects_by_name: dict[str, int] = {}
        if self._color_enabled:
            for c in (lz.get("colors_available") or []):
                try:
                    num = int(c.get("color_number"))
                    nm = str(c.get("color_name"))
                    self._effects_by_name[nm] = num
                except Exception:
                    continue
            self._attr_effect_list = list(self._effects_by_name.keys())

    @property
    def is_on(self) -> bool | None:
        mode = self._find_mode()
        if mode is None:
            return None
        return int(mode) == 2  # On

    def _find_mode(self) -> int | None:
        for lz in (self.data.get("lighting_zones") or []):
            if int(lz.get("lighting_zone_number")) == self._lz_number:
                try:
                    return int(lz.get("mode"))
                except Exception:
                    return None
        return None

    def _find_color(self) -> int | None:
        for lz in (self.data.get("lighting_zones") or []):
            if int(lz.get("lighting_zone_number")) == self._lz_number:
                col = lz.get("color")
                if col is None:
                    return None
                try:
                    return int(col)
                except Exception:
                    return None
        return None

    @property
    def effect(self) -> str | None:
        if not self._color_enabled:
            return None
        col = self._find_color()
        if col is None:
            return None
        for name, num in self._effects_by_name.items():
            if num == col:
                return name
        return str(col)

    async def async_turn_on(self, **kwargs: Any) -> None:
        try:
            await self._api.pool_action(
                pool_api_code=self.coordinator.pool_api_code,
                action_code=ACTION_SET_LIGHT_MODE,
                device_number=self._lz_number,
                value="2",
                wait_for_execution=self._wait,
            )
            effect = kwargs.get("effect")
            if effect and self._color_enabled and effect in self._effects_by_name:
                await self._api.pool_action(
                    pool_api_code=self.coordinator.pool_api_code,
                    action_code=ACTION_SET_LIGHT_COLOR,
                    device_number=self._lz_number,
                    value=str(self._effects_by_name[effect]),
                    wait_for_execution=self._wait,
                )
            await asyncio.sleep(1.5)
            await self.coordinator.async_request_refresh()
        except ConnectMyPoolError as err:
            raise HomeAssistantError(str(err)) from err

    async def async_turn_off(self, **kwargs: Any) -> None:
        try:
            await self._api.pool_action(
                pool_api_code=self.coordinator.pool_api_code,
                action_code=ACTION_SET_LIGHT_MODE,
                device_number=self._lz_number,
                value="0",
                wait_for_execution=self._wait,
            )
            await asyncio.sleep(1.5)
            await self.coordinator.async_request_refresh()
        except ConnectMyPoolError as err:
            raise HomeAssistantError(str(err)) from err

    async def async_set_effect(self, effect: str) -> None:
        if not self._color_enabled:
            raise HomeAssistantError("This lighting zone does not support colors/effects.")
        if effect not in self._effects_by_name:
            raise HomeAssistantError(f"Unknown effect: {effect}")
        try:
            await self._api.pool_action(
                pool_api_code=self.coordinator.pool_api_code,
                action_code=ACTION_SET_LIGHT_COLOR,
                device_number=self._lz_number,
                value=str(self._effects_by_name[effect]),
                wait_for_execution=self._wait,
            )
            await asyncio.sleep(1.5)
            await self.coordinator.async_request_refresh()
        except ConnectMyPoolError as err:
            raise HomeAssistantError(str(err)) from err
