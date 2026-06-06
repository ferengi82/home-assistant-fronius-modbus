"""Diagnostics support for the Fronius Symo Modbus integration."""

from __future__ import annotations

from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .coordinator import FroniusModbusCoordinator

TO_REDACT = {"host"}


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: ConfigEntry
) -> dict[str, Any]:
    """Return diagnostics for a config entry."""
    coordinator: FroniusModbusCoordinator = entry.runtime_data
    info = coordinator.device_info_data
    return {
        "entry_data": {k: v for k, v in entry.data.items() if k not in TO_REDACT},
        "options": dict(entry.options),
        "device": {
            "manufacturer": info.manufacturer if info else None,
            "model": info.model if info else None,
            "version": info.version if info else None,
            # Serial intentionally omitted from diagnostics.
        },
        "inverter_model_id": coordinator.inverter_model_id,
        "discovered_models": sorted(coordinator.models),
        "data": coordinator.data,
    }
