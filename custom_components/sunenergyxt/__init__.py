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

import logging
from http import HTTPStatus
from typing import TYPE_CHECKING, Any

import aiohttp
import async_timeout
from homeassistant.const import Platform
from homeassistant.exceptions import ConfigEntryNotReady
from homeassistant.helpers import config_validation as cv

from .const import CONF_GRID_SENSOR, CONF_METER_PHASE, DOMAIN, METER_PHASE_TOTAL
from .coordinator import SunlitDataUpdateCoordinator
from .proxy import (
    async_disable_mm,
    async_sync_md,
    build_md_string,
    build_meter_config,
    build_proxy_url,
    has_any_meter_sensor,
    md_points_to_proxy,
    register_proxy_view,
)

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
    meter_config = build_meter_config(entry.data)
    meter_phase = entry.data.get(CONF_METER_PHASE, METER_PHASE_TOTAL)
    # Legacy config entries (pre-multi-phase) only ever set CONF_GRID_SENSOR
    # and never had a meter_phase concept — CONF_GRID_SENSOR is still what
    # coordinator/sensor code expects as "the" grid sensor for now.
    grid_sensor = meter_config.get(CONF_GRID_SENSOR)

    try:
        await _test_connection(ip)
    except Exception as err:
        _LOGGER.warning("Device %s (%s) not ready: %s", sn, ip, err)
        msg = f"Device not ready: {err}"
        raise ConfigEntryNotReady(msg) from err

    # Register the proxy HTTP view (only once per HA instance)
    register_proxy_view(hass)

    # Store entry data (proxy view reads `meter` from here)
    hass.data[DOMAIN][entry.entry_id] = {
        "sn": sn,
        "ip": ip,
        "model": model,
        "grid_sensor": grid_sensor,
        "meter": meter_config,
        "meter_phase": meter_phase,
    }

    # If at least one meter sensor is configured: ensure the proxy MD is
    # set up. Read-first, write-only-on-mismatch — MM is never touched here.
    if has_any_meter_sensor(meter_config):
        try:
            # Get HA's internal URL (how the device reaches HA on the LAN)
            internal_url = hass.config.internal_url
            if not internal_url:
                # Fallback: try to build from network config
                internal_url = f"http://{hass.config.api.local_ip}:8123"
        except Exception:
            internal_url = "http://homeassistant.local:8123"

        proxy_url = build_proxy_url(internal_url, entry.entry_id)

        device_state = await _read_device_state(ip)

        if md_points_to_proxy(device_state.get("MD"), proxy_url, meter_phase):
            _LOGGER.debug(
                "Device MD already points at our proxy (%s, phase=%s) — skipping write",
                proxy_url,
                meter_phase,
            )
        else:
            _LOGGER.info(
                "Meter configured (phase=%s) — pointing device MD at proxy URL: %s",
                meter_phase,
                proxy_url,
            )
            md_string = build_md_string(proxy_url, meter_phase)
            await async_sync_md(ip, md_string)

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
    meter_config = entry_data.get("meter") or build_meter_config(entry.data)

    if ip and has_any_meter_sensor(meter_config):
        await async_disable_mm(ip)
