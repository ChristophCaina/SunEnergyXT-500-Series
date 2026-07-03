"""
Local HTTP proxy for SunEnergyXT 500 Series integration.

Exposes one or more HA sensors as a Shelly Pro 3EM-compatible JSON endpoint
so the SunEnergyXT device can use its internal PID controller against any
HA power sensor — without needing a physical Shelly or EcoTracker.

Multi-phase support: a single proxy endpoint (per config entry) can serve
per-phase power values (a_act_power / b_act_power / c_act_power) plus a
total (total_act_power), matching the real Shelly EM.GetStatus schema.
Each Kopfspeicher config entry then points its own MD at the field that
corresponds to the phase it is physically wired to, via CONF_METER_PHASE.

This module is intentionally free of config-entry lifecycle concerns
(setup/unload/remove) — those stay in __init__.py. It only knows how to:
  1. Serve the proxy HTTP view (SunEnergyXTProxyView)
  2. Build/compare the MD JSON string pointing at a given proxy field
  3. Write MD to the device (never MM — see __init__.py for that boundary)
"""

from __future__ import annotations

import json
import logging
from http import HTTPStatus
from typing import TYPE_CHECKING, Any

import aiohttp
import async_timeout
from homeassistant.components.http import HomeAssistantView

from .const import (
    CONF_GRID_SENSOR,
    CONF_METER_PHASE,
    CONF_PHASE_A_SENSOR,
    CONF_PHASE_B_SENSOR,
    CONF_PHASE_C_SENSOR,
    DOMAIN,
    METER_PHASE_FIELD_MAP,
    METER_PHASE_TOTAL,
)

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant

_LOGGER = logging.getLogger(__name__)

# Track registered proxy views to avoid duplicate registration
_PROXY_VIEWS_REGISTERED: set[str] = set()


def _sensor_value(hass: HomeAssistant, entity_id: str | None) -> float | None:
    """Return a sensor's numeric state in Watts, or None if unavailable."""
    if not entity_id:
        return None
    state = hass.states.get(entity_id)
    if state is None or state.state in ("unknown", "unavailable"):
        return None
    try:
        return float(state.state)
    except ValueError:
        return None


class SunEnergyXTProxyView(HomeAssistantView):
    """
    Local HTTP endpoint exposing HA sensors in Shelly Pro 3EM-compatible
    JSON format (EM.GetStatus schema, power fields only). The device polls
    this endpoint as if it were a real Shelly.

    Endpoint: GET /api/sunenergyxt_proxy/{entry_id}/status
    Response: {"a_act_power": .., "b_act_power": .., "c_act_power": ..,
               "total_act_power": ..}

    Sign convention (matches device expectation via MD/MM):
        Positive = export to grid (feed-in)
        Negative = import from grid (consumption)

    Backward compatibility: if only the legacy CONF_GRID_SENSOR is
    configured (no phase sensors), it is reported as total_act_power and
    a/b/c stay 0 — existing single-phase configs behave exactly as before.

    No authentication required — matches Shelly behaviour on local LAN.
    """

    requires_auth = False
    url = "/api/sunenergyxt_proxy/{entry_id}/status"
    name = "api:sunenergyxt_proxy:status"

    def __init__(self, hass: HomeAssistant) -> None:
        """Initialize the proxy view."""
        self.hass = hass

    async def get(self, request, entry_id: str):  # noqa: ARG002
        """Handle GET request — return sensor values in Shelly EM format."""
        from aiohttp.web import Response

        entry_data = self.hass.data.get(DOMAIN, {}).get(entry_id)
        if not entry_data:
            return Response(
                text=json.dumps({"error": "entry not found"}),
                status=404,
                content_type="application/json",
            )

        meter = entry_data.get("meter", {})
        grid_sensor = meter.get(CONF_GRID_SENSOR)
        a_sensor = meter.get(CONF_PHASE_A_SENSOR)
        b_sensor = meter.get(CONF_PHASE_B_SENSOR)
        c_sensor = meter.get(CONF_PHASE_C_SENSOR)

        if not any((grid_sensor, a_sensor, b_sensor, c_sensor)):
            return Response(
                text=json.dumps({"error": "no meter sensor configured"}),
                status=404,
                content_type="application/json",
            )

        a_val = _sensor_value(self.hass, a_sensor)
        b_val = _sensor_value(self.hass, b_sensor)
        c_val = _sensor_value(self.hass, c_sensor)
        total_val = _sensor_value(self.hass, grid_sensor)

        if total_val is None:
            # No explicit total sensor (or legacy grid_sensor not set) —
            # derive it from whichever phase sensors are actually available.
            phase_vals = [v for v in (a_val, b_val, c_val) if v is not None]
            total_val = sum(phase_vals) if phase_vals else 0.0

        payload = {
            "a_act_power": round(a_val, 1) if a_val is not None else 0.0,
            "b_act_power": round(b_val, 1) if b_val is not None else 0.0,
            "c_act_power": round(c_val, 1) if c_val is not None else 0.0,
            "total_act_power": round(total_val, 1),
        }

        return Response(
            text=json.dumps(payload),
            content_type="application/json",
        )


def build_proxy_url(internal_url: str, entry_id: str) -> str:
    """Build the local HA proxy URL for a given config entry."""
    return f"{internal_url.rstrip('/')}/api/sunenergyxt_proxy/{entry_id}/status"


def build_md_string(proxy_url: str, meter_phase: str = METER_PHASE_TOTAL) -> str:
    """
    Build the MD JSON string pointing the device at our local proxy.

    Args:
        proxy_url: URL of this entry's proxy endpoint (see build_proxy_url)
        meter_phase: which field this Kopfspeicher reads — "total"/"a"/"b"/"c"
            (see METER_PHASE_FIELD_MAP). Defaults to "total" so existing
            single-phase configs are unaffected.

    """
    field = METER_PHASE_FIELD_MAP.get(meter_phase, METER_PHASE_FIELD_MAP[METER_PHASE_TOTAL])
    md = {
        "mode": "direct",
        "direct": {
            "dat_url": proxy_url,
        },
        "dat_str": {
            "pwr": field,
        },
    }
    return json.dumps(md, separators=(",", ":"))


def md_points_to_proxy(current_md: str | None, proxy_url: str, meter_phase: str) -> bool:
    """
    Check whether the device's current MD already points at our proxy
    *and* reads the correct phase field.

    Both must match — otherwise changing meter_phase on reconfigure
    (e.g. from "a" to "b") would silently not take effect, since the
    dat_url alone wouldn't have changed.
    """
    if not current_md:
        return False
    try:
        parsed = json.loads(current_md)
    except (json.JSONDecodeError, TypeError):
        return False
    expected_field = METER_PHASE_FIELD_MAP.get(meter_phase, METER_PHASE_FIELD_MAP[METER_PHASE_TOTAL])
    url_matches = parsed.get("direct", {}).get("dat_url") == proxy_url
    field_matches = parsed.get("dat_str", {}).get("pwr") == expected_field
    return url_matches and field_matches


async def async_sync_md(ip: str, md_string: str) -> None:
    """
    Ensure the device's MD points at our proxy.

    Only writes MD — never touches MM. MM is exclusively owned by the
    user-facing switch entity, which already reflects/controls the live
    device state via the coordinator.

    This is idempotent by design: callers should check
    `md_points_to_proxy()` first and only call this when it's False, so
    we never write on every reload/update if nothing actually changed.
    """
    payload = json.dumps({
        "state": {
            "LM": 1,   # local mode on — required for the proxy endpoint to be used
            "MD": md_string,
        }
    })
    try:
        async with async_timeout.timeout(5), aiohttp.ClientSession() as session:
            async with session.post(
                f"http://{ip}/write",
                data=payload,
                headers={"Content-Type": "application/json"},
            ) as resp:
                if resp.status not in (200, 201, 204):
                    _LOGGER.warning(
                        "Failed to write MD to device: HTTP %d", resp.status
                    )
                else:
                    _LOGGER.info(
                        "✅ Proxy MD written to device (MM left untouched — "
                        "controlled via switch entity)"
                    )
    except Exception as err:
        _LOGGER.error("Error writing MD to device: %s", err)


async def async_disable_mm(ip: str) -> None:
    """
    Disable self-consumption mode and clear MD on the device.

    Only called when the config entry is actually being removed (see
    async_remove_entry in __init__.py), never on a plain reload/update,
    since the proxy URL becomes invalid once the entry is gone.
    """
    payload = json.dumps({"state": {"MM": 0, "MD": ""}})
    try:
        async with async_timeout.timeout(5), aiohttp.ClientSession() as session:
            async with session.post(
                f"http://{ip}/write",
                data=payload,
                headers={"Content-Type": "application/json"},
            ) as resp:
                if resp.status in (200, 201, 204):
                    _LOGGER.info("MM disabled on device")
    except Exception as err:
        _LOGGER.warning("Could not disable MM on device: %s", err)


def register_proxy_view(hass: HomeAssistant) -> None:
    """Register the proxy HTTP view (only once per HA instance)."""
    if DOMAIN not in _PROXY_VIEWS_REGISTERED:
        hass.http.register_view(SunEnergyXTProxyView(hass))
        _PROXY_VIEWS_REGISTERED.add(DOMAIN)
        _LOGGER.debug("SunEnergyXT proxy view registered")


def build_meter_config(entry_data: dict[str, Any]) -> dict[str, str | None]:
    """Extract the meter sensor mapping from a config entry's data dict."""
    return {
        CONF_GRID_SENSOR: entry_data.get(CONF_GRID_SENSOR),
        CONF_PHASE_A_SENSOR: entry_data.get(CONF_PHASE_A_SENSOR),
        CONF_PHASE_B_SENSOR: entry_data.get(CONF_PHASE_B_SENSOR),
        CONF_PHASE_C_SENSOR: entry_data.get(CONF_PHASE_C_SENSOR),
    }


def has_any_meter_sensor(meter_config: dict[str, str | None]) -> bool:
    """Whether at least one meter sensor is configured for this entry."""
    return any(meter_config.values())
