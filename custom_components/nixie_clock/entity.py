"""Base entity for the Nixie Clock integration."""

from __future__ import annotations

from homeassistant.helpers.device_registry import CONNECTION_BLUETOOTH, DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import MANUFACTURER, MODEL
from .coordinator import NixieClockCoordinator


class NixieClockEntity(CoordinatorEntity[NixieClockCoordinator]):
    """Common device info and unique id."""

    _attr_has_entity_name = True

    def __init__(self, coordinator: NixieClockCoordinator, key: str) -> None:
        super().__init__(coordinator)
        address = coordinator.client.address
        self._attr_unique_id = f"{address}_{key}"
        self._attr_translation_key = key
        self._attr_device_info = DeviceInfo(
            connections={(CONNECTION_BLUETOOTH, address)},
            name=coordinator.config_entry.title,
            manufacturer=MANUFACTURER,
            model=MODEL,
            sw_version=coordinator.data.firmware if coordinator.data else None,
        )
