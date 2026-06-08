"""The Fronius Symo Modbus integration."""

from __future__ import annotations

import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryNotReady

from .const import (
    CONF_HOST,
    CONF_PORT,
    CONF_SCAN_INTERVAL,
    CONF_UNIT_ID,
    DEFAULT_PORT,
    DEFAULT_SCAN_INTERVAL,
    DEFAULT_UNIT_ID,
)
from .coordinator import FroniusModbusCoordinator, FroniusModbusError

_LOGGER = logging.getLogger(__name__)

PLATFORMS: list[Platform] = [Platform.SENSOR, Platform.NUMBER, Platform.SWITCH]

type FroniusConfigEntry = ConfigEntry[FroniusModbusCoordinator]


async def async_setup_entry(hass: HomeAssistant, entry: FroniusConfigEntry) -> bool:
    """Set up Fronius Symo Modbus from a config entry."""
    # Options (set via the options flow) take precedence over the original
    # setup data so host / port / unit ID / interval can be changed later.
    def opt(key: str, default):
        return entry.options.get(key, entry.data.get(key, default))

    coordinator = FroniusModbusCoordinator(
        hass,
        host=opt(CONF_HOST, entry.data[CONF_HOST]),
        port=opt(CONF_PORT, DEFAULT_PORT),
        unit_id=opt(CONF_UNIT_ID, DEFAULT_UNIT_ID),
        scan_interval=opt(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL),
        entry=entry,
    )

    try:
        await coordinator.async_discover()
    except FroniusModbusError as err:
        await coordinator.async_close()
        raise ConfigEntryNotReady(str(err)) from err

    await coordinator.async_config_entry_first_refresh()

    entry.runtime_data = coordinator
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_on_unload(entry.add_update_listener(_async_update_listener))
    return True


async def async_unload_entry(hass: HomeAssistant, entry: FroniusConfigEntry) -> bool:
    """Unload a config entry."""
    unloaded = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unloaded:
        await entry.runtime_data.async_close()
    return unloaded


async def _async_update_listener(hass: HomeAssistant, entry: FroniusConfigEntry) -> None:
    """Reload the entry when options (e.g. scan interval) change."""
    await hass.config_entries.async_reload(entry.entry_id)
