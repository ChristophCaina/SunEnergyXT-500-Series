"""
Data update coordinator for SunEnergyXT 500 Series integration.

This module implements the data update coordinator for the SunEnergyXT integration,
responsible for fetching and updating data from the device at regular intervals.

When a grid power sensor entity is configured, the coordinator also listens for
state changes and automatically writes the GS (grid power setpoint) field to the
device — no manual rest_command needed.

GS sign convention (matches device API):
  Positive = feed-in / export to grid
  Negative = grid import / charge from grid

Classes:
- SunlitDataUpdateCoordinator: Handles data updates from SunEnergyXT devices
"""

import json
import logging
from datetime import UTC, datetime, timedelta
from http import HTTPStatus
from typing import Any

import async_timeout
from homeassistant.core import Event, HomeAssistant, State, callback
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.event import async_track_state_change_event
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

from .const import CONF_GRID_SENSOR

_LOGGER = logging.getLogger(__name__)

# Minimum change in watts before a new GS write is triggered.
# Avoids hammering the device with tiny fluctuations.
GS_DEADBAND_W = 10

# Round GS writes to this step size (device accepts multiples of 10 W).
GS_STEP_W = 10


class SunlitDataUpdateCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """
    Data update coordinator for SunEnergyXT devices.

    Handles fetching and updating data from the device at regular intervals.
    Optionally listens to a HA grid power sensor and writes GS automatically.
    """

    def __init__(
        self,
        hass: HomeAssistant,
        sn: str,
        ip: str,
        grid_sensor_entity_id: str | None = None,
    ) -> None:
        """
        Initialize the data update coordinator.

        Args:
            hass: Home Assistant instance
            sn: Device serial number
            ip: Device IP address
            grid_sensor_entity_id: Optional HA entity ID of the grid power sensor.
                When set, GS is written automatically on state changes.
                Positive = export, negative = import (same as device convention).

        """
        self._sn = sn
        self._ip = ip
        self._grid_sensor_entity_id = grid_sensor_entity_id
        self._last_gs_written: int | None = None
        self._session = async_get_clientsession(hass)
        super().__init__(
            hass,
            _LOGGER,
            name=f"SunlitMonitor-{sn}",
            update_interval=timedelta(seconds=3),
        )

    async def async_setup(self) -> None:
        """
        Set up the coordinator.

        Registers the grid sensor state change listener if configured.
        """
        if self._grid_sensor_entity_id:
            _LOGGER.debug(
                "Grid sensor configured: %s — automatic GS control enabled",
                self._grid_sensor_entity_id,
            )
            async_track_state_change_event(
                self.hass,
                [self._grid_sensor_entity_id],
                self._handle_grid_sensor_state_change,
            )

    @callback
    def _handle_grid_sensor_state_change(self, event: Event) -> None:
        """
        Handle state changes of the configured grid power sensor.

        Called whenever the grid sensor entity changes state.
        Schedules an async GS write without blocking the event loop.

        Args:
            event: State change event from Home Assistant

        """
        new_state: State | None = event.data.get("new_state")
        if new_state is None or new_state.state in ("unknown", "unavailable"):
            _LOGGER.debug("Grid sensor state unavailable, skipping GS write")
            return

        try:
            raw_value = float(new_state.state)
        except ValueError:
            _LOGGER.warning(
                "Grid sensor %s returned non-numeric state: %s",
                self._grid_sensor_entity_id,
                new_state.state,
            )
            return

        # Round to nearest GS_STEP_W (device accepts multiples of 10 W)
        gs_value = int(round(raw_value / GS_STEP_W) * GS_STEP_W)

        # Skip write if value hasn't changed meaningfully
        if (
            self._last_gs_written is not None
            and abs(gs_value - self._last_gs_written) < GS_DEADBAND_W
        ):
            _LOGGER.debug(
                "GS value %dW within deadband of last write %dW, skipping",
                gs_value,
                self._last_gs_written,
            )
            return

        _LOGGER.debug(
            "Grid sensor changed to %.1fW → writing GS=%dW to device",
            raw_value,
            gs_value,
        )

        self.hass.async_create_task(self._async_write_gs(gs_value))

    async def _async_write_gs(self, gs_value: int) -> None:
        """
        Write the GS (grid power setpoint) field to the device.

        Args:
            gs_value: Target grid power in watts.
                Positive = export to grid, negative = import from grid.

        """
        url = f"http://{self._ip}/write"
        payload = json.dumps({"state": {"GS": gs_value}})

        try:
            async with async_timeout.timeout(5):
                async with self._session.post(
                    url,
                    data=payload,
                    headers={"Content-Type": "application/json"},
                ) as resp:
                    if resp.status not in (200, 201, 204):
                        _LOGGER.warning(
                            "GS write returned unexpected HTTP %d", resp.status
                        )
                        return

            self._last_gs_written = gs_value
            _LOGGER.debug("GS successfully written: %dW", gs_value)

        except Exception as err:  # noqa: BLE001
            _LOGGER.error("Failed to write GS to device: %s", err)

    async def _async_update_data(self) -> dict[str, Any]:
        """
        Fetch data from the SunEnergyXT device.

        Returns:
            Dictionary containing the reported device data

        Raises:
            RuntimeError: If there's an error fetching or processing the data

        """
        try:
            async with async_timeout.timeout(10):
                async with self._session.get(f"http://{self._ip}/read") as resp:
                    if resp.status != HTTPStatus.OK:
                        msg = f"HTTP status {resp.status}"
                        raise RuntimeError(msg)

                    data = await resp.json()

                    reported = data.get("state", {}).get("reported", {})

                    if not isinstance(reported, dict):
                        msg = "Invalid 'reported' structure in JSON"
                        raise TypeError(msg)

                    self.last_success_time = datetime.now(UTC)
                    _LOGGER.debug("Get raw data: %s", str(data))
                    return reported
        except Exception as err:
            _LOGGER.exception("Error updating SunEnergyXT Monitor data: %s", err)
            raise
