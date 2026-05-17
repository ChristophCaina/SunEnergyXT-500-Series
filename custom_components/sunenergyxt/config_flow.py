"""
Configuration flow for SunEnergyXT 500 Series integration.

This module handles the configuration process for the SunEnergyXT integration,
including user input validation, device discovery via Zeroconf, device
information retrieval, and reconfiguration support.

Classes:
- SunlitConfigFlow: Main configuration flow handler for the integration
- InvalidIP: Exception raised for invalid IP addresses
- CannotConnect: Exception raised when unable to connect to the device
- CannotGetSN: Exception raised when unable to retrieve device serial number
- CannotGetModel: Exception raised when unable to retrieve device model

Functions:
- _validate_input: Validates the provided IP address
- _get_device_info: Retrieves device information from the given host
"""

import ipaddress
import logging
from http import HTTPStatus
from typing import Any

import aiohttp
import async_timeout
import voluptuous as vol
from homeassistant import config_entries, exceptions
from homeassistant.components.sensor import DOMAIN as SENSOR_DOMAIN
from homeassistant.data_entry_flow import AbortFlow, FlowResult
from homeassistant.helpers import selector
from homeassistant.helpers.service_info.zeroconf import ZeroconfServiceInfo

from .const import CONF_GRID_SENSOR, DOMAIN, HOST_PREFIX, HOST_SUFFIX

_LOGGER = logging.getLogger(__name__)


async def _validate_input(ip: str) -> None:
    """
    Validate the provided IP address.

    Args:
        ip: IP address to validate

    Raises:
        InvalidIP: If the IP address is invalid

    """
    try:
        ipaddress.ip_address(ip)
    except ValueError as err:
        raise InvalidIP from err


async def _get_device_info(host: str) -> dict[str, Any]:
    """
    Retrieve device information from the given host.

    Args:
        host: Hostname or IP address of the device

    Returns:
        Dictionary containing device serial number and model

    Raises:
        CannotConnect: If unable to connect to the device
        CannotGetSN: If unable to retrieve device serial number
        CannotGetModel: If unable to retrieve device model

    """
    try:
        async with async_timeout.timeout(5), aiohttp.ClientSession() as session:
            async with session.get(f"http://{host}/read") as resp:
                if resp.status != HTTPStatus.OK:
                    raise CannotConnect
                data = await resp.json()
                sn = data.get("state", {}).get("reported", {}).get("SN")
                model = data.get("state", {}).get("reported", {}).get("DevType")
                if not isinstance(sn, str):
                    raise CannotGetSN
                if not isinstance(model, str):
                    raise CannotGetModel
                return {"sn": sn, "model": model}
    except Exception:  # noqa: BLE001
        raise CannotConnect from None


class SunlitConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """
    Configuration flow handler for SunEnergyXT integration.

    This class handles the configuration process for the SunEnergyXT integration,
    including:
    - User input validation for IP addresses
    - Device discovery via Zeroconf
    - Device information retrieval
    - Optional HA entity as grid power sensor (local HTTP proxy → MM/MD)
    - Configuration entry creation
    - Reconfiguration of grid sensor without reinstalling
    - Error handling for various failure scenarios
    """

    VERSION = 1
    MINOR_VERSION = 1

    def __init__(self) -> None:
        """
        Initialize the configuration flow.

        Sets up instance variables for discovered device information.
        """
        self._discovered_sn: str | None = None
        self._discovered_ip: str | None = None
        self._discovered_model: str | None = None
        self._ip: str | None = None
        self._sn: str | None = None
        self._model: str | None = None

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """
        Handle user input for SunEnergyXT configuration.

        Args:
            user_input: Dictionary containing user input

        Returns:
            FlowResult indicating the next step in the configuration flow

        """
        errors: dict[str, str] = {}

        if user_input is not None:
            try:
                ip = user_input["IP"]
                _LOGGER.debug("user input ip: %s", ip)
                await _validate_input(ip)
                info = await _get_device_info(ip)
                sn = info["sn"]
                model = info["model"]
                _LOGGER.debug("get sn: %s, model: %s", sn, model)

                await self.async_set_unique_id(sn)
                self._abort_if_unique_id_configured(updates={"ip": ip})

                self._ip = ip
                self._sn = sn
                self._model = model

            except InvalidIP:
                errors["base"] = "invalid_ip"

            except CannotConnect:
                errors["base"] = "cannot_connect"

            except CannotGetSN:
                errors["base"] = "cannot_get_sn"

            except CannotGetModel:
                errors["base"] = "cannot_get_model"

            except AbortFlow as af:
                reason = getattr(af, "reason", str(af))
                if reason == "already_configured":
                    errors["base"] = "already_configured"
                elif reason == "already_in_progress":
                    errors["base"] = "already_in_progress"
                else:
                    raise

            except Exception as err:
                _LOGGER.exception("Unexpected error during user step: %s", err)
                errors["base"] = "unknown"

            if not errors:
                return await self.async_step_grid_sensor()

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema({vol.Required("IP"): str}),
            errors=errors,
        )

    async def async_step_grid_sensor(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """
        Optional step: select a HA sensor entity as grid power source.

        When configured, the integration registers a local HTTP proxy endpoint
        in HA (Shelly-compatible format) and sets MD/MM on the device so it
        uses its internal PID controller for regulation.

        The sensor must provide grid power in Watts:
        - Positive values = export to grid (feed-in)
        - Negative values = import from grid (consumption)

        Args:
            user_input: Dictionary containing user input

        Returns:
            FlowResult indicating the next step in the configuration flow

        """
        if user_input is not None:
            grid_sensor = user_input.get(CONF_GRID_SENSOR)

            return self.async_create_entry(
                title=self._model,
                data={
                    "ip": self._ip,
                    "sn": self._sn,
                    "model": self._model,
                    CONF_GRID_SENSOR: grid_sensor or None,
                },
            )

        return self.async_show_form(
            step_id="grid_sensor",
            data_schema=vol.Schema(
                {
                    vol.Optional(CONF_GRID_SENSOR): selector.EntitySelector(
                        selector.EntitySelectorConfig(
                            domain=SENSOR_DOMAIN,
                            device_class="power",
                            multiple=False,
                        )
                    ),
                }
            ),
            description_placeholders={
                "sn": self._sn,
                "model": self._model,
            },
        )

    async def async_step_reconfigure(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """
        Handle reconfiguration of an existing SunEnergyXT entry.

        Allows the user to change or remove the grid sensor without
        having to delete and re-add the integration.

        The current grid sensor is pre-filled so the user can see what
        is configured and change it if needed.

        Args:
            user_input: Dictionary containing user input

        Returns:
            FlowResult indicating the next step in the configuration flow

        """
        entry = self.hass.config_entries.async_get_entry(self.context["entry_id"])
        current_grid_sensor = entry.data.get(CONF_GRID_SENSOR) if entry else None

        if user_input is not None:
            grid_sensor = user_input.get(CONF_GRID_SENSOR) or None

            return self.async_update_reload_and_abort(
                entry,
                data_updates={CONF_GRID_SENSOR: grid_sensor},
                reason="reconfigure_successful",
            )

        return self.async_show_form(
            step_id="reconfigure",
            data_schema=vol.Schema(
                {
                    vol.Optional(
                        CONF_GRID_SENSOR,
                        default=current_grid_sensor,
                    ): selector.EntitySelector(
                        selector.EntitySelectorConfig(
                            domain=SENSOR_DOMAIN,
                            device_class="power",
                            multiple=False,
                        )
                    ),
                }
            ),
            description_placeholders={
                "sn": entry.data.get("sn") if entry else "",
                "model": entry.data.get("model") if entry else "",
            },
        )

    async def async_step_zeroconf(
        self, discovery_info: ZeroconfServiceInfo
    ) -> FlowResult:
        """
        Handle zeroconf discovery for SunEnergyXT devices.

        Args:
            discovery_info: Zeroconf service information

        Returns:
            FlowResult indicating the next step in the configuration flow

        """
        hostname = (discovery_info.hostname or "").rstrip(".")
        if not (hostname.startswith(HOST_PREFIX) and hostname.endswith(HOST_SUFFIX)):
            return self.async_abort(reason="not_device")

        sn = hostname[len(HOST_PREFIX) : -len(HOST_SUFFIX)]
        ip = str(discovery_info.host)
        model = discovery_info.properties["model"]

        await self.async_set_unique_id(sn)
        self._abort_if_unique_id_configured(updates={"ip": ip})

        _LOGGER.debug("Zeroconf discovery: %s", discovery_info)

        self.context["title_placeholders"] = {"sn": sn}

        self._discovered_sn = sn
        self._discovered_ip = ip
        self._discovered_model = model

        return await self.async_step_zeroconf_confirm()

    async def async_step_zeroconf_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """
        Confirm zeroconf discovery for SunEnergyXT devices.

        Args:
            user_input: Dictionary containing user input

        Returns:
            FlowResult indicating the next step in the configuration flow

        """
        errors: dict[str, str] = {}

        if user_input is not None:
            sn = self._discovered_sn
            ip = self._discovered_ip
            model = self._discovered_model

            try:
                _LOGGER.debug("zeroconf discover ip: %s", ip)
                await _validate_input(ip)
                info = await _get_device_info(ip)
                sn = info["sn"]
                model = info["model"]
                _LOGGER.debug("get sn: %s, model: %s", sn, model)

                await self.async_set_unique_id(sn)
                self._abort_if_unique_id_configured(updates={"ip": ip})

                self._ip = ip
                self._sn = sn
                self._model = model

            except CannotConnect:
                return self.async_abort(reason="cannot_connect")

            except CannotGetSN:
                return self.async_abort(reason="cannot_get_sn")

            except CannotGetModel:
                return self.async_abort(reason="cannot_get_model")

            except AbortFlow as af:
                reason = getattr(af, "reason", str(af))
                if reason == "already_configured":
                    return self.async_abort(reason="already_configured")
                raise

            except Exception as err:
                _LOGGER.exception("Unexpected error during zeroconf step: %s", err)
                return self.async_abort(reason="unknown")

            return await self.async_step_grid_sensor()

        return self.async_show_form(
            step_id="zeroconf_confirm",
            data_schema=vol.Schema({}),
            description_placeholders={
                "sn": self._discovered_sn,
                "host": self._discovered_ip,
            },
            errors=errors,
        )


class InvalidIP(exceptions.HomeAssistantError):
    """Input invalid IP."""


class CannotConnect(exceptions.HomeAssistantError):
    """Error to indicate we cannot connect."""


class CannotGetSN(exceptions.HomeAssistantError):
    """Error to indicate we cannot get SN."""


class CannotGetModel(exceptions.HomeAssistantError):
    """Error to indicate we cannot get Model."""
