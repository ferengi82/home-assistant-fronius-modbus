"""Base entity for the Fronius Symo Modbus integration."""

from __future__ import annotations

from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import FroniusModbusCoordinator


class FroniusModbusEntity(CoordinatorEntity[FroniusModbusCoordinator]):
    """Common base providing device info for all Fronius entities."""

    _attr_has_entity_name = True

    def __init__(self, coordinator: FroniusModbusCoordinator, unique_id_base: str) -> None:
        """Initialise the entity."""
        super().__init__(coordinator)
        self._unique_id_base = unique_id_base

    @property
    def device_info(self) -> DeviceInfo:
        """Return device information for the inverter."""
        info = self.coordinator.device_info_data
        identifier = self._unique_id_base
        return DeviceInfo(
            identifiers={(DOMAIN, identifier)},
            manufacturer=info.manufacturer if info else "Fronius",
            model=info.model if info else "Symo",
            name=info.model if info and info.model else "Fronius Symo",
            serial_number=info.serial if info else None,
            sw_version=info.version if info else None,
        )
