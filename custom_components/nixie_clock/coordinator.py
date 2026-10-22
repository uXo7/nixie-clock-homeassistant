"""Coordinator for the Nixie Clock integration."""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta
import logging
import time

from homeassistant.components import bluetooth
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import CALLBACK_TYPE, HomeAssistant, callback
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.event import async_track_time_change
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util import dt as dt_util

from .client import NixieClockClient, NixieClockError, NixieClockState
from .const import ADVERTISEMENT_RETRY_COOLDOWN_S, DOMAIN

_LOGGER = logging.getLogger(__name__)

type NixieClockConfigEntry = ConfigEntry[NixieClockCoordinator]


class NixieClockCoordinator(DataUpdateCoordinator[NixieClockState]):
    """Reads the clock and syncs its time.

    Every refresh is a time sync followed by a settings read. Refreshes happen
    * at setup and on the configured interval,
    * on the sync button,
    * at the top of every hour if the UTC offset changed since the last sync (DST),
      or if the previous attempt failed,
    * as soon as the clock advertises again after a failed attempt. The clock stops
      advertising while something (e.g. the phone app) is connected to it.
    """

    config_entry: NixieClockConfigEntry

    def __init__(
        self,
        hass: HomeAssistant,
        entry: NixieClockConfigEntry,
        client: NixieClockClient,
        sync_interval: timedelta,
    ) -> None:
        super().__init__(
            hass,
            _LOGGER,
            config_entry=entry,
            name=f"{DOMAIN} {client.address}",
            update_interval=sync_interval,
            always_update=True,
        )
        self.client = client
        self._lock = asyncio.Lock()
        # None = never retried. Not 0.0: time.monotonic() counts from host boot, so on a
        # freshly booted host 'now - 0.0' would still be inside the cooldown.
        self._last_advertisement_retry: float | None = None

    @property
    def needs_sync(self) -> bool:
        """True when the last attempt failed or nothing was synced yet."""
        return not self.last_update_success or self.data is None

    async def _async_update_data(self) -> NixieClockState:
        async with self._lock:
            try:
                state = await self.client.async_read_and_sync()
            except NixieClockError as err:
                raise UpdateFailed(str(err)) from err
        if not state.settings_valid:
            state = state.with_settings_from(self.data)
        self._update_device_firmware(state.firmware)
        return state

    async def async_write(self, uuid: str, payload: bytes) -> None:
        """Write a setting; keep the sync timer and sync statistics untouched."""
        async with self._lock:
            try:
                state = await self.client.async_write(uuid, payload)
            except NixieClockError as err:
                raise HomeAssistantError(
                    translation_domain=DOMAIN,
                    translation_key="write_failed",
                    translation_placeholders={"error": str(err)},
                ) from err
        self.data = state.with_sync_from(self.data)
        self.async_update_listeners()

    @callback
    def _update_device_firmware(self, firmware: str | None) -> None:
        if not firmware:
            return
        registry = dr.async_get(self.hass)
        device = registry.async_get_device(
            connections={(dr.CONNECTION_BLUETOOTH, self.client.address)}
        )
        if device and device.sw_version != firmware:
            registry.async_update_device(device.id, sw_version=firmware)

    @callback
    def _async_schedule_refresh(self, reason: str) -> None:
        _LOGGER.debug("Resync of %s: %s", self.client.address, reason)
        self.config_entry.async_create_background_task(
            self.hass, self.async_refresh(), f"{DOMAIN}_resync"
        )

    @callback
    def async_start_initial_sync(self) -> None:
        """First sync; also arms the advertisement cooldown so it doesn't double-fire."""
        self._last_advertisement_retry = time.monotonic()
        self._async_schedule_refresh("setup")

    @callback
    def async_start_hourly_check(self) -> CALLBACK_TYPE:
        """Resync after DST changes and retry failed syncs every hour."""

        @callback
        def _check(now: datetime) -> None:
            offset = dt_util.now().utcoffset()
            offset_s = int(offset.total_seconds()) if offset else 0
            if self.needs_sync:
                self._async_schedule_refresh("hourly retry after failure")
            elif self.data.synced_utc_offset_s != offset_s:
                self._async_schedule_refresh(
                    f"UTC offset {self.data.synced_utc_offset_s} -> {offset_s}"
                )

        # A few seconds past the hour: DST switches happen exactly on the hour.
        return async_track_time_change(self.hass, _check, minute=0, second=5)

    @callback
    def async_start_advertisement_watch(self) -> CALLBACK_TYPE:
        """Sync as soon as the clock is heard again after a failed attempt."""

        @callback
        def _seen(
            service_info: bluetooth.BluetoothServiceInfoBleak,
            change: bluetooth.BluetoothChange,
        ) -> None:
            if not self.needs_sync or self._lock.locked():
                return
            now = time.monotonic()
            last = self._last_advertisement_retry
            if last is not None and now - last < ADVERTISEMENT_RETRY_COOLDOWN_S:
                return
            self._last_advertisement_retry = now
            self._async_schedule_refresh(f"advertisement seen (rssi {service_info.rssi})")

        return bluetooth.async_register_callback(
            self.hass,
            _seen,
            bluetooth.BluetoothCallbackMatcher(address=self.client.address, connectable=True),
            bluetooth.BluetoothScanningMode.PASSIVE,
        )
