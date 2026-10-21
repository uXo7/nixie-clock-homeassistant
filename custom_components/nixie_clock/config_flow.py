"""Config flow for the Nixie Clock integration."""

from __future__ import annotations

from typing import Any

import voluptuous as vol

from homeassistant.components.bluetooth import (
    BluetoothServiceInfoBleak,
    async_discovered_service_info,
)
from homeassistant.config_entries import (
    ConfigEntry,
    ConfigFlow,
    ConfigFlowResult,
    OptionsFlowWithReload,
)
from homeassistant.const import CONF_ADDRESS
from homeassistant.core import callback
from homeassistant.helpers.selector import NumberSelector, NumberSelectorConfig, NumberSelectorMode

from .const import (
    CONF_SYNC_INTERVAL,
    DEFAULT_SYNC_INTERVAL_HOURS,
    DEVICE_NAME_PREFIX,
    DOMAIN,
    MAX_SYNC_INTERVAL_HOURS,
    MIN_SYNC_INTERVAL_HOURS,
)


def _is_nixie_clock(info: BluetoothServiceInfoBleak) -> bool:
    return (info.name or "").startswith(DEVICE_NAME_PREFIX)


class NixieClockConfigFlow(ConfigFlow, domain=DOMAIN):
    """Bluetooth discovery + manual pick from discovered devices."""

    VERSION = 1

    def __init__(self) -> None:
        self._discovery: BluetoothServiceInfoBleak | None = None
        self._candidates: dict[str, str] = {}

    async def async_step_bluetooth(
        self, discovery_info: BluetoothServiceInfoBleak
    ) -> ConfigFlowResult:
        await self.async_set_unique_id(discovery_info.address)
        self._abort_if_unique_id_configured()
        if not _is_nixie_clock(discovery_info):
            return self.async_abort(reason="not_supported")
        self._discovery = discovery_info
        self.context["title_placeholders"] = {
            "name": discovery_info.name,
            "address": discovery_info.address,
        }
        return await self.async_step_bluetooth_confirm()

    async def async_step_bluetooth_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        assert self._discovery is not None
        if user_input is not None:
            return self.async_create_entry(
                title=self._discovery.name or DEVICE_NAME_PREFIX,
                data={CONF_ADDRESS: self._discovery.address},
            )
        self._set_confirm_only()
        return self.async_show_form(
            step_id="bluetooth_confirm",
            description_placeholders={
                "name": self._discovery.name,
                "address": self._discovery.address,
                "rssi": str(self._discovery.rssi),
            },
        )

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        if user_input is not None:
            address = user_input[CONF_ADDRESS]
            await self.async_set_unique_id(address, raise_on_progress=False)
            self._abort_if_unique_id_configured()
            return self.async_create_entry(title=DEVICE_NAME_PREFIX, data={CONF_ADDRESS: address})

        configured = self._async_current_ids(include_ignore=False)
        for info in async_discovered_service_info(self.hass, connectable=True):
            if info.address in configured or not _is_nixie_clock(info):
                continue
            self._candidates[info.address] = f"{info.name} ({info.address}, {info.rssi} dBm)"

        if not self._candidates:
            return self.async_abort(reason="no_devices_found")

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema({vol.Required(CONF_ADDRESS): vol.In(self._candidates)}),
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> NixieClockOptionsFlow:
        return NixieClockOptionsFlow()


class NixieClockOptionsFlow(OptionsFlowWithReload):
    """Sync interval."""

    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        if user_input is not None:
            return self.async_create_entry(
                data={CONF_SYNC_INTERVAL: int(user_input[CONF_SYNC_INTERVAL])}
            )
        schema = vol.Schema(
            {
                vol.Required(
                    CONF_SYNC_INTERVAL, default=DEFAULT_SYNC_INTERVAL_HOURS
                ): NumberSelector(
                    NumberSelectorConfig(
                        min=MIN_SYNC_INTERVAL_HOURS,
                        max=MAX_SYNC_INTERVAL_HOURS,
                        step=1,
                        mode=NumberSelectorMode.BOX,
                        unit_of_measurement="h",
                    )
                )
            }
        )
        return self.async_show_form(
            step_id="init",
            data_schema=self.add_suggested_values_to_schema(schema, self.config_entry.options),
        )
