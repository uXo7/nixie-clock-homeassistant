"""Sensor platform: drift and last sync (from syncs), signal strength (live)."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
import time

from homeassistant.components import bluetooth
from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.const import SIGNAL_STRENGTH_DECIBELS_MILLIWATT, EntityCategory, UnitOfTime
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .client import NixieClockState
from .const import RSSI_MIN_UPDATE_INTERVAL_S
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
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: NixieClockConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    coordinator = entry.runtime_data
    async_add_entities(
        [
            *(NixieClockSensor(coordinator, description) for description in SENSORS),
            NixieClockSignalSensor(coordinator),
        ]
    )


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


class NixieClockSignalSensor(NixieClockEntity, SensorEntity):
    """RSSI of the clock as heard by the adapter/proxy HA currently prefers.

    Fed by advertisements, not by syncs, so it shows the live link and which adapter
    a connection would use. Writes are throttled: the clock advertises several times
    per second and every write ends up in the recorder.
    """

    _attr_device_class = SensorDeviceClass.SIGNAL_STRENGTH
    _attr_native_unit_of_measurement = SIGNAL_STRENGTH_DECIBELS_MILLIWATT
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, coordinator: NixieClockCoordinator) -> None:
        super().__init__(coordinator, "signal_strength")
        self._address = coordinator.client.address
        self._seen = False
        self._last_write: float | None = None
        self._attr_extra_state_attributes = {"source": None}

    @property
    def available(self) -> bool:
        # Independent of sync success: the clock can be heard while a sync failed.
        return self._seen

    @callback
    def _handle_coordinator_update(self) -> None:
        """Ignore syncs; this sensor is driven by advertisements."""

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        if info := bluetooth.async_last_service_info(self.hass, self._address, connectable=True):
            self._apply(info)
        self.async_on_remove(
            bluetooth.async_register_callback(
                self.hass,
                self._async_advertisement,
                bluetooth.BluetoothCallbackMatcher(address=self._address, connectable=True),
                bluetooth.BluetoothScanningMode.PASSIVE,
            )
        )
        self.async_on_remove(
            bluetooth.async_track_unavailable(
                self.hass, self._async_unavailable, self._address, connectable=True
            )
        )

    def _source_name(self, source: str) -> str:
        scanner = bluetooth.async_scanner_by_source(self.hass, source)
        return scanner.name if scanner else source

    def _apply(self, info: bluetooth.BluetoothServiceInfoBleak) -> None:
        self._seen = True
        self._attr_native_value = info.rssi
        self._attr_extra_state_attributes = {"source": self._source_name(info.source)}

    @callback
    def _async_advertisement(
        self,
        info: bluetooth.BluetoothServiceInfoBleak,
        change: bluetooth.BluetoothChange,
    ) -> None:
        now = time.monotonic()
        source_changed = (
            self._source_name(info.source) != self._attr_extra_state_attributes["source"]
        )
        if self._seen and not source_changed:
            if info.rssi == self._attr_native_value:
                return
            if self._last_write is not None and now - self._last_write < RSSI_MIN_UPDATE_INTERVAL_S:
                return
        self._apply(info)
        self._last_write = now
        self.async_write_ha_state()

    @callback
    def _async_unavailable(self, info: bluetooth.BluetoothServiceInfoBleak) -> None:
        self._seen = False
        self.async_write_ha_state()
