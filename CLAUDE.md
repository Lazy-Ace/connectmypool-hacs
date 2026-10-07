# ConnectMyPool — Home Assistant integration (CLAUDE.md)

Durable guidance for working on this repo. For the latest in-progress state and
session history, see `docs/SESSION_HANDOFF.md`.

## Purpose
Custom HACS integration (`domain: connectmypool`) for an **AstralPool Viron
Connect 10** pool controller, via the unofficial **ConnectMyPool** cloud API
(`https://www.connectmypool.com.au`). Companion Lovelace card lives in a
separate repo: `Lazy-Ace/lovelace-connectmypool-card`.

## Architecture
- `api.py` — async `ConnectMyPoolApi`. Endpoints: `/api/poolconfig`,
  `/api/poolstatus`, `/api/poolaction`, `/api/poolactionstatus`. Typed errors
  (`ConnectMyPoolAuthError`, `ConnectMyPoolThrottleError`,
  `ConnectMyPoolNotConnectedError`, `ConnectMyPoolActionError`). Caches
  config/status to survive the ~60s cloud throttle; a ~5-min "fast poll" window
  opens after any action. `pool_action` is serialised by an asyncio lock.
- `coordinator.py` — `DataUpdateCoordinator` polling `pool_status` every
  `max(60, scan_interval)` seconds.
- `entity.py` — base `ConnectMyPoolEntity`; unique_id = `sha1(api_code)[:12] +
  "_" + suffix`; `suggested_object_id = connectmypool_<suffix>`.
- `const.py` — enums (`CHANNEL_MODES`, `TRI_MODES`, …), action codes, defaults.
- `cycle.py` — **pure** channel state-machine arithmetic (no HA/network), unit
  tested. `cycle_steps(current, desired, cycle)`, `next_in_cycle(current, cycle)`.
- Platforms: `sensor`, `select`, `switch`, `light`, `button`, `climate`,
  `water_heater`, `number`. **Channels are `select` entities** (see below);
  `switch.py` deliberately creates no channel entities. Heater/solar/lighting/
  valve/pool-spa/favourite use direct `ACTION_SET_*` value actions (single-shot,
  reliable) — only **channels** use the cycle action.

## Connect 10 channel model (verified on live hardware)
Channels have no "set to mode X" API — only a single-step **cycle** action
(`ACTION_CYCLE_CHANNEL`, device_number = channel_number) that advances one step.

| Channel | # | function | cycle (mode ints) | HA entity |
|---|---|---|---|---|
| Filter Pump | 0 | 1 | Off→Auto→Medium→High  (0,1,4,5) | `select.connectmypool_filter_pump_mode` |
| Spa Jets | 1 | 12 | Off→Auto→On  (0,1,2) | `select.connectmypool_jets_mode` |
| Spa Blower | 2 | 18 | Off→Auto→On  (0,1,2) | `select.connectmypool_blower_mode` |
| Heater Pump | 3 | 3 | Off→Auto→On  (0,1,2) | heater-pump channel select — **DISABLED by default** |

Cycle definitions: `cycle.FILTER_PUMP_CYCLE = (0,1,4,5)`,
`cycle.SIMPLE_CHANNEL_CYCLE = (0,1,2)`. Filter pump is detected by `function == 1`;
heater pump by `function == 3` or name containing "heat".

## Important API behaviour (drives the channel control design)
- A cycle action is acknowledged by the cloud on **acceptance, not physical
  execution**. Sending the next cycle before the controller applies the previous
  one makes it silently drop ("accepted but not applied").
- `poolstatus` **lags** the controller by several seconds (observed ~10s) and can
  be stale/jumpy. Do **not** rely on an immediate status read to confirm a step.
- Therefore channel mode changes: read a **fresh** status first (cached value can
  mis-count steps), send **exactly** the required number of cycles **paced by a
  fixed time settle** (`_INTER_STEP_SETTLE ≈ 12s`), then confirm **best-effort**
  (warn, never error, never overshoot) and let the coordinator reconcile.
- Use `coordinator.async_refresh()` (awaited fetch), **not**
  `async_request_refresh()` (debounced, returns before data arrives), when a fresh
  read is needed.

## Safety constraints
- **Heater Pump (channel 3)**: its select is `entity_registry_enabled_default =
  False`. Do NOT enable or actuate it without explicit user approval — it
  energises heating circulation and the physical heater has been faulty.
- When live-testing controls, only operate **Filter Pump, Spa Jets, Spa Blower**,
  one at a time, verify before/after, and restore the original state. Do not run
  pump/blower for extended periods. Never use "All Off"/"All Auto" favourites,
  valves, solar, or lighting for tests without approval.
- Do not log or expose the pool API code or any secrets.

## Testing & deployment workflow
- Unit tests: `python -m pytest tests/ -q` (pure `cycle.py` logic; no HA needed).
- Deployment target: `/config/custom_components/connectmypool/` on the HA host.
  **Backups must NOT live under `custom_components/`** — HA scans every folder
  with a `manifest.json` and a stray copy breaks the integration. Keep backups
  outside that directory.
- A new module or changed module requires a **full HA restart** (a config-entry
  reload does not re-import changed Python).
- After deploy: confirm clean load (`get_error_log`), entities present, no
  tracebacks, then live-test within the safe scope.

## Home Assistant access via hass-mcp
These MCP tools are used for diagnosis/testing (read-only unless noted):
`get_version`, `search_entities_tool`, `get_entity`, `get_history`,
`get_error_log`, `list_entities`; `call_service_tool` (e.g. `select.select_option`
to actuate), `restart_ha`. The MCP has **no filesystem access** — deploy files
out-of-band (Samba share `\\HOMEASSISTANT\config`, File editor add-on, or SSH).
Entity state reads can be **stale** due to cloud lag; prefer `get_history` for
ground truth after a command.

## Known limitations
- ConnectMyPool cloud status lag is inherent/unbounded: commands converge
  reliably but cannot be confirmed synchronously; a `WARNING` may be logged and
  the entity may briefly show a stale value until the next poll.
- Mode changes take ~12s per extra cycle step; service calls can appear to time
  out at the caller while HA completes the operation.
- `config_flow.py` still exposes an inert "expose channel switches" option
  (channels are always selects now).

## Repository conventions
- Integration version in `manifest.json` (currently `1.0.6`); HACS metadata in
  `hacs.json`. Keep both in step when releasing.
- Keep pure logic (e.g. `cycle.py`) separate from HA/network code so it stays
  unit-testable.
- Make small, reviewable, single-concern commits; do not bundle unrelated
  cleanup with functional fixes.
