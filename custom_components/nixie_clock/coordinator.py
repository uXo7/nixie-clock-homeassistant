"""Coordinator for the Nixie Clock integration."""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta
import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import CALLBACK_TYPE, HomeAssistant, callback
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.event import async_track_time_change
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util import dt as dt_util

from .client import NixieClockClient, NixieClockError, NixieClockState
from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)

type NixieClockConfigEntry = ConfigEntry[NixieClockCoordinator]


class NixieClockCoordinator(DataUpdateCoordinator[NixieClockState]):
    """Reads the clock and syncs its time.

    Every refresh is a full read + time sync. Refreshes happen
    * on the configured interval,
    * on the sync button,
    * at the top of every hour if the UTC offset changed since the last sync (DST),
      or if the previous attempt failed (weak BLE link -> retry hourly, not daily).
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

    async def _async_update_data(self) -> NixieClockState:
        async with self._lock:
            try:
                return await self.client.async_read_and_sync()
            except NixieClockError as err:
                raise UpdateFailed(str(err)) from err

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
    def async_start_hourly_check(self) -> CALLBACK_TYPE:
        """Resync after DST changes and retry failed syncs every hour."""

        @callback
        def _check(now: datetime) -> None:
            offset = dt_util.now().utcoffset()
            offset_s = int(offset.total_seconds()) if offset else 0
            data = self.data
            if self.last_update_success and data and data.synced_utc_offset_s == offset_s:
                return
            _LOGGER.debug(
                "Hourly resync of %s (last success: %s, offset %s -> %s)",
                self.client.address,
                self.last_update_success,
                data.synced_utc_offset_s if data else None,
                offset_s,
            )
            self.config_entry.async_create_background_task(
                self.hass, self.async_refresh(), f"{DOMAIN}_hourly_resync"
            )

        # A few seconds past the hour: DST switches happen exactly on the hour.
        return async_track_time_change(self.hass, _check, minute=0, second=5)
