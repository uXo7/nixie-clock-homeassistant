"""Fixtures for Nixie Clock tests."""

from __future__ import annotations

from collections.abc import Generator
from unittest.mock import MagicMock, patch

import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.nixie_clock.client import NixieClockState
from custom_components.nixie_clock.const import DOMAIN
from homeassistant.const import CONF_ADDRESS
from homeassistant.core import HomeAssistant

ADDRESS = "CD:A7:3E:99:D9:13"


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations: None) -> None:
    """Allow loading custom_components."""


@pytest.fixture(autouse=True)
def fake_bluetooth_stack(hass: HomeAssistant) -> Generator[MagicMock]:
    """Pretend the bluetooth integrations are loaded and the clock is in range."""
    hass.config.components.update({"bluetooth", "bluetooth_adapters"})
    ble_device = MagicMock(name="BLEDevice", address=ADDRESS)
    ble_device.name = "Nixie Clock"
    with (
        patch(
            "custom_components.nixie_clock.bluetooth.async_ble_device_from_address",
            return_value=ble_device,
        ),
        patch(
            "custom_components.nixie_clock.client.bluetooth.async_ble_device_from_address",
            return_value=ble_device,
        ),
        patch(
            "custom_components.nixie_clock.client.bluetooth.async_last_service_info",
            return_value=MagicMock(rssi=-82),
        ),
    ):
        yield ble_device


@pytest.fixture
def clock_state() -> NixieClockState:
    from datetime import UTC, datetime

    return NixieClockState(
        firmware="1.17",
        time_format=0,
        hourglass=2,
        night_mode=True,
        # 2026-10-21 23:30:00 / 06:15:00 as local epoch
        night_mode_start_raw=1792625400,
        night_mode_end_raw=1792563300,
        nixie_dots=False,
        rssi=-82,
        drift_s=-37.5,
        last_sync=datetime(2026, 10, 21, 18, 0, tzinfo=UTC),
        synced_utc_offset_s=7200,
    )


@pytest.fixture
def config_entry() -> MockConfigEntry:
    return MockConfigEntry(
        domain=DOMAIN, title="Nixie Clock", unique_id=ADDRESS, data={CONF_ADDRESS: ADDRESS}
    )
