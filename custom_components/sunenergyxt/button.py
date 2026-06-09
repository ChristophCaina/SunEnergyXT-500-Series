"""
Button entities for SunEnergyXT 500 Series integration.

This module implements button entities for the SunEnergyXT integration,
primarily used for device restart functionality.

Classes:
- SunlitButton: Represents a button entity for controlling SunEnergyXT devices

Constants:
- BUTTON_META: Metadata configuration for button entities
"""

import logging
from http import HTTPStatus
from typing import Any

import async_timeout
from homeassistant.components.button import ButtonDeviceClass, ButtonEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import SunlitDataUpdateCoordinator

_LOGGER = logging.getLogger(__name__)

BUTTON_META: dict[str, dict[str, Any]] = {
    "RT": {
        "device_class": ButtonDeviceClass.RESTART,
        "icon": "mdi:restart",
    },
}


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """
    Set up button entities for SunEnergyXT.

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

    entities: list[ButtonEntity] = []

    keys = [
        "RT",
    ]

    for key in keys:
        entities.append(
            SunlitButton(
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


class SunlitButton(CoordinatorEntity[SunlitDataUpdateCoordinator], ButtonEntity):
    """
    Button entity for SunEnergyXT device actions.

    Represents a button entity that triggers specific actions on the SunEnergyXT device,
    such as device restart.
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
        Initialize the button entity.

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

        meta = BUTTON_META.get(key, {})

        self._attr_unique_id = f"{DOMAIN}_{entry_id}_{key}"
        self._attr_translation_key = key.lower()
        self._attr_device_info = device_info

        device_class = meta.get("device_class")
        if device_class:
            self._attr_device_class = device_class

        icon = meta.get("icon")
        if icon:
            self._attr_icon = icon

    @property
    def extra_state_attributes(self) -> dict:
        """Expose API key for debugging/transparency."""
        return {"api_key": self._key}

    async def async_press(self) -> None:
        """
        Handle button press event.

        Sends a request to the device to perform the action associated with this button.

        Raises:
            RuntimeError: If there's an error pressing the button

        """
        payload = {"state": {self._key: 1}}
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
            _LOGGER.exception("Error pressing button %s: %s", self._key, err)
            raise
