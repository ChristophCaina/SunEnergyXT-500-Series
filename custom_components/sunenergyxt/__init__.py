"""
SunEnergyXT 500 Series integration for Home Assistant.

This module handles the setup and configuration of the SunEnergyXT integration,
including device connection testing, coordinator initialization, platform setup,
and the local HTTP proxy that allows the device to use any HA sensor as a
smart meter — without needing a physical Shelly or EcoTracker.

Modules:
- const: Contains constant definitions for the integration
- coordinator: Handles data updates from the SunEnergyXT device
- sensor: Implements sensor entities
- number: Implements number entities
- button: Implements button entities
- switch: Implements switch entities
- text: Implements text entities
"""

from __future__ import annotations

import json
import logging
from http import HTTPStatus
from typing import TYPE_CHECKING

import aiohttp
import async_timeout
from homeassistant.components.http import HomeAssistantView
from homeassistant.const import Platform
from homeassistant.exceptions import ConfigEntryNotReady
from homeassistant.helpers import config_validation as cv

from .const import CONF_GRID_SENSOR, DOMAIN
from .coordinator import SunlitDataUpdateCoordinator

if TYPE_CHECKING:
    from homeassistant.config_entries import ConfigEntry
    from homeassistant.core import HomeAssistant

_LOGGER = logging.getLogger(__name__)
PLATFORMS: list[Platform] = [
    Platform.SENSOR,
    Platform.NUMBER,
    Platform.BUTTON,
    Platform.SWITCH,
    Platform.TEXT,
]
CONFIG_SCHEMA = cv.empty_config_schema(domain=DOMAIN)

# Track registered proxy views to avoid duplicate registration
_PROXY_VIEWS_REGISTERED: set[str] = set()


# ---------------------------------------------------------------------------
# Local HTTP proxy — makes HA look like a Shelly to the device
# ---------------------------------------------------------------------------
class SunEnergyXTProxyView(HomeAssistantView):
    """
    Local HTTP endpoint that exposes a HA sensor value in Shelly-compatible
    JSON format. The device polls this endpoint as if it were a Shelly Pro 3EM,
    enabling it to use its internal PID controller with any HA power sensor.

    Endpoint: GET /api/sunenergyxt_proxy/{entry_id}/status
    Response:  {"total_power": <value_in_watts>}

    Sign convention (matches device expectation via MD/MM):
        Positive = export to grid (feed-in)
        Negative = import from grid (consumption)

    No authentication required — matches Shelly behaviour on local LAN.
    """

    requires_auth = False
    url = "/api/sunenergyxt_proxy/{entry_id}/status"
    name = "api:sunenergyxt_proxy:status"

    def __init__(self, hass: HomeAssistant) -> None:
        """Initialize the proxy view."""
        self.hass = hass

    async def get(self, request, entry_id: str):
        """Handle GET request — return sensor value in Shelly format."""
        from aiohttp.web import Response

        # Find the entry
        entry_data = self.hass.data.get(DOMAIN, {}).get(entry_id)
        if not entry_data:
            return Response(
                text=json.dumps({"error": "entry not found"}),
                status=404,
                content_type="application/json",
            )

        grid_sensor = entry_data.get("grid_sensor")
        if not grid_sensor:
            return Response(
                text=json.dumps({"error": "no grid sensor configured"}),
                status=404,
                content_type="application/json",
            )

        # Get current sensor state
        state = self.hass.states.get(grid_sensor)
        if state is None or state.state in ("unknown", "unavailable"):
            return Response(
                text=json.dumps({"total_power": 0}),
                content_type="application/json",
            )

        try:
            value = float(state.state)
        except ValueError:
            value = 0.0

        return Response(
            text=json.dumps({"total_power": round(value, 1)}),
            content_type="application/json",
        )


# ---------------------------------------------------------------------------
# Helper: build MD string and write it to the device
# ---------------------------------------------------------------------------
def _build_md_string(proxy_url: str) -> str:
    """Build the MD JSON string pointing to our local proxy."""
    md = {
        "mode": "direct",
        "direct": {
            "dat_url": proxy_url,
        },
        "dat_str": {
            "pwr": "total_power",
        },
    }
    return json.dumps(md, separators=(",", ":"))


async def _read_device_state(ip: str) -> dict[str, Any]:
    """
    Read the current MM/MD state directly from the device.

    This is the single source of truth for whether the local proxy /
    zero-feed mode is currently active — never inferred from stored
    HA config data.

    Args:
        ip: IP address of the device

    Returns:
        Dict with "MM" (int | None) and "MD" (str | None) as currently
        reported by the device. Empty values on read failure.

    """
    try:
        async with async_timeout.timeout(5), aiohttp.ClientSession() as session:
            async with session.get(f"http://{ip}/read") as resp:
                if resp.status != HTTPStatus.OK:
                    _LOGGER.warning(
                        "Could not read device state: HTTP %d", resp.status
                    )
                    return {"MM": None, "MD": None}
                data = await resp.json()
                reported = data.get("state", {}).get("reported", {})
                return {"MM": reported.get("MM"), "MD": reported.get("MD")}
    except Exception as err:
        _LOGGER.warning("Error reading device state from %s: %s", ip, err)
        return {"MM": None, "MD": None}


def _md_points_to_proxy(current_md: str | None, proxy_url: str) -> bool:
    """Check whether the device's current MD already points at our proxy."""
    if not current_md:
        return False
    try:
        parsed = json.loads(current_md)
    except (json.JSONDecodeError, TypeError):
        return False
    return parsed.get("direct", {}).get("dat_url") == proxy_url


async def _sync_md(ip: str, md_string: str) -> None:
    """
    Ensure the device's MD points at our proxy.

    Only writes MD — never touches MM. MM is exclusively owned by the
    user-facing switch entity, which already reflects/controls the live
    device state via the coordinator.

    This is idempotent by design: callers should check
    `_md_points_to_proxy()` first and only call this when it's False,
    so we never write on every reload/update if nothing actually changed.
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


async def _disable_mm(ip: str) -> None:
    """
    Disable self-consumption mode and clear MD on the device.

    Only called when the config entry is actually being removed (see
    async_remove_entry), never on a plain reload/update, since the
    proxy URL becomes invalid once the entry is gone.
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


# ---------------------------------------------------------------------------
# Connection test
# ---------------------------------------------------------------------------
async def _test_connection(ip: str) -> None:
    """
    Test connection to the SunEnergyXT device.

    Args:
        ip: IP address of the device

    Raises:
        RuntimeError: If connection fails or device returns an error

    """
    try:
        async with async_timeout.timeout(5), aiohttp.ClientSession() as session:
            async with session.get(f"http://{ip}/read") as resp:
                if resp.status != HTTPStatus.OK:
                    msg = f"HTTP status {resp.status}"
                    raise RuntimeError(msg)
                await resp.json()
    except Exception as err:
        msg = f"Cannot connect to device at {ip}: {err}"
        raise RuntimeError(msg) from err


# ---------------------------------------------------------------------------
# Setup / unload
# ---------------------------------------------------------------------------
async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """
    Set up SunEnergyXT from a config entry.

    If a grid sensor is configured:
    1. Registers a local HTTP proxy endpoint (Shelly-compatible)
    2. Ensures MD on the device points at our proxy (idempotent — only
       writes if it's not already correct; never writes on every reload)
    3. The device's internal PID handles the actual regulation once the
       user activates it via the "MM" switch entity

    Note: MM (self-consumption / zero-feed mode) is intentionally never
    written here. It is fully owned by the "MM" switch entity, which
    reflects the live device state via the coordinator. Updating or
    reloading the integration must never silently flip the device's
    operating mode — only an explicit user action on the switch does
    that. (See GitHub issue #12.)

    Args:
        hass: Home Assistant instance
        entry: Config entry containing device information

    Returns:
        True if setup was successful

    Raises:
        ConfigEntryNotReady: If the device is not ready

    """
    hass.data.setdefault(DOMAIN, {})
    sn = entry.data.get("sn")
    ip = entry.data.get("ip")
    model = entry.data.get("model")
    grid_sensor = entry.data.get(CONF_GRID_SENSOR)

    try:
        await _test_connection(ip)
    except Exception as err:
        _LOGGER.warning("Device %s (%s) not ready: %s", sn, ip, err)
        msg = f"Device not ready: {err}"
        raise ConfigEntryNotReady(msg) from err

    # Register the proxy HTTP view (only once per HA instance)
    if DOMAIN not in _PROXY_VIEWS_REGISTERED:
        hass.http.register_view(SunEnergyXTProxyView(hass))
        _PROXY_VIEWS_REGISTERED.add(DOMAIN)
        _LOGGER.debug("SunEnergyXT proxy view registered")

    # Store entry data (proxy view reads grid_sensor from here)
    hass.data[DOMAIN][entry.entry_id] = {
        "sn": sn,
        "ip": ip,
        "model": model,
        "grid_sensor": grid_sensor,
    }

    # If grid sensor configured: ensure the proxy MD is set up.
    # Read-first, write-only-on-mismatch — MM is never touched here.
    if grid_sensor:
        try:
            # Get HA's internal URL (how the device reaches HA on the LAN)
            internal_url = hass.config.internal_url
            if not internal_url:
                # Fallback: try to build from network config
                internal_url = f"http://{hass.config.api.local_ip}:8123"
        except Exception:
            internal_url = "http://homeassistant.local:8123"

        proxy_url = f"{internal_url.rstrip('/')}/api/sunenergyxt_proxy/{entry.entry_id}/status"

        device_state = await _read_device_state(ip)

        if _md_points_to_proxy(device_state.get("MD"), proxy_url):
            _LOGGER.debug(
                "Device MD already points at our proxy (%s) — skipping write",
                proxy_url,
            )
        else:
            _LOGGER.info(
                "Grid sensor configured: %s — pointing device MD at proxy URL: %s",
                grid_sensor,
                proxy_url,
            )
            md_string = _build_md_string(proxy_url)
            await _sync_md(ip, md_string)

    coordinator = SunlitDataUpdateCoordinator(
        hass=hass,
        sn=sn,
        ip=ip,
        grid_sensor_entity_id=grid_sensor,
    )
    await coordinator.async_setup()
    await coordinator.async_config_entry_first_refresh()

    # Update stored data with coordinator
    hass.data[DOMAIN][entry.entry_id]["coordinator"] = coordinator

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """
    Unload a SunEnergyXT config entry.

    This runs on every reload — including HA restarts and integration
    updates — not just on removal. It must therefore be a pure platform
    unload and must NOT touch the device's MM/MD state, otherwise every
    update/restart would silently flip the device's operating mode.
    (See GitHub issue #12.) Device-side cleanup only happens in
    async_remove_entry, which runs solely on actual removal.

    Args:
        hass: Home Assistant instance
        entry: Config entry to unload

    Returns:
        True if unload was successful

    """
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)

    if unload_ok:
        hass.data[DOMAIN].pop(entry.entry_id, None)

    return unload_ok


async def async_remove_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """
    Handle full removal of a SunEnergyXT config entry.

    Unlike async_unload_entry (called on every reload, including updates
    and HA restarts), this only runs when the user actually deletes the
    integration. This is the correct — and only — place to disable MM
    and clear MD on the device, since the proxy endpoint genuinely stops
    existing once the entry is gone.

    Args:
        hass: Home Assistant instance
        entry: Config entry being removed

    """
    entry_data = hass.data.get(DOMAIN, {}).get(entry.entry_id, {})
    ip = entry_data.get("ip") or entry.data.get("ip")
    grid_sensor = entry_data.get("grid_sensor") or entry.data.get(CONF_GRID_SENSOR)

    if ip and grid_sensor:
        await _disable_mm(ip)
