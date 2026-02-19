from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Any

import aiohttp

from .const import DEFAULT_BASE_URL

class ConnectMyPoolError(Exception):
    """Base error."""

class ConnectMyPoolAuthError(ConnectMyPoolError):
    """Auth / API code error."""

class ConnectMyPoolThrottleError(ConnectMyPoolError):
    """Rate limit / throttle."""

@dataclass
class ApiResult:
    data: dict[str, Any]

def _raise_for_failure(payload: dict[str, Any]) -> None:
    # API errors are returned as: { failure_code: int, failure_description: str }
    if "failure_code" in payload:
        code = payload.get("failure_code")
        desc = payload.get("failure_description", "Unknown error")
        if code in (3, 4, 5):  # Invalid API Code / API Not Enabled / Invalid API Key
            raise ConnectMyPoolAuthError(f"{code}: {desc}")
        if code == 6:  # Time Throttle Exceeded
            raise ConnectMyPoolThrottleError(f"{code}: {desc}")
        raise ConnectMyPoolError(f"{code}: {desc}")

class ConnectMyPoolApi:
    def __init__(self, session: aiohttp.ClientSession, base_url: str = DEFAULT_BASE_URL) -> None:
        self._session = session
        self._base_url = base_url.rstrip("/")

    async def _post(self, path: str, json_data: dict[str, Any]) -> dict[str, Any]:
        url = f"{self._base_url}{path}"
        async with self._session.post(url, json=json_data, timeout=aiohttp.ClientTimeout(total=30)) as resp:
            # ConnectMyPool typically returns JSON
            resp.raise_for_status()
            payload = await resp.json(content_type=None)
        if isinstance(payload, list):
            # Some clients have seen list payloads; normalize.
            if payload:
                payload = payload[0]
            else:
                payload = {}
        if not isinstance(payload, dict):
            raise ConnectMyPoolError(f"Unexpected payload type: {type(payload)}")
        _raise_for_failure(payload)
        return payload

    async def pool_config(self, pool_api_code: str) -> dict[str, Any]:
        return await self._post("/api/poolconfig", {"pool_api_code": pool_api_code})

    async def pool_status(self, pool_api_code: str, temperature_scale: int = 0) -> dict[str, Any]:
        # temperature_scale: 0=C, 1=F (per docs)
        return await self._post(
            "/api/poolstatus",
            {"pool_api_code": pool_api_code, "temperature_scale": temperature_scale},
        )

    async def pool_action(
        self,
        pool_api_code: str,
        action_code: int,
        device_number: int = 0,
        value: str = "",
        wait_for_execution: bool = False,
    ) -> dict[str, Any]:
        # Docs and community examples use "value" (string). Some older docs mention "string".
        return await self._post(
            "/api/poolaction",
            {
                "pool_api_code": pool_api_code,
                "action_code": action_code,
                "device_number": device_number,
                "value": value,
                "wait_for_execution": wait_for_execution,
            },
        )

    async def pool_action_status(self, pool_api_code: str, action_number: int) -> dict[str, Any]:
        return await self._post(
            "/api/poolactionstatus",
            {"pool_api_code": pool_api_code, "action_number": action_number},
        )

    async def safe_refresh_after_action(self, delay_s: float = 2.0) -> None:
        await asyncio.sleep(delay_s)
