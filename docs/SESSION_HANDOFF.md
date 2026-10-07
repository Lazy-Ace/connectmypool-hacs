# ConnectMyPool — Session Handoff

Detailed state for a fresh Claude Code session to continue safely with no prior
conversation history. Durable guidance is in the repo-root `CLAUDE.md`.

## Snapshot
- **Date:** 2026-10-07
- **Repo:** `Lazy-Ace/connectmypool-hacs` (public). Companion card repo:
  `Lazy-Ace/lovelace-connectmypool-card`.
- **Starting point:** commit `25275b9` ("Advertise ConnectMyPool 1.0.6 in HACS"),
  integration `manifest.json` version `1.0.6`.
- **Working branch:** `fix/reliability-live-validation` (created off `25275b9`).
- **Branch HEAD:** `dbc4a06`.
- **Status:** Diagnosis, patch, deploy, and live testing **COMPLETE and PASSING**.
  Code is deployed to the live HA host and validated. **Not yet pushed to GitHub**
  (see Outstanding). The branch *ref* exists on GitHub (at `main`'s SHA); the
  commits exist only in the local clone + as a bundle (paths below).

## Live HA environment
- HA host reachable at `http://192.168.1.50:8123`; Samba share `\\HOMEASSISTANT\config`
  (writable from the dev machine).
- Integration installed at `/config/custom_components/connectmypool/`.
- Pool device: AstralPool Viron Connect 10. Pool water temp sensor read 24.0 °C.
- Integration loads cleanly after the work — only the benign "custom integration
  not tested by Home Assistant" warning; no errors/tracebacks.

## Defects diagnosed
1. **Batched cycle presses, no per-step execution (PRIMARY).** Old
   `_set_mode_locked` (in `select.py` and the old `switch.py`) computed N and fired
   all N cycle actions up front with `wait_for_execution=False` on all but the
   last, 0.2s apart, verifying only the final state. The cloud ACKs a cycle on
   acceptance, not execution, so presses sent too fast were dropped → "accepted
   but not applied". Hit every Off→On (2 steps) and filter Auto→High (2 steps).
2. **Multi-state channels modelled as binary switches.** Jets/Blower/Heater-Pump
   were on/off switches hiding the real Off/Auto/On state.
3. **Stale reads.** Verification used debounced `async_request_refresh()` then read
   immediately (stale); the initial `current` read also came from cached data,
   mis-counting steps.
4. **No automated tests.**
Healthy and left unchanged: `api.py` robustness, coordinator, config-entry
reload/cleanup, and all direct-`ACTION_SET_*` platforms (climate, water_heater,
number, light, button). Only the **channel cycle path** was defective.

## Final design (what the code now does)
- All channels are `select` entities. Filter = 4-state (Off/Auto/Medium/High);
  others = 3-state (Off/Auto/On).
- `_set_mode_locked`: fresh status read → `cycle_steps()` → send exactly that many
  cycle actions paced by `_INTER_STEP_SETTLE = 12.0s` → best-effort confirm via
  `_await_mode` (polls with `_VERIFY_DELAYS` using awaited `async_refresh()`),
  logging a WARNING (never raising, never overshooting) if status hasn't caught up.
- Per-entity `asyncio.Lock` + latest-request coalescing.
- Heater-pump channel select is created with `entity_registry_enabled_default=False`.

## Files changed / added (vs `25275b9`)
- `custom_components/connectmypool/cycle.py` — **new** (pure state machine).
- `custom_components/connectmypool/select.py` — **modified** (generic
  `ChannelModeSelect`, time-paced control, all channels as selects, heater pump
  disabled).
- `custom_components/connectmypool/switch.py` — **modified** (stub; creates no
  channel entities; retained so HA unloads old switches).
- `tests/test_cycle.py` — **new** (26 tests).
`diff --stat 25275b9 HEAD`: 4 files, +330 / −238.

## Commits (oldest → newest; the middle ones are the live-testing iteration)
```
bce7262  Add pure channel cycle state-machine helper with unit tests
445b749  Cycle channels one verified step at a time; model all channels as selects
db43081  Verify cycle steps with a real awaited refresh and backoff polling
42e1ca9  Trust wait_for_execution per step; make status verify best-effort
ad1c53d  Confirm each cycle step via status before sending the next (patient verify)
a20954e  Warn instead of erroring when a confirmed step times out
c213287  Pace cycle steps by time; fresh start read; best-effort reconcile
dbc4a06  Update ChannelModeSelect docstring to match time-paced behaviour
```
A squash-merge to `main` is recommended (keeps `main` clean; the iteration detail
is preserved on the branch).

## Tests added and results
- `tests/test_cycle.py`: filter & simple cycle step counts, no-op, wrap-around,
  max-step bound, full-sequence walk, `next_in_cycle`, unknown-mode errors.
- Result: `python -m pytest tests/ -q` → **26 passed**. All modules byte-compile.

## Live HA tests performed and results
Scope: Filter Pump, Spa Jets, Spa Blower only; one at a time; verified via state
and `get_history`; each restored to original. Heater Pump never enabled/actuated.
- **Filter Pump:** Auto → Medium → High (confirmed real cycle order) → restored to
  **Auto**. PASS.
- **Spa Jets:** Off → Auto → On → restored to **Off**. PASS (final design, no error).
- **Spa Blower:** Off → Auto → On → restored to **Off**. PASS (final design).
- The iteration also empirically established the two failure modes (false aborts
  from short verify windows; silent no-ops from firing cycles too fast) which the
  final time-paced design resolves.
- **Final resting states (restored):** Filter = Auto, Jets = Off, Blower = Off.

## Entity changes
- New/active: `select.connectmypool_filter_pump_mode` (Off/Auto/Medium Speed/High
  Speed), `select.connectmypool_jets_mode`, `select.connectmypool_blower_mode`
  (Off/Auto/On).
- Heater-pump channel select: **registered but disabled by default** (not in the
  active state machine; `get_entity` returns 404 while disabled — expected).
- Removed: channel switches. The old `switch.connectmypool_jets`,
  `switch.connectmypool_blower`, `switch.connectmypool_spa_pump` (Heater Pump) are
  now unavailable/orphaned in the registry — **safe to delete** (cannot be deleted
  via hass-mcp; do it in the HA UI).

## Dashboard / entity references
- **Needs changing:** the `custom:connectmypool-card` on the Seabreeze dashboard
  "Outside" view references removed switches:
  `switch.connectmypool_filter_pump` (never existed as a switch — filter was
  already a select), `switch.connectmypool_blower`, `switch.connectmypool_jets`.
  These should point at the new `select.*` entities — BUT first verify whether the
  custom card's `channels` option accepts `select` entities (it may expect
  switches). Not yet changed. (Dashboard: `/dashboard-seabreeze`, view path
  `outside`; editable via hass-mcp `get_dashboard_config` / `update_view`.)

## Heater Pump restrictions (carry forward)
- Channel 3, function 3. Select is disabled by default and must stay that way until
  the user explicitly asks to enable it. Do not actuate it. Physical heater is
  currently faulty — treat as read-only.

## Not yet completed / Outstanding
1. **Push the branch to GitHub.** `git push` from the dev machine hangs on the
   Windows Credential Manager (non-interactive); the updated token is for the
   GitHub API/MCP, not the git CLI. A full-history **git bundle** and patch are
   staged (paths below). Resume options: (a) user runs `git push` from their own
   terminal using the bundle; (b) push via GitHub API file-by-file with md5
   verification against local.
2. **Open a PR and squash-merge to `main`** after review.
3. **Fix the dashboard card** references (see above) — pending a decision on card
   compatibility with selects.
4. **Delete orphaned old switch entities** in the HA UI (optional cleanup).
5. **Optional:** remove the inert "expose channel switches" option from
   `config_flow.py`/`const.py` (harmless; separate small commit).
6. **Sync note:** the doc-only commit `dbc4a06` (docstring) is deployed to the live
   share but will only load on the next HA restart; runtime behaviour is identical
   to `c213287`, so no restart is required for it.

## Exact next recommended steps
1. Publish the branch (see Outstanding #1), e.g. from a terminal with GitHub creds:
   ```
   git clone https://github.com/Lazy-Ace/connectmypool-hacs.git cmp && cd cmp
   git fetch "C:\AI_Local_Test\connectmypool-deploy\connectmypool-fix.bundle" \
     fix/reliability-live-validation:fix/reliability-live-validation
   git push origin fix/reliability-live-validation
   ```
2. Open PR `fix/reliability-live-validation` → `main`; review; squash-merge.
3. Decide on and apply the dashboard card update.
4. Optionally delete orphaned switch entities and remove the inert option.

## Temporary / local paths (dev machine: Windows)
- Local clone with full branch history:
  `C:\Users\Admin\AppData\Local\Temp\claude\...\scratchpad\cmp` (session scratchpad
  — may be cleaned up between sessions; the bundle below is the durable copy).
- Staged deployment files + artifacts (durable):
  `C:\AI_Local_Test\connectmypool-deploy\`
  - `cycle.py`, `select.py`, `switch.py` — the deployable files
  - `connectmypool-fix.bundle` — git bundle of the full branch (tip `dbc4a06`)
  - `reliability-fix.patch` — full diff vs `25275b9`
- Live integration: `\\HOMEASSISTANT\config\custom_components\connectmypool\`
- Moved-aside backup (do NOT return it under custom_components):
  `\\HOMEASSISTANT\config\connectmypool_backup_1.0.6`
