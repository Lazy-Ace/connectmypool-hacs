from __future__ import annotations

from homeassistant.components.sensor import SensorEntity
from homeassistant.const import UnitOfTemperature

from .const import DOMAIN
from .entity import ConnectMyPoolEntity


async def async_setup_entry(hass, entry, async_add_entities):
    data = hass.data[DOMAIN][entry.entry_id]
    coordinator = data["coordinator"]
    async_add_entities([PoolTemperatureSensor(coordinator)])


class PoolTemperatureSensor(ConnectMyPoolEntity, SensorEntity):
    _attr_icon = "mdi:pool-thermometer"

    def __init__(self, coordinator) -> None:
        super().__init__(coordinator, "Pool Water Temperature", "water_temp")

    @property
    def native_unit_of_measurement(self) -> str:
        return UnitOfTemperature.CELSIUS if int(self.coordinator.temperature_scale) == 0 else UnitOfTemperature.FAHRENHEIT

    @property
    def native_value(self) -> float | None:
        t = self.data.get("temperature")
        if t is None:
            return None
        try:
            return float(t)
        except Exception:
            return None
