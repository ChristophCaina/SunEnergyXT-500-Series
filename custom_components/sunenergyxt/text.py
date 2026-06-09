"""
Text entities for SunEnergyXT 500 Series integration.

This module implements text entities for the SunEnergyXT integration,
allowing control of text-based device parameters such as mode and time zone.

Classes:
- SunlitText: Represents a text entity for controlling SunEnergyXT device parameters

Constants:
- TEXT_META: Metadata configuration for text entities
"""

import logging
from http import HTTPStatus
from typing import Any

import async_timeout
from homeassistant.components.text import TextEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.entity import DeviceInfo, EntityCategory
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import SunlitDataUpdateCoordinator

_LOGGER = logging.getLogger(__name__)

TEXT_META: dict[str, dict[str, Any]] = {
    "MD": {
        "entity_category": EntityCategory.CONFIG,
        "icon": "mdi:code-json",
    },
    "TZ": {
        "entity_category": EntityCategory.CONFIG,
        "icon": "mdi:map-clock-outline",
    },
}


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """
    Set up text entities for SunEnergyXT.

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

    entities: list[TextEntity] = []

    keys = [
        "MD",
        "TZ",
    ]

    for key in keys:
        entities.append(
            SunlitText(
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


class SunlitText(CoordinatorEntity[SunlitDataUpdateCoordinator], TextEntity):
    """
    Text entity for SunEnergyXT device parameters.

    Represents a text entity that controls text-based device parameters
    such as mode and time zone.
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
        Initialize the text entity.

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

        meta = TEXT_META.get(key, {})

        self._attr_unique_id = f"{DOMAIN}_{entry_id}_{key}"
        self._attr_translation_key = key.lower()
        self._attr_device_info = device_info

        entity_category = meta.get("entity_category")
        if entity_category is not None:
            self._attr_entity_category = entity_category

        icon = meta.get("icon")
        if icon:
            self._attr_icon = icon

    @property
    def extra_state_attributes(self) -> dict:
        """Expose API key for debugging/transparency."""
        return {"api_key": self._key}

    @property
    def native_value(self) -> str:
        """
        Get the current value of the text entity.

        Returns:
            Current text value

        """
        raw = self.coordinator.data.get(self._key)
        return str(raw) if raw is not None else ""

    async def async_set_value(self, value: str) -> None:
        """
        Set the value of the text entity.

        Args:
            value: New text value to set

        """
        await self._async_write_text(value)

    async def _async_write_text(self, value: str) -> None:
        """
        Write the text value to the device.

        Args:
            value: Text value to write to the device

        Raises:
            RuntimeError: If there's an error writing to the device

        """
        if self._key == "MD":
            mm_value = 0 if value.strip() == "" else 1
            payload = {"state": {"MM": mm_value, "MD": value}}
        else:
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
            _LOGGER.exception("Error writing text %s: %s", self._key, err)
            raise

        if isinstance(self.coordinator.data, dict):
            self.coordinator.data[self._key] = value
            if self._key == "MD":
                self.coordinator.data["MM"] = 0 if value.strip() == "" else 1
        self.async_write_ha_state()
