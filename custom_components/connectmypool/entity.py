from __future__ import annotations

import hashlib
from typing import Any

from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import ConnectMyPoolCoordinator

def _stable_id(pool_api_code: str) -> str:
    # Avoid storing raw API code in entity unique_ids (paranoia-friendly).
    return hashlib.sha1(pool_api_code.encode("utf-8")).hexdigest()[:12]

class ConnectMyPoolEntity(CoordinatorEntity[ConnectMyPoolCoordinator]):
    def __init__(
        self,
        coordinator: ConnectMyPoolCoordinator,
        name: str,
        unique_suffix: str,
    ) -> None:
        super().__init__(coordinator)
        self._pool_id = _stable_id(coordinator.pool_api_code)
        self._attr_name = name
        self._attr_unique_id = f"{self._pool_id}_{unique_suffix}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, self._pool_id)},
            name="ConnectMyPool Pool",
            manufacturer="AstralPool",
            model="ConnectMyPool",
        )

    @property
    def data(self) -> dict[str, Any]:
        return self.coordinator.data or {}
