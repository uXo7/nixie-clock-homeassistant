"""Noyce Joyce Nixie Clock integration (BLE, local)."""

from __future__ import annotations

from datetime import timedelta

from homeassistant.components import bluetooth
from homeassistant.const import CONF_ADDRESS, Platform
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryNotReady

from .client import NixieClockClient
from .const import CONF_SYNC_INTERVAL, DEFAULT_SYNC_INTERVAL_HOURS, DOMAIN
from .coordinator import NixieClockConfigEntry, NixieClockCoordinator

PLATFORMS: list[Platform] = [
    Platform.BUTTON,
    Platform.SELECT,
    Platform.SENSOR,
    Platform.SWITCH,
    Platform.TIME,
]


async def async_setup_entry(hass: HomeAssistant, entry: NixieClockConfigEntry) -> bool:
    address: str = entry.data[CONF_ADDRESS]

    if not bluetooth.async_ble_device_from_address(hass, address, connectable=True):
        raise ConfigEntryNotReady(
            translation_domain=DOMAIN,
            translation_key="not_in_range",
            translation_placeholders={"address": address},
        )

    hours = int(entry.options.get(CONF_SYNC_INTERVAL, DEFAULT_SYNC_INTERVAL_HOURS))
    coordinator = NixieClockCoordinator(
        hass, entry, NixieClockClient(hass, address), timedelta(hours=hours)
    )
    # First refresh = read + time sync, so every HA restart also corrects the clock.
    await coordinator.async_config_entry_first_refresh()
    entry.async_on_unload(coordinator.async_start_hourly_check())

    entry.runtime_data = coordinator
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: NixieClockConfigEntry) -> bool:
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
