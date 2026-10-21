"""Select platform: hourglass interval, time format."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from homeassistant.components.select import SelectEntity, SelectEntityDescription
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import protocol
from .client import NixieClockState
from .coordinator import NixieClockConfigEntry, NixieClockCoordinator
from .entity import NixieClockEntity

PARALLEL_UPDATES = 1


@dataclass(frozen=True, kw_only=True)
class NixieClockSelectDescription(SelectEntityDescription):
    characteristic: str
    value_fn: Callable[[NixieClockState], int | None]


SELECTS: tuple[NixieClockSelectDescription, ...] = (
    NixieClockSelectDescription(
        key="hourglass",
        entity_category=EntityCategory.CONFIG,
        options=list(protocol.HOURGLASS_OPTIONS),
        characteristic=protocol.CHAR_HOURGLASS,
        value_fn=lambda s: s.hourglass,
    ),
    NixieClockSelectDescription(
        key="time_format",
        entity_category=EntityCategory.CONFIG,
        options=list(protocol.TIME_FORMAT_OPTIONS),
        characteristic=protocol.CHAR_TIME_FORMAT,
        value_fn=lambda s: s.time_format,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: NixieClockConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    coordinator = entry.runtime_data
    async_add_entities(
        NixieClockSelect(coordinator, description)
        for description in SELECTS
        if coordinator.data is None or description.value_fn(coordinator.data) is not None
    )


class NixieClockSelect(NixieClockEntity, SelectEntity):
    entity_description: NixieClockSelectDescription

    def __init__(
        self, coordinator: NixieClockCoordinator, description: NixieClockSelectDescription
    ) -> None:
        super().__init__(coordinator, description.key)
        self.entity_description = description

    @property
    def current_option(self) -> str | None:
        if self.coordinator.data is None:
            return None
        index = self.entity_description.value_fn(self.coordinator.data)
        options = self.entity_description.options or []
        if index is None or not 0 <= index < len(options):
            return None
        return options[index]

    async def async_select_option(self, option: str) -> None:
        index = (self.entity_description.options or []).index(option)
        await self.coordinator.async_write(
            self.entity_description.characteristic, protocol.encode_u8(index)
        )
