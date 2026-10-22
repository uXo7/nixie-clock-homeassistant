"""Noyce Joyce Nixie Clock integration (BLE, local)."""

from __future__ import annotations

from datetime import timedelta

from homeassistant.const import CONF_ADDRESS, Platform
from homeassistant.core import HomeAssistant

from .client import NixieClockClient
from .const import CONF_SYNC_INTERVAL, DEFAULT_SYNC_INTERVAL_HOURS
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

    hours = int(entry.options.get(CONF_SYNC_INTERVAL, DEFAULT_SYNC_INTERVAL_HOURS))
    coordinator = NixieClockCoordinator(
        hass, entry, NixieClockClient(hass, address), timedelta(hours=hours)
    )
    entry.runtime_data = coordinator
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    # Sync on every setup / HA restart, in the background: a BLE connect with retries can
    # take tens of seconds and must not block HA startup. Failure is not fatal - the clock
    # is often silent (connected to the phone app, out of range); the hourly check and the
    # advertisement watch retry, so we don't depend on HA's setup-retry backoff.
    coordinator.async_start_initial_sync()
    entry.async_on_unload(coordinator.async_start_hourly_check())
    entry.async_on_unload(coordinator.async_start_advertisement_watch())
    return True


async def async_unload_entry(hass: HomeAssistant, entry: NixieClockConfigEntry) -> bool:
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
