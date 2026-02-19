# ConnectMyPool (Astral Pool) — Home Assistant Custom Integration (HACS)

This is a **custom** Home Assistant integration for Astral Pool **ConnectMyPool** cloud API (`connectmypool.com.au`).

## Features (v0.1.0)
- Discovers your pool devices via `/api/poolconfig`
- Polls live state via `/api/poolstatus` (cloud polling)
- Entities:
  - Water temperature sensor
  - Selects for:
    - Channel modes (best-effort; API cycles modes)
    - Valve mode (Off/Auto/On)
    - Lighting zone mode (Off/Auto/On)
    - Pool/Spa selection (if supported)
    - Heat/Cool selection (if supported)
    - Solar mode (Off/Auto/On)
    - Active favourite
  - Numbers for:
    - Heater setpoint
    - Solar setpoint
  - Light entity per lighting zone (On/Off + effects where available)
  - Button to re-sync lighting colour (where supported)

## Requirements
- Your pool must be approved for API access in ConnectMyPool and you must have a **Pool API Code** (shown under *Settings → Home Automation* after approval).

## Install via HACS (custom repository)
1. Push this repository to GitHub (public or private).
2. In Home Assistant: **HACS → Integrations → ⋮ → Custom repositories**
3. Paste your repo URL, choose **Integration**, click **Add**.
4. Install, restart Home Assistant.
5. Add integration: **Settings → Devices & services → Add integration → ConnectMyPool**

## Notes / Caveats
- The ConnectMyPool API is rate-limited (the official guide mentions ~60s throttling). Keep polling conservative.
- Some channels (e.g., multi-speed pumps) cannot be set directly; the API can **only cycle** a channel’s mode. The integration attempts to reach the requested mode by cycling and checking status, but this is inherently “best effort”.

## Troubleshooting
- If you get “API Not Enabled” or similar, re-check that Astral have approved API access for your pool and that the Pool API Code is correct.
- If you hit throttling errors, increase the polling interval in the integration options.

## Disclaimer
This is not an official integration. Use at your own risk.
