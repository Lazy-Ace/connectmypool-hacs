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
SIMPLE_CHANNEL_CYCLE = (0, 1, 2)  # Off -> Auto -> On -> Off


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

    The V10 cycles these channels Off -> Auto -> On -> Off.  Home Assistant's
    switch represents the explicit manual On state; Auto is deliberately shown
    as not manually on.  Changes are serialised and the required cycle actions
    are batched before a single verification refresh to avoid unnecessary API
    traffic.
    """

    def __init__(self, coordinator, api: ConnectMyPoolApi, wait_for_execution: bool, ch: dict[str, Any]) -> None:
        self._api = api
        self._wait = bool(wait_for_execution)
        self._channel_number = int(ch["channel_number"])
        self._function = ch.get("function")
        self._mode_lock = asyncio.Lock()
        self._latest_target: int | None = None
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

    async def _send_cycle(self, *, wait_for_execution: bool) -> None:
        try:
            await self._api.pool_action(
                pool_api_code=self.coordinator.pool_api_code,
                action_code=ACTION_CYCLE_CHANNEL,
                device_number=self._channel_number,
                value="",
                temperature_scale=self.coordinator.temperature_scale,
                wait_for_execution=wait_for_execution,
            )
        except ConnectMyPoolError as err:
            raise HomeAssistantError(str(err)) from err

    async def _refresh_and_read(self, delay: float) -> int | None:
        if delay > 0:
            await asyncio.sleep(delay)
        await self.coordinator.async_request_refresh()
        return self._find_mode()

    async def _set_target_locked(self, target: int) -> None:
        current = self._find_mode()
        if current is None:
            current = await self._refresh_and_read(0)

        if current not in SIMPLE_CHANNEL_CYCLE:
            label = CHANNEL_MODES.get(current, str(current)) if current is not None else "unknown"
            raise HomeAssistantError(
                f"Channel {self._channel_number} reported unexpected mode '{label}'. "
                "Refusing to cycle blindly."
            )

        if current == target:
            return

        current_index = SIMPLE_CHANNEL_CYCLE.index(current)
        target_index = SIMPLE_CHANNEL_CYCLE.index(target)
        steps = (target_index - current_index) % len(SIMPLE_CHANNEL_CYCLE)

        for step in range(steps):
            is_final = step == steps - 1
            await self._send_cycle(
                wait_for_execution=self._wait if is_final else False,
            )
            if not is_final:
                await asyncio.sleep(0.2)

        observed = await self._refresh_and_read(0.75)
        if observed != target:
            observed = await self._refresh_and_read(1.5)

        if observed != target:
            target_label = CHANNEL_MODES[target]
            observed_label = (
                CHANNEL_MODES.get(observed, str(observed))
                if observed is not None
                else "unknown"
            )
            raise HomeAssistantError(
                f"Couldn't confirm channel {self._channel_number} in '{target_label}' mode; "
                f"controller reported '{observed_label}'. No further cycles were sent."
            )

    async def _request_target(self, target: int) -> None:
        self._latest_target = target
        async with self._mode_lock:
            while True:
                requested = self._latest_target
                if requested is None:
                    return
                await self._set_target_locked(requested)
                if self._latest_target == requested:
                    return

    async def async_turn_on(self, **kwargs: Any) -> None:
        await self._request_target(2)

    async def async_turn_off(self, **kwargs: Any) -> None:
        await self._request_target(0)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        mode = self._find_mode()
        return {
            "channel_number": self._channel_number,
            "function": self._function,
            "mode": None if mode is None else int(mode),
            "mode_label": None if mode is None else CHANNEL_MODES.get(int(mode), str(mode)),
            "cycle_sequence": [CHANNEL_MODES[mode] for mode in SIMPLE_CHANNEL_CYCLE],
        }
