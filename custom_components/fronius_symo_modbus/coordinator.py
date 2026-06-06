"""Data update coordinator for the Fronius Symo Modbus integration."""

from __future__ import annotations

import asyncio
import logging
from datetime import timedelta

from pymodbus.client import AsyncModbusTcpClient

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from . import sunspec
from .const import (
    CONNECT_TIMEOUT,
    DOMAIN,
    MAX_REGISTER_READ,
    SUNSPEC_BASE_ADDRESS,
)

_LOGGER = logging.getLogger(__name__)

# Registers to scan from the base address to discover the model chain. Large
# enough to cover SunSpec marker + common + inverter + nameplate models.
_DISCOVERY_LENGTH = 180


class FroniusModbusError(Exception):
    """Raised for Modbus / SunSpec communication problems."""


class DeviceInfoData:
    """Static device information read from the SunSpec common block."""

    def __init__(
        self,
        manufacturer: str | None,
        model: str | None,
        serial: str | None,
        version: str | None,
    ) -> None:
        self.manufacturer = manufacturer or "Fronius"
        self.model = model or "Symo"
        self.serial = serial
        self.version = version


class FroniusModbusCoordinator(DataUpdateCoordinator[dict[str, int | float | None]]):
    """Polls a Fronius inverter over Modbus TCP and decodes SunSpec models."""

    def __init__(
        self,
        hass: HomeAssistant,
        *,
        host: str,
        port: int,
        unit_id: int,
        scan_interval: int,
        entry: ConfigEntry | None = None,
    ) -> None:
        """Initialise the coordinator."""
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=timedelta(seconds=scan_interval),
            config_entry=entry,
        )
        self._host = host
        self._port = port
        self._unit_id = unit_id
        self._client: AsyncModbusTcpClient | None = None
        self._lock = asyncio.Lock()

        self.models: dict[int, sunspec.ModelLocation] = {}
        self.inverter_model_id: int | None = None
        self.inverter_layout: dict[str, sunspec.Point] | None = None
        self.device_info_data: DeviceInfoData | None = None

    # --- Connection helpers ---------------------------------------------

    async def _ensure_client(self) -> AsyncModbusTcpClient:
        """Return a connected Modbus client, connecting if necessary."""
        if self._client is None:
            self._client = AsyncModbusTcpClient(
                self._host, port=self._port, timeout=CONNECT_TIMEOUT
            )
        if not self._client.connected:
            connected = await self._client.connect()
            if not connected or not self._client.connected:
                raise FroniusModbusError(
                    f"Could not connect to {self._host}:{self._port}"
                )
        return self._client

    async def _read_block(self, address: int, count: int) -> list[int]:
        """Read ``count`` holding registers starting at ``address``.

        Splits the read into Modbus-sized chunks and concatenates the result.
        """
        client = await self._ensure_client()
        registers: list[int] = []
        offset = 0
        while offset < count:
            chunk = min(MAX_REGISTER_READ, count - offset)
            result = await self._read_holding(client, address + offset, chunk)
            if result is None or result.isError():
                raise FroniusModbusError(
                    f"Modbus read error at {address + offset} (count {chunk})"
                )
            registers.extend(result.registers)
            offset += chunk
        return registers

    async def _read_holding(self, client: AsyncModbusTcpClient, address: int, count: int):
        """Read holding registers, tolerating pymodbus keyword changes."""
        try:
            return await client.read_holding_registers(
                address, count=count, slave=self._unit_id
            )
        except TypeError:
            # Newer pymodbus releases renamed the unit keyword.
            return await client.read_holding_registers(
                address, count=count, device_id=self._unit_id
            )

    async def async_close(self) -> None:
        """Close the Modbus connection."""
        if self._client is not None:
            self._client.close()
            self._client = None

    # --- Discovery -------------------------------------------------------

    async def async_discover(self) -> None:
        """Discover the SunSpec model chain and static device information."""
        async with self._lock:
            header = await self._read_block(SUNSPEC_BASE_ADDRESS, _DISCOVERY_LENGTH)
            try:
                self.models = sunspec.parse_chain(header, SUNSPEC_BASE_ADDRESS)
            except ValueError as err:
                raise FroniusModbusError(str(err)) from err

            self.inverter_model_id = sunspec.find_inverter_model(self.models)
            if self.inverter_model_id is None:
                raise FroniusModbusError("No SunSpec inverter model found")
            self.inverter_layout = sunspec.inverter_layout(self.inverter_model_id)

            self.device_info_data = self._decode_common(header)

    def _decode_common(self, header: list[int]) -> DeviceInfoData:
        """Decode the common block from the discovery dump."""
        common = self.models.get(sunspec.COMMON_MODEL)
        if common is None:
            return DeviceInfoData(None, None, None, None)
        # Translate absolute data address back into the header dump index.
        start = common.data_address - SUNSPEC_BASE_ADDRESS
        block = header[start : start + common.length]

        def field(name: str) -> str | None:
            offset, length = sunspec.COMMON_FIELDS[name]
            return sunspec.decode_string(block, offset, length)

        return DeviceInfoData(
            manufacturer=field("manufacturer"),
            model=field("model"),
            serial=field("serial"),
            version=field("version"),
        )

    # --- Polling ---------------------------------------------------------

    async def _async_update_data(self) -> dict[str, int | float | None]:
        """Fetch and decode the inverter and nameplate models."""
        async with self._lock:
            try:
                if not self.models or self.inverter_layout is None:
                    # Re-discover after a reconnect.
                    header = await self._read_block(
                        SUNSPEC_BASE_ADDRESS, _DISCOVERY_LENGTH
                    )
                    self.models = sunspec.parse_chain(header, SUNSPEC_BASE_ADDRESS)
                    self.inverter_model_id = sunspec.find_inverter_model(self.models)
                    self.inverter_layout = sunspec.inverter_layout(
                        self.inverter_model_id
                    )

                data: dict[str, int | float | None] = {}
                data.update(await self._read_inverter())
                data.update(await self._read_nameplate())
                return data
            except FroniusModbusError as err:
                # Drop the model map so the next cycle re-discovers after a
                # reconnect, and surface the failure to the coordinator.
                await self.async_close()
                self.models = {}
                raise UpdateFailed(str(err)) from err

    async def _read_inverter(self) -> dict[str, int | float | None]:
        """Read and decode the inverter model block."""
        assert self.inverter_model_id is not None
        assert self.inverter_layout is not None
        location = self.models[self.inverter_model_id]
        block = await self._read_block(location.data_address, location.length)
        return self._decode_layout(block, self.inverter_layout)

    async def _read_nameplate(self) -> dict[str, int | float | None]:
        """Read and decode the nameplate model block, if present."""
        location = self.models.get(sunspec.NAMEPLATE_MODEL)
        if location is None:
            return {}
        block = await self._read_block(location.data_address, location.length)
        decoded = self._decode_layout(block, sunspec.NAMEPLATE_POINTS)
        # Prefix nameplate keys to avoid clashes with inverter points.
        return {f"nameplate_{key}": value for key, value in decoded.items()}

    @staticmethod
    def _decode_layout(
        block: list[int], layout: dict[str, sunspec.Point]
    ) -> dict[str, int | float | None]:
        """Decode every point in a layout, applying scale factors."""
        raw: dict[str, int | float | None] = {
            name: sunspec.decode_point(block, point)
            for name, point in layout.items()
        }
        scaled: dict[str, int | float | None] = {}
        for name, point in layout.items():
            if point.dtype == "sunssf":
                scaled[name] = raw[name]
                continue
            if point.scale is not None:
                scaled[name] = sunspec.apply_scale(raw[name], raw.get(point.scale))
            else:
                scaled[name] = raw[name]
        return scaled
