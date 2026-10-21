"""Config and options flow."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from custom_components.nixie_clock.const import CONF_SYNC_INTERVAL, DOMAIN
from homeassistant.config_entries import SOURCE_BLUETOOTH, SOURCE_USER
from homeassistant.const import CONF_ADDRESS
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType

from .conftest import ADDRESS


def _info(name: str = "Nixie Clock", address: str = ADDRESS) -> MagicMock:
    info = MagicMock(address=address, rssi=-82)
    info.name = name
    return info


async def test_bluetooth_discovery(hass: HomeAssistant) -> None:
    with patch("custom_components.nixie_clock.async_setup_entry", return_value=True):
        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": SOURCE_BLUETOOTH}, data=_info()
        )
        assert result["type"] is FlowResultType.FORM
        assert result["step_id"] == "bluetooth_confirm"
        result = await hass.config_entries.flow.async_configure(result["flow_id"], {})
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["data"] == {CONF_ADDRESS: ADDRESS}
    assert result["result"].unique_id == ADDRESS


async def test_user_flow_lists_only_clocks(hass: HomeAssistant) -> None:
    with (
        patch(
            "custom_components.nixie_clock.config_flow.async_discovered_service_info",
            return_value=[_info(), _info("TNT_BW", "04:C4:61:86:7A:A8")],
        ),
        patch("custom_components.nixie_clock.async_setup_entry", return_value=True),
    ):
        result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": SOURCE_USER})
        assert result["type"] is FlowResultType.FORM
        schema_keys = result["data_schema"].schema[CONF_ADDRESS].container
        assert list(schema_keys) == [ADDRESS]
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {CONF_ADDRESS: ADDRESS}
        )
    assert result["type"] is FlowResultType.CREATE_ENTRY


async def test_user_flow_no_devices(hass: HomeAssistant) -> None:
    with patch(
        "custom_components.nixie_clock.config_flow.async_discovered_service_info",
        return_value=[],
    ):
        result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": SOURCE_USER})
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "no_devices_found"


async def test_options_flow(hass: HomeAssistant, config_entry) -> None:
    config_entry.add_to_hass(hass)
    with patch("custom_components.nixie_clock.async_setup_entry", return_value=True):
        result = await hass.config_entries.options.async_init(config_entry.entry_id)
        result = await hass.config_entries.options.async_configure(
            result["flow_id"], {CONF_SYNC_INTERVAL: 6.0}
        )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert config_entry.options == {CONF_SYNC_INTERVAL: 6}
