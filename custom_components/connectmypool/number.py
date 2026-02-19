from __future__ import annotations

import asyncio
from typing import Any

from homeassistant.components.number import NumberEntity
from homeassistant.const import EntityCategory
from homeassistant.exceptions import HomeAssistantError

from .api import ConnectMyPoolApi, ConnectMyPoolError
from .const import DOMAIN

from .entity import ConnectMyPoolEntity

ACTION_SET_HEATER_SET_TEMP = 5
ACTION_SET_SOLAR_SET_TEMP = 10

async def async_setup_entry(hass, entry, async_add_entities):
    data = hass.data[DOMAIN][entry.entry_id]
    coordinator = data["coordinator"]
    api: ConnectMyPoolApi = data["api"]
    cfg: dict[str, Any] = data["config"]
    wait_for_execution: bool = entry.options.get("wait_for_execution", False)

    entities: list[NumberEntity] = []

    for heater in (cfg.get("heaters") or []):
        entities.append(HeaterSetTempNumber(coordinator, api, wait_for_execution, heater))

    for solar in (cfg.get("solar_systems") or []):
        entities.append(SolarSetTempNumber(coordinator, api, wait_for_execution, solar))

    async_add_entities(entities)

class _BaseNumber(ConnectMyPoolEntity, NumberEntity):
    _attr_entity_category = EntityCategory.CONFIG

    def __init__(self, coordinator, api: ConnectMyPoolApi, wait_for_execution: bool, name: str, unique_suffix: str) -> None:
        super().__init__(coordinator, name, unique_suffix)
        self._api = api
        self._wait = wait_for_execution
        # Docs suggest heater/solar set temp ranges:
        # 10-40C / 50-104F
        self._attr_min_value = 10
        self._attr_max_value = 40
        self._attr_step = 1

    async def _do_action(self, action_code: int, device_number: int, value: int) -> None:
        try:
            await self._api.pool_action(
                pool_api_code=self.coordinator.pool_api_code,
                action_code=action_code,
                device_number=device_number,
                value=str(int(value)),
                wait_for_execution=self._wait,
            )
            await asyncio.sleep(1.5)
            await self.coordinator.async_request_refresh()
        except ConnectMyPoolError as err:
            raise HomeAssistantError(str(err)) from err

class HeaterSetTempNumber(_BaseNumber):
    def __init__(self, coordinator, api, wait_for_execution, heater: dict[str, Any]) -> None:
        self._heater_number = int(heater["heater_number"])
        super().__init__(coordinator, api, wait_for_execution, f"Heater {self._heater_number} Set Temperature", f"heater_{self._heater_number}_set_temp")

    @property
    def native_value(self):
        for h in (self.data.get("heaters") or []):
            if int(h.get("heater_number")) == self._heater_number:
                # If in pool/spa combined, HA can still show pool setpoint;
                # users can change Pool/Spa selection then setpoint.
                return h.get("set_temperature")
        return None

    async def async_set_native_value(self, value: float) -> None:
        await self._do_action(ACTION_SET_HEATER_SET_TEMP, device_number=self._heater_number, value=int(value))

class SolarSetTempNumber(_BaseNumber):
    def __init__(self, coordinator, api, wait_for_execution, solar: dict[str, Any]) -> None:
        self._solar_number = int(solar["solar_number"])
        super().__init__(coordinator, api, wait_for_execution, f"Solar {self._solar_number} Set Temperature", f"solar_{self._solar_number}_set_temp")

    @property
    def native_value(self):
        for s in (self.data.get("solar_systems") or []):
            if int(s.get("solar_number")) == self._solar_number:
                return s.get("set_temperature")
        return None

    async def async_set_native_value(self, value: float) -> None:
        await self._do_action(ACTION_SET_SOLAR_SET_TEMP, device_number=self._solar_number, value=int(value))
