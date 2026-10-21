"""Time platform: night mode window."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import time

from homeassistant.components.time import TimeEntity, TimeEntityDescription
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.util import dt as dt_util

from . import protocol
from .client import NixieClockState
from .coordinator import NixieClockConfigEntry, NixieClockCoordinator
from .entity import NixieClockEntity

PARALLEL_UPDATES = 1


@dataclass(frozen=True, kw_only=True)
class NixieClockTimeDescription(TimeEntityDescription):
    characteristic: str
    raw_fn: Callable[[NixieClockState], int | None]


TIMES: tuple[NixieClockTimeDescription, ...] = (
    NixieClockTimeDescription(
        key="night_mode_start",
        entity_category=EntityCategory.CONFIG,
        characteristic=protocol.CHAR_NIGHT_MODE_START,
        raw_fn=lambda s: s.night_mode_start_raw,
    ),
    NixieClockTimeDescription(
        key="night_mode_end",
        entity_category=EntityCategory.CONFIG,
        characteristic=protocol.CHAR_NIGHT_MODE_END,
        raw_fn=lambda s: s.night_mode_end_raw,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: NixieClockConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    coordinator = entry.runtime_data
    async_add_entities(
        NixieClockTime(coordinator, description)
        for description in TIMES
        if coordinator.data is None or description.raw_fn(coordinator.data) is not None
    )


class NixieClockTime(NixieClockEntity, TimeEntity):
    """Night-mode boundary.

    The app stores a full local-epoch timestamp (picked date + time). We assume the
    firmware only uses the time of day (value mod 86400); the raw value is exposed as
    an attribute so this assumption can be verified on the device.
    """

    entity_description: NixieClockTimeDescription

    def __init__(
        self, coordinator: NixieClockCoordinator, description: NixieClockTimeDescription
    ) -> None:
        super().__init__(coordinator, description.key)
        self.entity_description = description

    def _raw(self) -> int | None:
        if self.coordinator.data is None:
            return None
        return self.entity_description.raw_fn(self.coordinator.data)

    @property
    def native_value(self) -> time | None:
        raw = self._raw()
        return None if raw is None else protocol.time_of_day(raw)

    @property
    def extra_state_attributes(self) -> dict[str, int | None]:
        return {"raw_value": self._raw()}

    async def async_set_value(self, value: time) -> None:
        encoded = protocol.night_mode_value(value, dt_util.now().date())
        await self.coordinator.async_write(
            self.entity_description.characteristic, protocol.encode_u32(encoded)
        )
