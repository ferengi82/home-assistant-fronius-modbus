"""Config flow for the Fronius Symo Modbus integration."""

from __future__ import annotations

from typing import Any

import voluptuous as vol

from homeassistant.config_entries import (
    ConfigEntry,
    ConfigFlow,
    ConfigFlowResult,
    OptionsFlow,
)
from homeassistant.core import callback
from homeassistant.helpers import config_validation as cv

from .const import (
    CONF_HOST,
    CONF_NAME,
    CONF_PORT,
    CONF_SCAN_INTERVAL,
    CONF_UNIT_ID,
    DEFAULT_NAME,
    DEFAULT_PORT,
    DEFAULT_SCAN_INTERVAL,
    DEFAULT_UNIT_ID,
    DOMAIN,
    MAX_SCAN_INTERVAL,
    MIN_SCAN_INTERVAL,
)
from .coordinator import FroniusModbusCoordinator, FroniusModbusError


async def _validate(hass, data: dict[str, Any]) -> str | None:
    """Connect, run SunSpec discovery and return the inverter serial number."""
    coordinator = FroniusModbusCoordinator(
        hass,
        host=data[CONF_HOST],
        port=data[CONF_PORT],
        unit_id=data[CONF_UNIT_ID],
        scan_interval=DEFAULT_SCAN_INTERVAL,
    )
    try:
        await coordinator.async_discover()
        info = coordinator.device_info_data
        return info.serial if info else None
    finally:
        await coordinator.async_close()


class FroniusModbusConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle the config flow for Fronius Symo Modbus."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle the initial step."""
        errors: dict[str, str] = {}
        if user_input is not None:
            try:
                serial = await _validate(self.hass, user_input)
            except FroniusModbusError as err:
                errors["base"] = (
                    "invalid_sunspec"
                    if "marker" in str(err).lower() or "inverter" in str(err).lower()
                    else "cannot_connect"
                )
            else:
                unique_id = serial or f"{user_input[CONF_HOST]}:{user_input[CONF_PORT]}"
                await self.async_set_unique_id(unique_id)
                self._abort_if_unique_id_configured()
                return self.async_create_entry(
                    title=user_input[CONF_NAME], data=user_input
                )

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_HOST): cv.string,
                    vol.Required(CONF_NAME, default=DEFAULT_NAME): cv.string,
                    vol.Required(CONF_PORT, default=DEFAULT_PORT): cv.port,
                    vol.Required(CONF_UNIT_ID, default=DEFAULT_UNIT_ID): vol.All(
                        cv.positive_int, vol.Range(min=1, max=247)
                    ),
                    vol.Required(
                        CONF_SCAN_INTERVAL, default=DEFAULT_SCAN_INTERVAL
                    ): vol.All(
                        cv.positive_int,
                        vol.Range(min=MIN_SCAN_INTERVAL, max=MAX_SCAN_INTERVAL),
                    ),
                }
            ),
            errors=errors,
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> OptionsFlow:
        """Return the options flow."""
        return FroniusModbusOptionsFlow()


class FroniusModbusOptionsFlow(OptionsFlow):
    """Allow changing connection settings and scan interval after setup."""

    def _current(self, key: str, default: Any) -> Any:
        """Return the effective current value (options override data)."""
        return self.config_entry.options.get(
            key, self.config_entry.data.get(key, default)
        )

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Manage the options."""
        errors: dict[str, str] = {}
        if user_input is not None:
            try:
                await _validate(self.hass, user_input)
            except FroniusModbusError as err:
                errors["base"] = (
                    "invalid_sunspec"
                    if "marker" in str(err).lower() or "inverter" in str(err).lower()
                    else "cannot_connect"
                )
            else:
                return self.async_create_entry(title="", data=user_input)

        suggested = user_input or {
            CONF_HOST: self._current(CONF_HOST, ""),
            CONF_PORT: self._current(CONF_PORT, DEFAULT_PORT),
            CONF_UNIT_ID: self._current(CONF_UNIT_ID, DEFAULT_UNIT_ID),
            CONF_SCAN_INTERVAL: self._current(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL),
        }
        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_HOST, default=suggested[CONF_HOST]): cv.string,
                    vol.Required(CONF_PORT, default=suggested[CONF_PORT]): cv.port,
                    vol.Required(
                        CONF_UNIT_ID, default=suggested[CONF_UNIT_ID]
                    ): vol.All(cv.positive_int, vol.Range(min=1, max=247)),
                    vol.Required(
                        CONF_SCAN_INTERVAL, default=suggested[CONF_SCAN_INTERVAL]
                    ): vol.All(
                        cv.positive_int,
                        vol.Range(min=MIN_SCAN_INTERVAL, max=MAX_SCAN_INTERVAL),
                    ),
                }
            ),
            errors=errors,
        )
