"""Switch platform: night mode, nixie dots."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from homeassistant.components.switch import SwitchEntity, SwitchEntityDescription
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import protocol
from .client import NixieClockState
from .coordinator import NixieClockConfigEntry, NixieClockCoordinator
from .entity import NixieClockEntity

PARALLEL_UPDATES = 1


@dataclass(frozen=True, kw_only=True)
class NixieClockSwitchDescription(SwitchEntityDescription):
    characteristic: str
    value_fn: Callable[[NixieClockState], bool | None]


SWITCHES: tuple[NixieClockSwitchDescription, ...] = (
    NixieClockSwitchDescription(
        key="night_mode",
        entity_category=EntityCategory.CONFIG,
        characteristic=protocol.CHAR_NIGHT_MODE,
        value_fn=lambda s: s.night_mode,
    ),
    NixieClockSwitchDescription(
        key="nixie_dots",
        entity_category=EntityCategory.CONFIG,
        characteristic=protocol.CHAR_NIXIE_DOTS,
        value_fn=lambda s: s.nixie_dots,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: NixieClockConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    coordinator = entry.runtime_data
    async_add_entities(
        NixieClockSwitch(coordinator, description)
        for description in SWITCHES
        if coordinator.data is None or description.value_fn(coordinator.data) is not None
    )


class NixieClockSwitch(NixieClockEntity, SwitchEntity):
    entity_description: NixieClockSwitchDescription

    def __init__(
        self, coordinator: NixieClockCoordinator, description: NixieClockSwitchDescription
    ) -> None:
        super().__init__(coordinator, description.key)
        self.entity_description = description

    @property
    def is_on(self) -> bool | None:
        if self.coordinator.data is None:
            return None
        return self.entity_description.value_fn(self.coordinator.data)

    async def async_turn_on(self, **kwargs: Any) -> None:
        await self.coordinator.async_write(
            self.entity_description.characteristic, protocol.encode_u8(1)
        )

    async def async_turn_off(self, **kwargs: Any) -> None:
        await self.coordinator.async_write(
            self.entity_description.characteristic, protocol.encode_u8(0)
        )
