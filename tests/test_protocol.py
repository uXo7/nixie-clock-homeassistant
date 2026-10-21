"""Protocol helper tests (no HA needed)."""

from datetime import date, time

import pytest

from custom_components.nixie_clock import protocol


def test_u32_roundtrip_little_endian() -> None:
    assert protocol.encode_u32(0x12345678) == b"\x78\x56\x34\x12"
    assert protocol.decode_u32(b"\x78\x56\x34\x12") == 0x12345678
    with pytest.raises(ValueError):
        protocol.decode_u32(b"\x01\x02")


def test_u8_bounds() -> None:
    assert protocol.encode_u8(4) == b"\x04"
    with pytest.raises(ValueError):
        protocol.encode_u8(256)


def test_local_epoch_matches_app() -> None:
    # App: (millisecondsSinceEpoch + timeZoneOffset) / 1000
    assert protocol.to_local_epoch(1_792_600_000, 7200) == 1_792_607_200


def test_night_mode_value_and_time_of_day_roundtrip() -> None:
    raw = protocol.night_mode_value(time(23, 30), date(2026, 10, 21))
    assert raw == 1_792_625_400
    assert protocol.time_of_day(raw) == time(23, 30)


def test_parse_firmware() -> None:
    assert protocol.parse_firmware(b"Nixie Clock 1.17") == "1.17"
    assert protocol.parse_firmware(b"FW 1.2.3\x00") == "1.2.3"
    assert protocol.parse_firmware(b"weird") == "weird"


def test_dfu_characteristic_never_writable() -> None:
    assert not any("14ff" in uuid for uuid in protocol.WRITABLE_CHARACTERISTICS)
    assert not any(
        "14ff" in str(v).lower() for k, v in vars(protocol).items() if not k.startswith("_")
    )
