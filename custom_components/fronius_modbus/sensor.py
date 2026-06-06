"""Sensor platform for the Fronius Symo Modbus integration."""

from __future__ import annotations

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity, SensorEntityDescription
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .coordinator import FroniusModbusCoordinator
from .entity import FroniusModbusEntity
from .models import ALL_SENSORS
from .sunspec import OPERATING_STATES


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Fronius Modbus sensors from a config entry."""
    coordinator: FroniusModbusCoordinator = entry.runtime_data
    serial = coordinator.device_info_data.serial if coordinator.device_info_data else None
    unique_id_base = serial or entry.entry_id

    entities = [
        FroniusModbusSensor(coordinator, description, unique_id_base)
        for description in ALL_SENSORS
        # Only create entities for data points the device actually reports.
        if description.key in coordinator.data
    ]
    async_add_entities(entities)


class FroniusModbusSensor(FroniusModbusEntity, SensorEntity):
    """A single SunSpec-derived sensor."""

    def __init__(
        self,
        coordinator: FroniusModbusCoordinator,
        description: SensorEntityDescription,
        unique_id_base: str,
    ) -> None:
        """Initialise the sensor."""
        super().__init__(coordinator, unique_id_base)
        self.entity_description = description
        self._attr_unique_id = f"{unique_id_base}_{description.key}"

    @property
    def available(self) -> bool:
        """Return True if the coordinator has a value for this key."""
        return (
            super().available
            and self.coordinator.data is not None
            and self.coordinator.data.get(self.entity_description.key) is not None
        )

    @property
    def native_value(self) -> int | float | str | None:
        """Return the current value, mapping the operating state to text."""
        value = self.coordinator.data.get(self.entity_description.key)
        if value is None:
            return None
        if self.entity_description.device_class == SensorDeviceClass.ENUM:
            return OPERATING_STATES.get(int(value), "unknown")
        return value
