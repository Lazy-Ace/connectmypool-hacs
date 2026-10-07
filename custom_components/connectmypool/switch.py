from __future__ import annotations

"""Switch platform for ConnectMyPool.

Channels are multi-state devices (Off/Auto/On, or Off/Auto/Medium/High for the
filter pump) driven by a single-step cycle action.  Representing them as on/off
switches hides the Auto state and cannot faithfully model the controller, so
every channel is now exposed as a mode ``select`` instead (see select.py).

No channel switch entities are created here.  The platform is retained so that
Home Assistant cleanly unloads any switch entities created by earlier versions;
those become unavailable and can be deleted from the entity registry.
"""


async def async_setup_entry(hass, entry, async_add_entities):
    # Channels are modelled as selects (Off/Auto/On, filter: Off/Auto/Medium/High).
    return
