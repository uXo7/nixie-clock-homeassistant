"""Sensor platform: drift, last sync, signal strength."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.const import SIGNAL_STRENGTH_DECIBELS_MILLIWATT, EntityCategory, UnitOfTime
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .client import NixieClockState
from .coordinator import NixieClockConfigEntry, NixieClockCoordinator
from .entity import NixieClockEntity

PARALLEL_UPDATES = 0


@dataclass(frozen=True, kw_only=True)
class NixieClockSensorDescription(SensorEntityDescription):
    value_fn: Callable[[NixieClockState], float | int | datetime | None]


SENSORS: tuple[NixieClockSensorDescription, ...] = (
    NixieClockSensorDescription(
        # Positive = clock was ahead. Measured right before each sync.
        key="drift",
        native_unit_of_measurement=UnitOfTime.SECONDS,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=1,
        value_fn=lambda s: s.drift_s,
    ),
    NixieClockSensorDescription(
        key="last_sync",
        device_class=SensorDeviceClass.TIMESTAMP,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda s: s.last_sync,
    ),
    NixieClockSensorDescription(
        key="signal_strength",
        device_class=SensorDeviceClass.SIGNAL_STRENGTH,
        native_unit_of_measurement=SIGNAL_STRENGTH_DECIBELS_MILLIWATT,
        state_class=SensorStateClass.MEASUREMENT,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda s: s.rssi,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: NixieClockConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    async_add_entities(NixieClockSensor(entry.runtime_data, description) for description in SENSORS)


class NixieClockSensor(NixieClockEntity, SensorEntity):
    entity_description: NixieClockSensorDescription

    def __init__(
        self, coordinator: NixieClockCoordinator, description: NixieClockSensorDescription
    ) -> None:
        super().__init__(coordinator, description.key)
        self.entity_description = description

    @property
    def native_value(self) -> float | int | datetime | None:
        if self.coordinator.data is None:
            return None
        return self.entity_description.value_fn(self.coordinator.data)
