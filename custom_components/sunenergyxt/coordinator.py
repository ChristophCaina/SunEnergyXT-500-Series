"""
Data update coordinator for SunEnergyXT 500 Series integration.

This module implements the data update coordinator for the SunEnergyXT integration,
responsible for fetching and updating data from the device at regular intervals.

When a grid power sensor entity is configured, the integration registers a local
HTTP proxy endpoint (Shelly-compatible) and sets MD/MM on the device so it uses
its internal PID controller — no manual GS writes needed.

Classes:
- SunlitDataUpdateCoordinator: Handles data updates from SunEnergyXT devices
"""

import asyncio
import logging
from datetime import UTC, datetime, timedelta
from http import HTTPStatus
from typing import Any

import aiohttp
import async_timeout
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

_LOGGER = logging.getLogger(__name__)


class SunlitDataUpdateCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """
    Data update coordinator for SunEnergyXT devices.

    Handles fetching and updating data from the device at regular intervals.
    When a grid sensor is configured, the device uses its internal PID via
    the local HTTP proxy — this coordinator only handles polling /read.
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
                When set, the integration uses MD/MM (internal device PID) instead
                of writing GS directly.

        """
        self._sn = sn
        self._ip = ip
        self._grid_sensor_entity_id = grid_sensor_entity_id
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

        When a grid sensor is configured, the actual regulation is handled
        by the device's internal PID via the local HTTP proxy (MD/MM).
        No additional listeners needed here.
        """
        if self._grid_sensor_entity_id:
            _LOGGER.debug(
                "Grid sensor configured: %s — device uses internal PID via proxy",
                self._grid_sensor_entity_id,
            )

    async def _async_update_data(self) -> dict[str, Any]:
        """
        Fetch data from the SunEnergyXT device.

        Returns:
            Dictionary containing the reported device data

        Raises:
            UpdateFailed: If there's a transient communication error (timeout,
                connection refused, HTTP error). HA will retry on the next
                polling interval and mark entities unavailable without
                writing a full stack trace to the log.

        """
        try:
            async with async_timeout.timeout(10):
                async with self._session.get(f"http://{self._ip}/read") as resp:
                    if resp.status != HTTPStatus.OK:
                        raise UpdateFailed(f"HTTP {resp.status} from device")

                    data = await resp.json()
                    reported = data.get("state", {}).get("reported", {})

                    if not isinstance(reported, dict):
                        raise UpdateFailed("Invalid 'reported' structure in JSON response")

                    self.last_success_time = datetime.now(UTC)
                    _LOGGER.debug("Get raw data: %s", str(data))
                    return reported

        except asyncio.TimeoutError as err:
            raise UpdateFailed(
                f"Timeout communicating with device at {self._ip} "
                f"(firmware bug on ES=1.1.12/EH=1.0.1 can cause this — "
                f"see https://github.com/ChristophCaina/SunEnergyXT-500-Series/discussions)"
            ) from err

        except aiohttp.ClientConnectionError as err:
            raise UpdateFailed(
                f"Cannot reach device at {self._ip}: {err}"
            ) from err

        except aiohttp.ClientError as err:
            raise UpdateFailed(
                f"Communication error with device at {self._ip}: {err}"
            ) from err

        except UpdateFailed:
            raise

        except Exception as err:
            _LOGGER.exception("Unexpected error updating SunEnergyXT Monitor data")
            raise UpdateFailed(f"Unexpected error: {err}") from err
