"""Noyce Joyce Nixie Clock BLE protocol.

Pure helpers without Home Assistant imports so they can be unit tested in isolation.

Protocol reverse-read from the official Flutter app
(https://github.com/michalvalkoun/noyce_joyce_nixie, lib/ble/ble_device_interactor.dart):

* All settings live in one vendor service, no pairing/bonding (the firmware refuses bonded peers).
* Integers are little-endian uint32.
* Timestamps are "local epoch": unix seconds + the local UTC offset. The firmware knows
  nothing about time zones or DST, so the host must resync after every offset change.

SAFETY: characteristic A8ED14FF is deliberately NOT defined here. Writing 0x99 to it
reboots the clock into the Nordic DFU bootloader (used by the app for firmware updates).
It must never be exposed by this integration.
"""

from __future__ import annotations

import calendar
from datetime import date, datetime, time
import re
import struct

INTERFACE_SERVICE_UUID = "a8ed1400-130a-4d4b-acba-5de7e77e9b47"
INFO_SERVICE_UUID = "0000180a-0000-1000-8000-00805f9b34fb"

CHAR_FIRMWARE_REVISION = "00002a26-0000-1000-8000-00805f9b34fb"
CHAR_DATETIME = "a8ed1410-130a-4d4b-acba-5de7e77e9b47"
CHAR_TIME_FORMAT = "a8ed1420-130a-4d4b-acba-5de7e77e9b47"
CHAR_HOURGLASS = "a8ed1421-130a-4d4b-acba-5de7e77e9b47"
CHAR_NIGHT_MODE = "a8ed1423-130a-4d4b-acba-5de7e77e9b47"
CHAR_NIGHT_MODE_END = "a8ed1424-130a-4d4b-acba-5de7e77e9b47"
CHAR_NIGHT_MODE_START = "a8ed1425-130a-4d4b-acba-5de7e77e9b47"
CHAR_NIXIE_DOTS = "a8ed1426-130a-4d4b-acba-5de7e77e9b47"

WRITABLE_CHARACTERISTICS = frozenset(
    {
        CHAR_DATETIME,
        CHAR_TIME_FORMAT,
        CHAR_HOURGLASS,
        CHAR_NIGHT_MODE,
        CHAR_NIGHT_MODE_END,
        CHAR_NIGHT_MODE_START,
        CHAR_NIXIE_DOTS,
    }
)

# Index written to CHAR_HOURGLASS -> how often the cathode-poisoning cycle runs.
HOURGLASS_OPTIONS: tuple[str, ...] = ("1_min", "10_min", "30_min", "60_min", "3_am")

# Value written to CHAR_TIME_FORMAT (app: "24 h" button writes 0, "12 h" writes 1).
TIME_FORMAT_OPTIONS: tuple[str, ...] = ("24h", "12h")

SECONDS_PER_DAY = 86_400

_FW_VERSION_RE = re.compile(r"(\d+(?:\.\d+)+)")


def encode_u32(value: int) -> bytes:
    """Encode an unsigned 32-bit little-endian integer."""
    return struct.pack("<I", value)


def decode_u32(data: bytes | bytearray) -> int:
    """Decode an unsigned 32-bit little-endian integer."""
    if len(data) < 4:
        raise ValueError(f"expected 4 bytes, got {len(data)}")
    return struct.unpack_from("<I", data)[0]


def encode_u8(value: int) -> bytes:
    """Encode a single byte."""
    if not 0 <= value <= 0xFF:
        raise ValueError(f"value {value} out of uint8 range")
    return bytes((value,))


def decode_u8(data: bytes | bytearray) -> int:
    """Decode a single byte."""
    if not data:
        raise ValueError("empty payload")
    return data[0]


def to_local_epoch(unix_ts: int, utc_offset_s: int) -> int:
    """Convert a unix timestamp to the clock's local epoch."""
    return unix_ts + utc_offset_s


def night_mode_value(value: time, on_date: date) -> int:
    """Encode a night-mode boundary the way the app does (local wall time as epoch)."""
    naive = datetime.combine(on_date, value.replace(tzinfo=None, microsecond=0))
    return calendar.timegm(naive.timetuple())


def time_of_day(local_epoch: int) -> time:
    """Extract the wall-clock time of day from a local-epoch value."""
    seconds = local_epoch % SECONDS_PER_DAY
    return time(seconds // 3600, (seconds % 3600) // 60, seconds % 60)


def parse_firmware(raw: bytes | bytearray) -> str | None:
    """Return the version number from the firmware revision string (e.g. '... FW 1.17')."""
    text = bytes(raw).decode("utf-8", errors="replace").strip("\x00 \r\n")
    matches = _FW_VERSION_RE.findall(text)
    return matches[-1] if matches else (text or None)
