"""Constants for the Nixie Clock integration."""

from __future__ import annotations

from typing import Final

DOMAIN: Final = "nixie_clock"

DEVICE_NAME_PREFIX: Final = "Nixie Clock"
MANUFACTURER: Final = "Noyce Joyce"
MODEL: Final = "Nixie Clock"

CONF_SYNC_INTERVAL: Final = "sync_interval_hours"
DEFAULT_SYNC_INTERVAL_HOURS: Final = 24
MIN_SYNC_INTERVAL_HOURS: Final = 1
MAX_SYNC_INTERVAL_HOURS: Final = 168

# Connection attempts per operation; the clock is a weak BLE peripheral.
MAX_CONNECT_ATTEMPTS: Final = 4
