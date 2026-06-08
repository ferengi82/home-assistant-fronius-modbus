"""Switch platform: enable/disable the active-power limit (SunSpec model 123)."""

from __future__ import annotations

from typing import Any

from homeassistant.components.switch import SwitchDeviceClass, SwitchEntity
from homeassistant.config_entries import ConfigEntry
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
    """Set up the power-limit enable switch when control is enabled."""
    coordinator: FroniusModbusCoordinator = entry.runtime_data
    enabled = entry.options.get(
        CONF_ENABLE_CONTROL, entry.data.get(CONF_ENABLE_CONTROL, DEFAULT_ENABLE_CONTROL)
    )
    if not enabled or not coordinator.has_controls:
        return

    serial = coordinator.device_info_data.serial if coordinator.device_info_data else None
    unique_id_base = serial or entry.entry_id
    async_add_entities([FroniusPowerLimitSwitch(coordinator, unique_id_base)])


class FroniusPowerLimitSwitch(FroniusModbusEntity, SwitchEntity):
    """Enable or disable the active-power limit (WMaxLim_Ena)."""

    _attr_translation_key = "power_limit_enabled"
    _attr_device_class = SwitchDeviceClass.SWITCH

    def __init__(
        self, coordinator: FroniusModbusCoordinator, unique_id_base: str
    ) -> None:
        """Initialise the entity."""
        super().__init__(coordinator, unique_id_base)
        self._attr_unique_id = f"{unique_id_base}_power_limit_enabled"

    @property
    def is_on(self) -> bool | None:
        """Return whether the active-power limit is currently enabled."""
        value = self.coordinator.data.get("power_limit_enabled")
        return bool(value) if value is not None else None

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Enable the active-power limit."""
        await self._set(True)

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Disable the active-power limit."""
        await self._set(False)

    async def _set(self, enabled: bool) -> None:
        try:
            await self.coordinator.async_set_power_limit_enabled(enabled)
        except FroniusModbusError as err:
            raise HomeAssistantError(str(err)) from err
