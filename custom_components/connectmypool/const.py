from __future__ import annotations

DOMAIN = "connectmypool"

CONF_POOL_API_CODE = "pool_api_code"
CONF_BASE_URL = "base_url"
CONF_TEMPERATURE_SCALE = "temperature_scale"
CONF_SCAN_INTERVAL = "scan_interval"
CONF_WAIT_FOR_EXECUTION = "wait_for_execution"

DEFAULT_BASE_URL = "https://www.connectmypool.com.au"
DEFAULT_TEMPERATURE_SCALE = 0  # 0=C, 1=F
DEFAULT_SCAN_INTERVAL = 60  # seconds (API is commonly throttled ~60s)
DEFAULT_WAIT_FOR_EXECUTION = False

PLATFORMS: list[str] = ["sensor", "select", "number", "light", "button"]

# Status enums (per ConnectMyPool docs)
CHANNEL_MODES = {
    0: "Off",
    1: "Auto",
    2: "On",
    3: "Low Speed",
    4: "Medium Speed",
    5: "High Speed",
}

TRI_MODES = {
    0: "Off",
    1: "Auto",
    2: "On",
}

HEATER_MODES = {
    0: "Off",
    1: "On",
}

POOL_SPA = {
    0: "Spa",
    1: "Pool",
}

HEAT_COOL = {
    0: "Cooling",
    1: "Heating",
}
