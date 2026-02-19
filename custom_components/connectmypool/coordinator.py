from __future__ import annotations

from datetime import timedelta
import logging
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import (
    ConnectMyPoolApi,
    ConnectMyPoolError,
    ConnectMyPoolThrottleError,
    ConnectMyPoolNotConnectedError,
)
from .const import DEFAULT_SCAN_INTERVAL

_LOGGER = logging.getLogger(__name__)


class ConnectMyPoolCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """Coordinator fetching pool status."""

    def __init__(
        self,
        hass: HomeAssistant,
        api: ConnectMyPoolApi,
        pool_api_code: str,
        temperature_scale: int,
        scan_interval: int,
    ) -> None:
        super().__init__(
            hass,
            _LOGGER,
            name="ConnectMyPool",
            update_interval=timedelta(seconds=max(DEFAULT_SCAN_INTERVAL, int(scan_interval))),
        )
        self.api = api
        self.pool_api_code = pool_api_code
        self.temperature_scale = int(temperature_scale)

    async def _async_update_data(self) -> dict[str, Any]:
        try:
            return await self.api.pool_status(
                self.pool_api_code,
                temperature_scale=self.temperature_scale,
            )
        except ConnectMyPoolThrottleError as err:
            # If throttled, api.pool_status may already have returned cached data.
            raise UpdateFailed(f"Throttled: {err}") from err
        except ConnectMyPoolNotConnectedError as err:
            raise UpdateFailed(f"Pool not connected: {err}") from err
        except ConnectMyPoolError as err:
            raise UpdateFailed(str(err)) from err
        except Exception as err:  # noqa: BLE001
            raise UpdateFailed(f"Unexpected error: {err}") from err
