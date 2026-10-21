"""BLE client: sync encoding, drift and the write guard."""

from __future__ import annotations

from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch
from zoneinfo import ZoneInfo

from freezegun.api import FrozenDateTimeFactory
import pytest

from custom_components.nixie_clock import protocol
from custom_components.nixie_clock.client import NixieClockClient, NixieClockError
from homeassistant.core import HomeAssistant

from .conftest import ADDRESS


def _fake_client(values: dict[str, bytes]) -> MagicMock:
    client = MagicMock()
    client.services.get_characteristic.side_effect = lambda uuid: uuid if uuid in values else None
    client.read_gatt_char = AsyncMock(side_effect=lambda uuid: bytearray(values[uuid]))
    client.write_gatt_char = AsyncMock()
    client.disconnect = AsyncMock()
    return client


async def test_sync_writes_local_epoch_and_measures_drift(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory
) -> None:
    await hass.config.async_set_time_zone("Europe/Bratislava")
    now = datetime(2026, 10, 21, 19, 45, 10, tzinfo=ZoneInfo("Europe/Bratislava"))
    freezer.move_to(now)
    local_now = int(now.timestamp()) + 7200
    fake = _fake_client(
        {
            protocol.CHAR_FIRMWARE_REVISION: b"Nixie Clock 1.17",
            protocol.CHAR_DATETIME: protocol.encode_u32(local_now - 42),  # clock 42 s late
            protocol.CHAR_TIME_FORMAT: b"\x00",
            protocol.CHAR_HOURGLASS: b"\x01",
            protocol.CHAR_NIGHT_MODE: b"\x00",
            protocol.CHAR_NIGHT_MODE_START: protocol.encode_u32(0),
            protocol.CHAR_NIGHT_MODE_END: protocol.encode_u32(0),
            protocol.CHAR_NIXIE_DOTS: b"\x01",
        }
    )
    with (
        patch(
            "custom_components.nixie_clock.client.establish_connection",
            AsyncMock(return_value=fake),
        ),
        patch("custom_components.nixie_clock.client.asyncio.sleep", AsyncMock()),
    ):
        state = await NixieClockClient(hass, ADDRESS).async_read_and_sync()

    assert state.firmware == "1.17"
    assert state.drift_s == pytest.approx(-41.5, abs=0.1)
    assert state.synced_utc_offset_s == 7200
    uuid, payload = fake.write_gatt_char.await_args.args
    assert uuid == protocol.CHAR_DATETIME
    assert protocol.decode_u32(payload) == local_now + 1  # aligned to next full second
    fake.disconnect.assert_awaited_once()


async def test_write_guard_rejects_unknown_characteristic(hass: HomeAssistant) -> None:
    with pytest.raises(ValueError):
        await NixieClockClient(hass, ADDRESS).async_write(
            "a8ed14ff-130a-4d4b-acba-5de7e77e9b47", b"\x99"
        )


async def test_gatt_error_is_wrapped(hass: HomeAssistant) -> None:
    from bleak.exc import BleakError

    fake = _fake_client({protocol.CHAR_DATETIME: b"\x00\x00\x00\x00"})
    fake.read_gatt_char.side_effect = BleakError("gone")
    with (
        patch(
            "custom_components.nixie_clock.client.establish_connection",
            AsyncMock(return_value=fake),
        ),
        pytest.raises(NixieClockError),
    ):
        await NixieClockClient(hass, ADDRESS).async_read_and_sync()
    fake.disconnect.assert_awaited_once()
