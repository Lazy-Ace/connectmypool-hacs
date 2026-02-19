from __future__ import annotations

import asyncio
from typing import Any, Optional

from homeassistant.components.climate import ClimateEntity, HVACMode, ClimateEntityFeature
from homeassistant.const import UnitOfTemperature
from homeassistant.exceptions import HomeAssistantError

from .api import ConnectMyPoolApi, ConnectMyPoolError
from .const import (
    DOMAIN,
    ACTION_SET_HEATER_MODE,
    ACTION_SET_HEATER_SET_TEMP,
    ACTION_SET_HEAT_COOL,
    HEATER_MODES,
    HEAT_COOL,
    POOL_SPA,
)
from .entity import ConnectMyPoolEntity


async def async_setup_entry(hass, entry, async_add_entities):
    data = hass.data[DOMAIN][entry.entry_id]
    coordinator = data["coordinator"]
    api: ConnectMyPoolApi = data["api"]
    cfg: dict[str, Any] = data["config"]
    wait_for_execution: bool = data.get("wait_for_execution", True)

    entities: list[ClimateEntity] = []
    for h in (cfg.get("heaters") or []):
        entities.append(ConnectMyPoolHeaterClimate(coordinator, api, wait_for_execution, cfg, h))
    async_add_entities(entities)


class ConnectMyPoolHeaterClimate(ConnectMyPoolEntity, ClimateEntity):
    _attr_supported_features = ClimateEntityFeature.TARGET_TEMPERATURE
    _attr_hvac_modes = [HVACMode.OFF, HVACMode.HEAT]

    def __init__(
        self,
        coordinator,
        api: ConnectMyPoolApi,
        wait_for_execution: bool,
        cfg: dict[str, Any],
        heater_cfg: dict[str, Any],
    ) -> None:
        self._api = api
        self._wait = bool(wait_for_execution)
        self._cfg = cfg
        self._heater_number = int(heater_cfg.get("heater_number", 1))
        name = heater_cfg.get("friendly_name") or heater_cfg.get("name") or (f"Heater {self._heater_number}" if self._heater_number != 1 else "Heater")
        super().__init__(coordinator, name, f"heater_{self._heater_number}")

        self._heat_cool_enabled = bool(cfg.get("heat_cool_selection_enabled"))
        if self._heat_cool_enabled and HVACMode.COOL not in self._attr_hvac_modes:
            self._attr_hvac_modes = [HVACMode.OFF, HVACMode.HEAT, HVACMode.COOL]

    def _unit(self) -> str:
        return UnitOfTemperature.CELSIUS if int(self.coordinator.temperature_scale) == 0 else UnitOfTemperature.FAHRENHEIT

    @property
    def temperature_unit(self) -> str:
        return self._unit()

    @property
    def min_temp(self) -> float:
        return 10 if self.temperature_unit == UnitOfTemperature.CELSIUS else 50

    @property
    def max_temp(self) -> float:
        return 40 if self.temperature_unit == UnitOfTemperature.CELSIUS else 104

    def _find_heater(self) -> dict[str, Any] | None:
        for h in (self.data.get("heaters") or []):
            if int(h.get("heater_number")) == self._heater_number:
                return h
        return None

    def _pool_or_spa(self) -> int:
        # Default to Pool if unknown.
        val = self.data.get("pool_spa_selection")
        try:
            return int(val)
        except Exception:
            return 1

    @property
    def current_temperature(self) -> float | None:
        t = self.data.get("temperature")
        if t is None:
            return None
        try:
            return float(t)
        except Exception:
            return None

    @property
    def target_temperature(self) -> float | None:
        h = self._find_heater()
        if not h:
            return None

        try:
            is_spa = (self._pool_or_spa() == 0) and bool(self._cfg.get("pool_spa_selection_enabled"))
            key = "spa_set_temperature" if is_spa else "set_temperature"
            return float(h.get(key))
        except Exception:
            return None

    @property
    def hvac_mode(self) -> HVACMode | None:
        h = self._find_heater()
        if not h:
            return None
        try:
            heater_mode = int(h.get("mode"))
        except Exception:
            return None

        if heater_mode == 0:
            return HVACMode.OFF

        if not self._heat_cool_enabled:
            return HVACMode.HEAT

        try:
            hc = int(self.data.get("heat_cool_selection", 1))
        except Exception:
            hc = 1
        return HVACMode.HEAT if hc == 1 else HVACMode.COOL

    async def _do_action(self, action_code: int, *, value: str = "") -> None:
        try:
            await self._api.pool_action(
                pool_api_code=self.coordinator.pool_api_code,
                action_code=action_code,
                device_number=self._heater_number,
                value=value,
                temperature_scale=self.coordinator.temperature_scale,
                wait_for_execution=self._wait,
            )
            await asyncio.sleep(1.0)
            await self.coordinator.async_request_refresh()
        except ConnectMyPoolError as err:
            raise HomeAssistantError(str(err)) from err

    async def async_set_hvac_mode(self, hvac_mode: HVACMode) -> None:
        if hvac_mode == HVACMode.OFF:
            await self._do_action(ACTION_SET_HEATER_MODE, value="0")
            return

        if hvac_mode == HVACMode.HEAT:
            if self._heat_cool_enabled:
                await self._do_action(ACTION_SET_HEAT_COOL, value="1")
            await self._do_action(ACTION_SET_HEATER_MODE, value="1")
            return

        if hvac_mode == HVACMode.COOL:
            if not self._heat_cool_enabled:
                raise HomeAssistantError("Cooling mode is not enabled for this pool.")
            await self._do_action(ACTION_SET_HEAT_COOL, value="0")
            await self._do_action(ACTION_SET_HEATER_MODE, value="1")
            return

        raise HomeAssistantError(f"Unsupported hvac_mode: {hvac_mode}")

    async def async_set_temperature(self, **kwargs: Any) -> None:
        temp = kwargs.get("temperature")
        if temp is None:
            return
        # ConnectMyPool expects an integer setpoint.
        try:
            val = str(int(round(float(temp))))
        except Exception as err:
            raise HomeAssistantError(f"Invalid temperature: {temp}") from err

        # Note: The API sets pool or spa setpoint based on the *current* pool/spa selection.
        await self._do_action(ACTION_SET_HEATER_SET_TEMP, value=val)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        return {
            "heater_number": self._heater_number,
            "heater_mode_raw": None if self._find_heater() is None else self._find_heater().get("mode"),
            "pool_spa_selection": POOL_SPA.get(self._pool_or_spa(), str(self._pool_or_spa())),
            "heat_cool_selection": HEAT_COOL.get(int(self.data.get("heat_cool_selection", 1)), str(self.data.get("heat_cool_selection"))),
        }
