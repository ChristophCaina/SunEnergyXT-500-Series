"""Device triggers for SunEnergyXT 500 Series integration.

Why this file exists
---------------------
Home Assistant's Automation UI only lists a device under "Add Trigger ->
By Target -> Devices" if the integration implements the
`device_automation` platform for triggers (``async_get_triggers`` /
``async_get_trigger_capabilities`` / ``async_attach_trigger``). None of
the previous versions of this integration (neither the fork nor
upstream) implemented it, so the SunEnergyXT device always fell into
"Unassigned devices -> No triggers available".

This module adds that platform. It is intentionally thin: it never
talks to the device directly and never touches MM/MD. It only resolves,
for a given HA device_id, which entity_id backs a given trigger type,
and then delegates to Home Assistant's own built-in `state` and
`numeric_state` trigger platforms. That keeps it fully decoupled from
the MM/MD ownership logic in __init__.py / switch.py -- adding this
file changes nothing about read/write behavior toward the device.

Triggers offered (only shown if the matching entity actually exists on
that device/config entry, so this also works unchanged for multiple
Kopfspeicher / config entries):

- "mm_turned_on"     - the MM (Zero-Feed-in) switch turned on
- "mm_turned_off"    - the MM (Zero-Feed-in) switch turned off
- "restart_pressed"  - the RT restart button was pressed
- "status_changed"   - the ST status sensor changed value
- "soc_above"        - the SC (total SOC) sensor rose above a threshold
- "soc_below"        - the SC (total SOC) sensor fell below a threshold

Entity resolution relies on this integration's existing unique_id
convention, used consistently across switch.py / button.py / text.py /
sensor.py / number.py:

    f"{DOMAIN}_{entry_id}_{key}"

e.g. "sunenergyxt_01JABC..._MM" for the MM switch. If that convention
ever changes, `_KEY_TO_UNIQUE_ID_SUFFIX` below is the only place that
needs updating.
"""

from __future__ import annotations

from typing import Any

import voluptuous as vol

from homeassistant.components.device_automation import DEVICE_TRIGGER_BASE_SCHEMA
from homeassistant.components.homeassistant.triggers import (
    numeric_state as numeric_state_trigger,
    state as state_trigger,
)
from homeassistant.const import CONF_DEVICE_ID, CONF_DOMAIN, CONF_ENTITY_ID, CONF_PLATFORM, CONF_TYPE
from homeassistant.core import CALLBACK_TYPE, HomeAssistant
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.trigger import TriggerActionType, TriggerInfo

from .const import DOMAIN

# trigger_type -> device API key whose entity backs this trigger.
_TRIGGER_KEY: dict[str, str] = {
    "mm_turned_on": "MM",
    "mm_turned_off": "MM",
    "restart_pressed": "RT",
    "status_changed": "ST",
    "soc_above": "SC",
    "soc_below": "SC",
}

TRIGGER_TYPES = set(_TRIGGER_KEY)

TRIGGER_SCHEMA = DEVICE_TRIGGER_BASE_SCHEMA.extend(
    {
        vol.Required(CONF_TYPE): vol.In(TRIGGER_TYPES),
    }
)


def _find_entity_id(hass: HomeAssistant, device_id: str, key: str) -> str | None:
    """Find the entity_id on this device whose unique_id ends in '_<key>'.

    Matches this integration's unique_id convention
    f"{DOMAIN}_{entry_id}_{key}" -- comparing the last underscore-
    separated segment avoids false positives from an entry_id that
    happens to end in the same letters as a key.
    """
    entity_registry = er.async_get(hass)
    for entry in er.async_entries_for_device(entity_registry, device_id):
        if entry.platform != DOMAIN:
            continue
        if entry.unique_id.rsplit("_", 1)[-1] == key:
            return entry.entity_id
    return None


async def async_get_triggers(hass: HomeAssistant, device_id: str) -> list[dict[str, Any]]:
    """Return the triggers this integration offers for a given device.

    Only triggers whose backing entity actually exists on this device
    are returned, so this naturally adapts if a future firmware/entity
    set differs between devices (e.g. a key that isn't exposed on some
    Kopfspeicher).
    """
    triggers: list[dict[str, Any]] = []

    for trigger_type, key in _TRIGGER_KEY.items():
        if _find_entity_id(hass, device_id, key) is None:
            continue
        triggers.append(
            {
                CONF_PLATFORM: "device",
                CONF_DEVICE_ID: device_id,
                CONF_DOMAIN: DOMAIN,
                CONF_TYPE: trigger_type,
            }
        )

    return triggers


async def async_get_trigger_capabilities(
    hass: HomeAssistant,  # noqa: ARG001
    config: dict[str, Any],
) -> dict[str, Any]:
    """Return extra UI fields for a trigger (the SOC threshold value)."""
    trigger_type = config[CONF_TYPE]

    if trigger_type == "soc_above":
        return {"extra_fields": vol.Schema({vol.Required("above"): vol.Coerce(float)})}
    if trigger_type == "soc_below":
        return {"extra_fields": vol.Schema({vol.Required("below"): vol.Coerce(float)})}

    return {}


async def async_attach_trigger(
    hass: HomeAssistant,
    config: dict[str, Any],
    action: TriggerActionType,
    trigger_info: TriggerInfo,
) -> CALLBACK_TYPE:
    """Attach a device trigger by delegating to state/numeric_state."""
    trigger_type = config[CONF_TYPE]
    device_id = config[CONF_DEVICE_ID]
    key = _TRIGGER_KEY[trigger_type]

    entity_id = _find_entity_id(hass, device_id, key)
    if entity_id is None:
        msg = f"Entity for SunEnergyXT trigger '{trigger_type}' not found on device {device_id}"
        raise ValueError(msg)

    if trigger_type in ("soc_above", "soc_below"):
        numeric_config: dict[str, Any] = {
            CONF_PLATFORM: "numeric_state",
            CONF_ENTITY_ID: [entity_id],
        }
        if trigger_type == "soc_above":
            numeric_config["above"] = config["above"]
        else:
            numeric_config["below"] = config["below"]

        numeric_config = await numeric_state_trigger.async_validate_trigger_config(hass, numeric_config)
        return await numeric_state_trigger.async_attach_trigger(hass, numeric_config, action, trigger_info)

    # mm_turned_on / mm_turned_off / restart_pressed / status_changed all
    # reduce to a plain state trigger; mm_turned_on/off pin the target
    # state, restart_pressed/status_changed fire on any state change.
    state_config: dict[str, Any] = {
        CONF_PLATFORM: "state",
        CONF_ENTITY_ID: [entity_id],
    }
    if trigger_type == "mm_turned_on":
        state_config["to"] = "on"
    elif trigger_type == "mm_turned_off":
        state_config["to"] = "off"

    state_config = await state_trigger.async_validate_trigger_config(hass, state_config)
    return await state_trigger.async_attach_trigger(hass, state_config, action, trigger_info)
