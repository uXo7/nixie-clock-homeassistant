"""Button platform: manual time sync."""

from __future__ import annotations

from homeassistant.components.button import ButtonEntity
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .const import DOMAIN
from .coordinator import NixieClockConfigEntry
from .entity import NixieClockEntity

PARALLEL_UPDATES = 1


async def async_setup_entry(
    hass: HomeAssistant,
    entry: NixieClockConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    async_add_entities([NixieClockSyncButton(entry.runtime_data, "sync_time")])


class NixieClockSyncButton(NixieClockEntity, ButtonEntity):
    """Read the clock, record drift and set it to HA's time."""

    @property
    def available(self) -> bool:
        # Must stay pressable after a failed sync, otherwise it could never recover it.
        return True

    async def async_press(self) -> None:
        await self.coordinator.async_refresh()
        if not self.coordinator.last_update_success:
            raise HomeAssistantError(
                translation_domain=DOMAIN,
                translation_key="sync_failed",
                translation_placeholders={"error": str(self.coordinator.last_exception)},
            )
