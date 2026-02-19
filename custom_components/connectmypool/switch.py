from __future__ import annotations

import asyncio
from typing import Any, Optional

from homeassistant.components.switch import SwitchEntity
from homeassistant.exceptions import HomeAssistantError

from .api import ConnectMyPoolApi, ConnectMyPoolError
from .const import DOMAIN, CHANNEL_MODES, ACTION_CYCLE_CHANNEL, CONF_EXPOSE_CHANNEL_SWITCHES, DEFAULT_EXPOSE_CHANNEL_SWITCHES
from .entity import ConnectMyPoolEntity


async def async_setup_entry(hass, entry, async_add_entities):
    if not entry.options.get(CONF_EXPOSE_CHANNEL_SWITCHES, DEFAULT_EXPOSE_CHANNEL_SWITCHES):
        return

    data = hass.data[DOMAIN][entry.entry_id]
    coordinator = data["coordinator"]
    api: ConnectMyPoolApi = data["api"]
    cfg: dict[str, Any] = data["config"]
    wait_for_execution: bool = data.get("wait_for_execution", True)

    entities: list[SwitchEntity] = []
    for ch in (cfg.get("channels") or []):
        entities.append(ChannelSwitch(coordinator, api, wait_for_execution, ch))
    async_add_entities(entities)


class ChannelSwitch(ConnectMyPoolEntity, SwitchEntity):
    """Convenience ON/OFF switch for a channel.

    Under the hood, ConnectMyPool only supports *cycling* channel modes.
    This entity cycles until it reaches the desired state.
    """

    def __init__(self, coordinator, api: ConnectMyPoolApi, wait_for_execution: bool, ch: dict[str, Any]) -> None:
        self._api = api
        self._wait = bool(wait_for_execution)
        self._channel_number = int(ch["channel_number"])
        self._function = ch.get("function")
        friendly = ch.get("friendly_name") or ch.get("name") or f"Channel {self._channel_number}"
        super().__init__(coordinator, friendly, f"channel_{self._channel_number}_switch")

    def _find_mode(self) -> Optional[int]:
        for c in (self.data.get("channels") or []):
            if int(c.get("channel_number")) == self._channel_number:
                try:
                    return int(c.get("mode"))
                except Exception:
                    return None
        return None

    @property
    def is_on(self) -> bool | None:
        mode = self._find_mode()
        if mode is None:
            return None
        return int(mode) != 0

    async def _cycle_once(self) -> None:
        try:
            await self._api.pool_action(
                pool_api_code=self.coordinator.pool_api_code,
                action_code=ACTION_CYCLE_CHANNEL,
                device_number=self._channel_number,
                value="",
                temperature_scale=self.coordinator.temperature_scale,
                wait_for_execution=self._wait,
            )
            await asyncio.sleep(1.0)
            await self.coordinator.async_request_refresh()
        except ConnectMyPoolError as err:
            raise HomeAssistantError(str(err)) from err

    async def async_turn_on(self, **kwargs: Any) -> None:
        desired_on = {2, 3, 4, 5}
        for _ in range(8):
            mode = self._find_mode()
            if mode in desired_on:
                return
            # If it isn't off, we consider it "on enough" (e.g., Auto)
            if mode is not None and mode != 0:
                return
            await self._cycle_once()

        # Final grace: if we reached a non-off mode, treat as success.
        mode = self._find_mode()
        if mode is not None and mode != 0:
            return
        raise HomeAssistantError("Couldn't turn channel on (cycle did not reach a non-off mode).")

    async def async_turn_off(self, **kwargs: Any) -> None:
        for _ in range(8):
            mode = self._find_mode()
            if mode == 0:
                return
            await self._cycle_once()

        raise HomeAssistantError("Couldn't turn channel off (cycle did not reach Off).")

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        mode = self._find_mode()
        return {
            "channel_number": self._channel_number,
            "function": self._function,
            "mode": None if mode is None else int(mode),
            "mode_label": None if mode is None else CHANNEL_MODES.get(int(mode), str(mode)),
        }
