"""Diagnostics: raw values for protocol verification."""

from __future__ import annotations

from dataclasses import asdict
from typing import Any

from homeassistant.core import HomeAssistant

from .coordinator import NixieClockConfigEntry


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: NixieClockConfigEntry
) -> dict[str, Any]:
    coordinator = entry.runtime_data
    data = coordinator.data
    return {
        "options": dict(entry.options),
        "last_update_success": coordinator.last_update_success,
        "last_exception": repr(coordinator.last_exception),
        "state": {
            **(asdict(data) if data else {}),
            "last_sync": data.last_sync.isoformat() if data and data.last_sync else None,
        },
    }
