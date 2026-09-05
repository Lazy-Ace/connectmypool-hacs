from __future__ import annotations

import asyncio
from typing import Any, Optional

from homeassistant.components.switch import SwitchEntity
from homeassistant.exceptions import HomeAssistantError

from .api import ConnectMyPoolApi, ConnectMyPoolError
from .const import (
    DOMAIN,
    CHANNEL_MODES,
    ACTION_CYCLE_CHANNEL,
    CONF_EXPOSE_CHANNEL_SWITCHES,
    DEFAULT_EXPOSE_CHANNEL_SWITCHES,
)
from .entity import ConnectMyPoolEntity


FILTER_PUMP_FUNCTION = 1
SIMPLE_CHANNEL_MODES = {0, 1, 2}  # Off / Auto / On


def _is_filter_pump_channel(ch: dict[str, Any]) -> bool:
    try:
        return int(ch.get("function")) == FILTER_PUMP_FUNCTION
    except (TypeError, ValueError):
        return False


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
        # Multi-speed filter pumps are exposed as a mode selector instead.
        if _is_filter_pump_channel(ch):
            continue
        entities.append(ChannelSwitch(coordinator, api, wait_for_execution, ch))
    async_add_entities(entities)


class ChannelSwitch(ConnectMyPoolEntity, SwitchEntity):
    """Manual ON/OFF control for a simple ConnectMyPool channel.

    ConnectMyPool exposes a cycle action rather than a direct set-state action,
    so we cycle and verify until the requested Off or On state is reported.
    Auto is treated as neither manually On nor Off for control purposes.
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
        if mode == 2:
            return True
        if mode in (0, 1):
            return False
        return None

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

    async def _cycle_to(self, target: int) -> None:
        current = self._find_mode()
        if current is None:
            await self.coordinator.async_request_refresh()
            current = self._find_mode()

        if current not in SIMPLE_CHANNEL_MODES:
            label = CHANNEL_MODES.get(current, str(current)) if current is not None else "unknown"
            raise HomeAssistantError(
                f"Channel {self._channel_number} reported unexpected mode '{label}'. "
                "Refusing to cycle blindly."
            )

        if current == target:
            return

        # Three states (Off/Auto/On) means no valid target can be more than
        # two cycles away, but allow one extra attempt for controller quirks.
        for _ in range(3):
            previous = current
            await self._cycle_once()
            current = self._find_mode()

            if current == target:
                return

            if current == previous:
                # One extra fresh read before declaring that the command did not move.
                await asyncio.sleep(0.8)
                await self.coordinator.async_request_refresh()
                current = self._find_mode()
                if current == target:
                    return
                if current == previous:
                    raise HomeAssistantError(
                        f"Channel {self._channel_number} did not change state after a cycle command."
                    )

            if current not in SIMPLE_CHANNEL_MODES:
                label = CHANNEL_MODES.get(current, str(current)) if current is not None else "unknown"
                raise HomeAssistantError(
                    f"Channel {self._channel_number} moved to unexpected mode '{label}'. "
                    "Stopped to avoid cycling into the wrong state."
                )

        target_label = CHANNEL_MODES[target]
        raise HomeAssistantError(
            f"Couldn't confirm channel {self._channel_number} in '{target_label}' mode."
        )

    async def async_turn_on(self, **kwargs: Any) -> None:
        await self._cycle_to(2)

    async def async_turn_off(self, **kwargs: Any) -> None:
        await self._cycle_to(0)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        mode = self._find_mode()
        return {
            "channel_number": self._channel_number,
            "function": self._function,
            "mode": None if mode is None else int(mode),
            "mode_label": None if mode is None else CHANNEL_MODES.get(int(mode), str(mode)),
        }
