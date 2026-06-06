"""Constants for the Fronius Symo Modbus integration."""

from __future__ import annotations

from typing import Final

DOMAIN: Final = "fronius_symo_modbus"

# Config / options keys
CONF_HOST: Final = "host"
CONF_PORT: Final = "port"
CONF_UNIT_ID: Final = "unit_id"
CONF_SCAN_INTERVAL: Final = "scan_interval"
CONF_NAME: Final = "name"

# Defaults
DEFAULT_NAME: Final = "Fronius Symo"
DEFAULT_PORT: Final = 502
DEFAULT_UNIT_ID: Final = 1
DEFAULT_SCAN_INTERVAL: Final = 30

MIN_SCAN_INTERVAL: Final = 5
MAX_SCAN_INTERVAL: Final = 600

# Modbus / SunSpec base
# SunSpec base register is the holding register 40001 (Modicon notation).
# Modbus protocol addresses are zero-based, so register 40001 -> address 40000.
# The SunS marker and end-of-chain model id live in sunspec.py.
SUNSPEC_BASE_ADDRESS: Final = 40000

# Number of registers to read in a single Modbus request. Fronius / SunSpec
# blocks comfortably fit within the Modbus limit of 125 registers per request.
MAX_REGISTER_READ: Final = 124

CONNECT_TIMEOUT: Final = 10
