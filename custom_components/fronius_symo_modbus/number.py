"""Number platform: writable active-power limit (SunSpec model 123)."""

from __future__ import annotations

from homeassistant.components.number import NumberEntity, NumberMode
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import PERCENTAGE
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import CONF_ENABLE_CONTROL, DEFAULT_ENABLE_CONTROL
from .coordinator import FroniusModbusCoordinator, FroniusModbusError
from .entity import FroniusModbusEntity


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the power-limit number entity when control is enabled."""
    coordinator: FroniusModbusCoordinator = entry.runtime_data
    enabled = entry.options.get(
        CONF_ENABLE_CONTROL, entry.data.get(CONF_ENABLE_CONTROL, DEFAULT_ENABLE_CONTROL)
    )
    if not enabled or not coordinator.has_controls:
        return

    serial = coordinator.device_info_data.serial if coordinator.device_info_data else None
    unique_id_base = serial or entry.entry_id
    async_add_entities([FroniusPowerLimitNumber(coordinator, unique_id_base)])


class FroniusPowerLimitNumber(FroniusModbusEntity, NumberEntity):
    """Active-power output limit in percent (WMaxLimPct)."""

    _attr_translation_key = "power_limit"
    _attr_native_min_value = 0
    _attr_native_max_value = 100
    _attr_native_step = 1
    _attr_native_unit_of_measurement = PERCENTAGE
    _attr_mode = NumberMode.SLIDER

    def __init__(
        self, coordinator: FroniusModbusCoordinator, unique_id_base: str
    ) -> None:
        """Initialise the entity."""
        super().__init__(coordinator, unique_id_base)
        self._attr_unique_id = f"{unique_id_base}_power_limit"

    @property
    def native_value(self) -> float | None:
        """Return the current active-power limit percentage."""
        value = self.coordinator.data.get("power_limit_pct")
        return float(value) if isinstance(value, (int, float)) else None

    async def async_set_native_value(self, value: float) -> None:
        """Write a new active-power limit percentage to the inverter."""
        try:
            await self.coordinator.async_set_power_limit(value)
        except FroniusModbusError as err:
            raise HomeAssistantError(str(err)) from err
