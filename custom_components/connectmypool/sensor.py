from __future__ import annotations

from typing import Any

from homeassistant.components.sensor import SensorEntity, SensorDeviceClass
from homeassistant.const import UnitOfTemperature

from .const import DOMAIN
from .entity import ConnectMyPoolEntity

async def async_setup_entry(hass, entry, async_add_entities):
    data = hass.data[DOMAIN][entry.entry_id]
    coordinator = data["coordinator"]
    temp_scale = coordinator.temperature_scale

    unit = UnitOfTemperature.CELSIUS if temp_scale == 0 else UnitOfTemperature.FAHRENHEIT

    entities: list[SensorEntity] = [
        PoolTemperatureSensor(coordinator, unit),
    ]
    async_add_entities(entities)

class PoolTemperatureSensor(ConnectMyPoolEntity, SensorEntity):
    _attr_device_class = SensorDeviceClass.TEMPERATURE

    def __init__(self, coordinator, unit) -> None:
        super().__init__(coordinator, "Pool Water Temperature", "water_temperature")
        self._attr_native_unit_of_measurement = unit

    @property
    def native_value(self):
        return self.data.get("temperature")
