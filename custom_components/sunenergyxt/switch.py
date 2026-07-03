"""
Switch entities for SunEnergyXT 500 Series integration.

This module implements switch entities for the SunEnergyXT integration,
allowing control of various device modes and functions.

Classes:
- SunlitSwitch: Represents a switch entity for controlling SunEnergyXT device modes

Constants:
- SWITCH_META: Metadata configuration for switch entities
"""

import logging
from http import HTTPStatus
from typing import Any

import async_timeout
from homeassistant.components.switch import SwitchDeviceClass, SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import SunlitDataUpdateCoordinator

_LOGGER = logging.getLogger(__name__)

SWITCH_META: dict[str, dict[str, Any]] = {
    "LM": {
        "icon": "mdi:lan",
    },
    "MM": {
        "icon": "mdi:meter-electric-outline",
    },
    "PM": {
        "icon": "mdi:link-variant",
    },
    "UO": {
        "icon": "mdi:power-plug-outline",
        "device_class": SwitchDeviceClass.OUTLET,
    },
    "LFB": {
        "icon": "mdi:link-variant",
    },
    "LPS": {
        "icon": "mdi:link-variant",
    },
}


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """
    Set up switch entities for SunEnergyXT.

    Args:
        hass: Home Assistant instance
        entry: Config entry containing device information
        async_add_entities: Callback to add new entities

    """
    config = hass.data[DOMAIN][entry.entry_id]
    sn = config["sn"]
    ip = config["ip"]
    model = config["model"]
    coordinator = config["coordinator"]

    device_info = DeviceInfo(
        identifiers={(DOMAIN, entry.entry_id)},
        name=sn,
        manufacturer="SunEnergyXT",
        model=model,
        serial_number=sn,
    )

    entities: list[SwitchEntity] = []

    keys = [
        "LM",
        "MM",
        "PM",
        "UO",
        "LFB",
        "LPS",
    ]

    for key in keys:
        entities.append(
            SunlitSwitch(
                coordinator=coordinator,
                entry_id=entry.entry_id,
                key=key,
                sn=sn,
                ip=ip,
                device_info=device_info,
                hass=hass,
            )
        )

    async_add_entities(entities, True)  # noqa: FBT003


class SunlitSwitch(CoordinatorEntity[SunlitDataUpdateCoordinator], SwitchEntity):
    """
    Switch entity for SunEnergyXT device modes.

    Represents a switch entity that controls various device modes and functions.
    """

    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: SunlitDataUpdateCoordinator,
        entry_id: str,
        key: str,
        sn: str,
        ip: str,
        device_info: DeviceInfo,
        hass: HomeAssistant,
    ) -> None:
        """
        Initialize the switch entity.

        Args:
            coordinator: Data update coordinator
            entry_id: Config entry ID
            key: Parameter key
            sn: Device serial number
            ip: Device IP address
            device_info: Device information
            hass: Home Assistant instance

        """
        super().__init__(coordinator)
        self._key = key
        self._sn = sn
        self._ip = ip
        self._session = async_get_clientsession(hass)

        meta = SWITCH_META.get(key, {})

        self._attr_unique_id = f"{DOMAIN}_{entry_id}_{key}"
        self._attr_translation_key = key.lower()
        self._attr_device_info = device_info

        icon = meta.get("icon")
        if icon:
            self._attr_icon = icon

        device_class = meta.get("device_class")
        if device_class:
            self._attr_device_class = device_class

    @property
    def extra_state_attributes(self) -> dict:
        """Expose API key for debugging/transparency."""
        return {"api_key": self._key}

    @property
    def is_on(self) -> bool:
        """
        Get the current state of the switch.

        Returns:
            True if the switch is on, False otherwise

        """
        raw = self.coordinator.data.get(self._key)
        return bool(int(raw)) if raw is not None else False

    async def async_turn_on(self, **kwargs: dict[str, Any]) -> None:  # noqa: ARG002
        """Turn the switch on."""
        await self._async_write_switch(is_on=True)

    async def async_turn_off(self, **kwargs: dict[str, Any]) -> None:  # noqa: ARG002
        """Turn the switch off."""
        await self._async_write_switch(is_on=False)

    async def _async_write_switch(self, is_on: bool) -> None:  # noqa: FBT001
        """
        Write the switch state to the device.

        Args:
            is_on: True to turn the switch on, False to turn it off

        Raises:
            RuntimeError: If there's an error writing to the device

        """
        if self._key == "MM":
            value = 1 if is_on else 0
            md_value = self.coordinator.data.get("MD", "").strip()
            if value == 0:
                # Only touch MM here. MD is independent config (which
                # meter/proxy field to use) and must survive MM being
                # switched off — otherwise immediately switching MM back
                # on fails with "no meter configured" until the next
                # reload re-syncs MD via _sync_md() in __init__.py.
                payload = {"state": {"MM": 0}}
            elif md_value == "":
                # Turning MM on requires a meter (MD) to already be
                # configured — either via the config flow's grid sensor
                # (proxy) or manually via the MD text entity. Surface
                # this to the user instead of silently doing nothing.
                msg = (
                    "Cannot enable local zero feed-in mode (MM): no meter "
                    "configured (MD is empty). Configure a grid sensor via "
                    "the integration options, or set MD manually first."
                )
                raise HomeAssistantError(msg)
            else:
                payload = {"state": {self._key: value}}
        else:
            value = 1 if is_on else 0
            payload = {"state": {self._key: value}}
        try:
            async with (
                async_timeout.timeout(5),
                self._session.post(
                    f"http://{self._ip}/write",
                    json=payload,
                ) as resp,
            ):
                if resp.status != HTTPStatus.OK:
                    text = await resp.text()
                    msg = f"HTTP {resp.status}: {text}"
                    raise RuntimeError(msg)
        except Exception as err:
            _LOGGER.exception("Error writing switch %s: %s", self._key, err)
            raise

        if isinstance(self.coordinator.data, dict):
            self.coordinator.data[self._key] = value
        self.coordinator.async_set_updated_data(self.coordinator.data)
