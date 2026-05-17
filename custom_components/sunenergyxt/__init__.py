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


async def _write_md_and_mm(ip: str, md_string: str) -> None:
    """
    Write MD (meter connection) and activate MM (self-consumption mode)
    on the device so it uses our proxy as its smart meter.
    """
    payload = json.dumps({
        "state": {
            "LM": 1,   # local mode on
            "MD": md_string,
            "MM": 1,   # self-consumption mode on
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
                        "Failed to write MD/MM to device: HTTP %d", resp.status
                    )
                else:
                    _LOGGER.info(
                        "✅ Proxy MD written to device — device will now use "
                        "HA sensor as smart meter"
                    )
    except Exception as err:
        _LOGGER.error("Error writing MD/MM to device: %s", err)


async def _disable_mm(ip: str) -> None:
    """Disable self-consumption mode on the device."""
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
    2. Writes MD + MM to the device so it polls the proxy
    3. The device's internal PID handles the actual regulation

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

    # If grid sensor configured: set up proxy and write MD/MM to device
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
        md_string = _build_md_string(proxy_url)

        _LOGGER.info(
            "Grid sensor configured: %s — proxy URL: %s", grid_sensor, proxy_url
        )

        await _write_md_and_mm(ip, md_string)

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

    If a grid sensor was configured, disables MM on the device so it
    doesn't keep trying to reach a proxy that no longer exists.

    Args:
        hass: Home Assistant instance
        entry: Config entry to unload

    Returns:
        True if unload was successful

    """
    entry_data = hass.data.get(DOMAIN, {}).get(entry.entry_id, {})
    ip = entry_data.get("ip")
    grid_sensor = entry_data.get("grid_sensor")

    # Disable MM on device when unloading if we had set it up
    if ip and grid_sensor:
        await _disable_mm(ip)

    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)

    if unload_ok:
        hass.data[DOMAIN].pop(entry.entry_id, None)

    return unload_ok
