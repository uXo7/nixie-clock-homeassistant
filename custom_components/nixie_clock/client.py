"""BLE client for the Noyce Joyce Nixie Clock.

Connect-on-demand: every operation opens a short connection and closes it again, so the
clock stays free for the phone app and HA does not hold a connection slot permanently.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass, replace
from datetime import datetime
import logging
import time

from bleak.backends.device import BLEDevice
from bleak.exc import BleakError
from bleak_retry_connector import BleakClientWithServiceCache, establish_connection

from homeassistant.components import bluetooth
from homeassistant.core import HomeAssistant
from homeassistant.util import dt as dt_util

from . import protocol
from .const import MAX_CONNECT_ATTEMPTS

_LOGGER = logging.getLogger(__name__)


class NixieClockError(Exception):
    """Communication with the clock failed."""


class NixieClockNotFoundError(NixieClockError):
    """The clock is not visible to any connectable Bluetooth adapter or proxy."""


@dataclass(slots=True)
class NixieClockState:
    """Snapshot of the clock, as read over BLE."""

    firmware: str | None = None
    time_format: int | None = None
    hourglass: int | None = None
    night_mode: bool | None = None
    night_mode_start_raw: int | None = None
    night_mode_end_raw: int | None = None
    nixie_dots: bool | None = None
    rssi: int | None = None
    # Filled in by a time sync only.
    clock_raw_before_sync: int | None = None
    drift_s: float | None = None
    last_sync: datetime | None = None
    synced_utc_offset_s: int | None = None

    def with_sync_from(self, other: NixieClockState | None) -> NixieClockState:
        """Carry the sync-related fields over from a previous snapshot."""
        if other is None:
            return self
        return replace(
            self,
            clock_raw_before_sync=other.clock_raw_before_sync,
            drift_s=other.drift_s,
            last_sync=other.last_sync,
            synced_utc_offset_s=other.synced_utc_offset_s,
        )


def _utc_offset_s(unix_ts: float) -> int:
    """UTC offset of HA's configured time zone at the given instant."""
    offset = datetime.fromtimestamp(unix_ts, dt_util.get_default_time_zone()).utcoffset()
    return int(offset.total_seconds()) if offset else 0


class NixieClockClient:
    """Talks to one clock."""

    def __init__(self, hass: HomeAssistant, address: str) -> None:
        self._hass = hass
        self._address = address

    @property
    def address(self) -> str:
        return self._address

    def _ble_device(self) -> BLEDevice | None:
        return bluetooth.async_ble_device_from_address(self._hass, self._address, connectable=True)

    def _rssi(self) -> int | None:
        info = bluetooth.async_last_service_info(self._hass, self._address, connectable=True)
        return info.rssi if info else None

    @asynccontextmanager
    async def _session(self) -> AsyncIterator[BleakClientWithServiceCache]:
        ble_device = self._ble_device()
        if ble_device is None:
            raise NixieClockNotFoundError(
                f"{self._address} is not in range of any connectable Bluetooth adapter"
            )
        try:
            client = await establish_connection(
                BleakClientWithServiceCache,
                ble_device,
                ble_device.name or self._address,
                max_attempts=MAX_CONNECT_ATTEMPTS,
                ble_device_callback=lambda: self._ble_device() or ble_device,
            )
        except (BleakError, TimeoutError) as err:
            raise NixieClockError(f"Cannot connect to {self._address}: {err}") from err
        try:
            yield client
        except (BleakError, TimeoutError, ValueError) as err:
            raise NixieClockError(f"GATT operation failed on {self._address}: {err}") from err
        finally:
            try:
                await client.disconnect()
            except BleakError as err:  # pragma: no cover - best effort
                _LOGGER.debug("Disconnect from %s failed: %s", self._address, err)

    @staticmethod
    async def _read(client: BleakClientWithServiceCache, uuid: str) -> bytearray | None:
        char = client.services.get_characteristic(uuid)
        if char is None:
            return None
        return await client.read_gatt_char(char)

    async def _read_state(self, client: BleakClientWithServiceCache) -> NixieClockState:
        state = NixieClockState(rssi=self._rssi())
        if (raw := await self._read(client, protocol.CHAR_FIRMWARE_REVISION)) is not None:
            state.firmware = protocol.parse_firmware(raw)
        if (raw := await self._read(client, protocol.CHAR_TIME_FORMAT)) is not None:
            state.time_format = protocol.decode_u8(raw)
        if (raw := await self._read(client, protocol.CHAR_HOURGLASS)) is not None:
            state.hourglass = protocol.decode_u8(raw)
        if (raw := await self._read(client, protocol.CHAR_NIGHT_MODE)) is not None:
            state.night_mode = protocol.decode_u8(raw) > 0
        if (raw := await self._read(client, protocol.CHAR_NIGHT_MODE_START)) is not None:
            state.night_mode_start_raw = protocol.decode_u32(raw)
        if (raw := await self._read(client, protocol.CHAR_NIGHT_MODE_END)) is not None:
            state.night_mode_end_raw = protocol.decode_u32(raw)
        if (raw := await self._read(client, protocol.CHAR_NIXIE_DOTS)) is not None:
            state.nixie_dots = protocol.decode_u8(raw) > 0
        return state

    async def async_read_and_sync(self) -> NixieClockState:
        """Read all settings, measure drift, then set the clock to HA's time."""
        async with self._session() as client:
            state = await self._read_state(client)

            if client.services.get_characteristic(protocol.CHAR_DATETIME) is None:
                raise NixieClockError("Date/time characteristic not found (unsupported firmware?)")

            # Drift: what the clock shows vs. what it should show right now.
            raw_clock = protocol.decode_u32(await client.read_gatt_char(protocol.CHAR_DATETIME))
            now = time.time()
            expected = now + _utc_offset_s(now)
            state.clock_raw_before_sync = raw_clock
            # The clock has whole-second resolution and truncates; compare against the
            # middle of its current second to avoid a systematic -0.5 s bias.
            state.drift_s = round(raw_clock + 0.5 - expected, 1)

            # Align the write to the next full second so the tubes flip on the boundary.
            target = int(time.time()) + 1
            await asyncio.sleep(max(0.0, target - time.time()))
            offset = _utc_offset_s(target)
            await client.write_gatt_char(
                protocol.CHAR_DATETIME,
                protocol.encode_u32(protocol.to_local_epoch(target, offset)),
                response=True,
            )
            state.last_sync = dt_util.utcnow()
            state.synced_utc_offset_s = offset

        _LOGGER.debug(
            "Synced %s: drift %.1f s, offset %d s, fw %s, rssi %s",
            self._address,
            state.drift_s,
            offset,
            state.firmware,
            state.rssi,
        )
        return state

    async def async_write(self, uuid: str, payload: bytes) -> NixieClockState:
        """Write one setting and read the state back."""
        if uuid not in protocol.WRITABLE_CHARACTERISTICS:
            # Hard guard: never let anything (incl. future code) poke unknown characteristics.
            raise ValueError(f"Refusing to write to non-whitelisted characteristic {uuid}")
        async with self._session() as client:
            await client.write_gatt_char(uuid, payload, response=True)
            return await self._read_state(client)
