"""Setup, entities, writes and resync logic."""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch
from zoneinfo import ZoneInfo

from freezegun.api import FrozenDateTimeFactory
import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry, async_fire_time_changed

from custom_components.nixie_clock import protocol
from custom_components.nixie_clock.client import NixieClockState
from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr, entity_registry as er

from .conftest import ADDRESS

SYNC = "custom_components.nixie_clock.client.NixieClockClient.async_read_and_sync"
WRITE = "custom_components.nixie_clock.client.NixieClockClient.async_write"


async def _setup(hass: HomeAssistant, entry: MockConfigEntry, state: NixieClockState) -> AsyncMock:
    await hass.config.async_set_time_zone("Europe/Bratislava")
    entry.add_to_hass(hass)
    sync = AsyncMock(return_value=state)
    with patch(SYNC, sync):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()
    return sync


def _eid(hass: HomeAssistant, domain: str, key: str) -> str:
    entity_id = er.async_get(hass).async_get_entity_id(domain, "nixie_clock", f"{ADDRESS}_{key}")
    assert entity_id
    return entity_id


async def test_setup_creates_entities(
    hass: HomeAssistant, config_entry: MockConfigEntry, clock_state: NixieClockState
) -> None:
    sync = await _setup(hass, config_entry, clock_state)
    assert config_entry.state is ConfigEntryState.LOADED
    assert sync.await_count == 1  # first refresh syncs immediately

    assert hass.states.get(_eid(hass, "sensor", "drift")).state == "-37.5"
    assert hass.states.get(_eid(hass, "sensor", "signal_strength")).state == "-82"
    assert hass.states.get(_eid(hass, "select", "hourglass")).state == "30_min"
    assert hass.states.get(_eid(hass, "select", "time_format")).state == "24h"
    assert hass.states.get(_eid(hass, "switch", "night_mode")).state == "on"
    assert hass.states.get(_eid(hass, "switch", "nixie_dots")).state == "off"
    start = hass.states.get(_eid(hass, "time", "night_mode_start"))
    assert start.state == "23:30:00"
    assert start.attributes["raw_value"] == 1792625400
    assert hass.states.get(_eid(hass, "time", "night_mode_end")).state == "06:15:00"


async def test_unreachable_clock_does_not_block_setup(
    hass: HomeAssistant,
    config_entry: MockConfigEntry,
    clock_state: NixieClockState,
    fake_bluetooth_stack: MagicMock,
) -> None:
    from custom_components.nixie_clock.client import NixieClockNotFoundError

    await hass.config.async_set_time_zone("Europe/Bratislava")
    config_entry.add_to_hass(hass)
    with patch(SYNC, AsyncMock(side_effect=NixieClockNotFoundError("silent"))):
        assert await hass.config_entries.async_setup(config_entry.entry_id)
        await hass.async_block_till_done()
    assert config_entry.state is ConfigEntryState.LOADED
    assert hass.states.get(_eid(hass, "sensor", "drift")).state == "unavailable"
    assert hass.states.get(_eid(hass, "switch", "night_mode")).state == "unavailable"
    assert hass.states.get(_eid(hass, "button", "sync_time")).state != "unavailable"

    # The clock advertises again -> immediate sync (setup armed a cooldown, so skip it).
    coordinator = config_entry.runtime_data
    coordinator._last_advertisement_retry = 0.0
    seen = fake_bluetooth_stack.register_callback.call_args.args[1]
    sync = AsyncMock(return_value=clock_state)
    with patch(SYNC, sync):
        seen(MagicMock(rssi=-80), None)
        await hass.async_block_till_done()
        assert sync.await_count == 1
        assert hass.states.get(_eid(hass, "sensor", "drift")).state == "-37.5"
        # Healthy now -> further advertisements are ignored.
        coordinator._last_advertisement_retry = 0.0
        seen(MagicMock(rssi=-80), None)
        await hass.async_block_till_done()
        assert sync.await_count == 1

    device = dr.async_get(hass).async_get_device(connections={("bluetooth", ADDRESS)})
    assert device.sw_version == "1.17"


async def test_partial_read_keeps_previous_settings(
    hass: HomeAssistant, config_entry: MockConfigEntry, clock_state: NixieClockState
) -> None:
    await _setup(hass, config_entry, clock_state)
    partial = NixieClockState(drift_s=1.5, synced_utc_offset_s=7200, settings_valid=False)
    with patch(SYNC, AsyncMock(return_value=partial)):
        await config_entry.runtime_data.async_refresh()
    assert hass.states.get(_eid(hass, "sensor", "drift")).state == "1.5"
    assert hass.states.get(_eid(hass, "select", "hourglass")).state == "30_min"
    assert hass.states.get(_eid(hass, "switch", "night_mode")).state == "on"


@pytest.mark.parametrize(
    ("domain", "service", "key", "data", "uuid", "payload"),
    [
        (
            "select",
            "select_option",
            "hourglass",
            {"option": "3_am"},
            protocol.CHAR_HOURGLASS,
            b"\x04",
        ),
        (
            "select",
            "select_option",
            "time_format",
            {"option": "12h"},
            protocol.CHAR_TIME_FORMAT,
            b"\x01",
        ),
        ("switch", "turn_on", "nixie_dots", {}, protocol.CHAR_NIXIE_DOTS, b"\x01"),
        ("switch", "turn_off", "night_mode", {}, protocol.CHAR_NIGHT_MODE, b"\x00"),
        (
            "time",
            "set_value",
            "night_mode_start",
            {"time": "22:00:00"},
            protocol.CHAR_NIGHT_MODE_START,
            None,
        ),
    ],
)
async def test_writes(
    hass: HomeAssistant,
    config_entry: MockConfigEntry,
    clock_state: NixieClockState,
    domain: str,
    service: str,
    key: str,
    data: dict,
    uuid: str,
    payload: bytes | None,
) -> None:
    await _setup(hass, config_entry, clock_state)
    readback = replace(clock_state, drift_s=None, last_sync=None, synced_utc_offset_s=None)
    write = AsyncMock(return_value=readback)
    with patch(WRITE, write):
        await hass.services.async_call(
            domain, service, {"entity_id": _eid(hass, domain, key), **data}, blocking=True
        )
    write.assert_awaited_once()
    assert write.await_args.args[0] == uuid
    if payload is not None:
        assert write.await_args.args[1] == payload
    else:
        assert protocol.time_of_day(protocol.decode_u32(write.await_args.args[1])).hour == 22
    # Sync statistics survive a settings write.
    assert hass.states.get(_eid(hass, "sensor", "drift")).state == "-37.5"


async def test_button_triggers_sync(
    hass: HomeAssistant, config_entry: MockConfigEntry, clock_state: NixieClockState
) -> None:
    await _setup(hass, config_entry, clock_state)
    sync = AsyncMock(return_value=replace(clock_state, drift_s=0.2))
    with patch(SYNC, sync):
        await hass.services.async_call(
            "button", "press", {"entity_id": _eid(hass, "button", "sync_time")}, blocking=True
        )
    assert sync.await_count == 1
    assert hass.states.get(_eid(hass, "sensor", "drift")).state == "0.2"


async def test_hourly_resync_on_dst_change(
    hass: HomeAssistant,
    config_entry: MockConfigEntry,
    clock_state: NixieClockState,
    freezer: FrozenDateTimeFactory,
) -> None:
    tz = ZoneInfo("Europe/Bratislava")
    freezer.move_to(datetime(2026, 10, 25, 1, 30, tzinfo=tz))  # CEST, offset 7200
    await _setup(hass, config_entry, clock_state)

    sync = AsyncMock(return_value=replace(clock_state, synced_utc_offset_s=3600))
    with patch(SYNC, sync):
        # 02:00 CEST -> nothing changed yet (still offset 7200 at 02:00:05 CEST)
        freezer.move_to(datetime(2026, 10, 25, 2, 0, 5, fold=0, tzinfo=tz))
        async_fire_time_changed(hass)
        await hass.async_block_till_done()
        assert sync.await_count == 0
        # 03:00 CEST becomes 02:00 CET: next top of the hour sees offset 3600
        freezer.move_to(datetime(2026, 10, 25, 2, 0, 5, fold=1, tzinfo=tz))
        async_fire_time_changed(hass)
        await hass.async_block_till_done()
        assert sync.await_count == 1
        # Offset now matches -> no further resyncs
        freezer.move_to(datetime(2026, 10, 25, 3, 0, 5, tzinfo=tz))
        async_fire_time_changed(hass)
        await hass.async_block_till_done()
        assert sync.await_count == 1


async def test_hourly_retry_after_failure(
    hass: HomeAssistant,
    config_entry: MockConfigEntry,
    clock_state: NixieClockState,
    freezer: FrozenDateTimeFactory,
) -> None:
    from custom_components.nixie_clock.client import NixieClockError

    tz = ZoneInfo("Europe/Bratislava")
    freezer.move_to(datetime(2026, 10, 21, 18, 30, tzinfo=tz))
    await _setup(hass, config_entry, clock_state)
    coordinator = config_entry.runtime_data

    with patch(SYNC, AsyncMock(side_effect=NixieClockError("out of range"))):
        await coordinator.async_refresh()
    assert not coordinator.last_update_success
    assert hass.states.get(_eid(hass, "sensor", "drift")).state == "unavailable"
    assert hass.states.get(_eid(hass, "button", "sync_time")).state != "unavailable"

    sync = AsyncMock(return_value=clock_state)
    with patch(SYNC, sync):
        freezer.move_to(datetime(2026, 10, 21, 19, 0, 5, tzinfo=tz))
        async_fire_time_changed(hass)
        await hass.async_block_till_done()
    assert sync.await_count == 1
    assert coordinator.last_update_success
