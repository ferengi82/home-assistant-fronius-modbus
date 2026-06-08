"""SunSpec model discovery and decoding for Fronius inverters.

This module is intentionally free of Home Assistant and pymodbus imports so it
can be unit tested against plain lists of register values.

A SunSpec device exposes a chain of models starting at a base register:

    [ "SunS" marker (2 regs) ][ model_id ][ length L ][ L data regs ] ...

The chain terminates with model id 0xFFFF. Fronius supports two interchangeable
inverter layouts selected in the Datamanager:

    * float   -> inverter models 111 / 112 / 113 (float32, no scale factors)
    * int+SF  -> inverter models 101 / 102 / 103 (integers + sunssf scale factors)

Switching the layout shifts the addresses of all following models, so we never
hardcode addresses: we walk the chain and read each model's reported length.
"""

from __future__ import annotations

import struct
from dataclasses import dataclass

# "SunS" identifier (0x53756e53) stored in the first two SunSpec registers.
SUNSPEC_MARKER = 0x53756E53
# End-of-chain model id.
SUNSPEC_END_MODEL = 0xFFFF

# SunSpec "not implemented" sentinels per data type.
_NAN_UINT16 = 0xFFFF
_NAN_INT16 = 0x8000
_NAN_UINT32 = 0xFFFFFFFF
_NAN_ACC32 = 0x00000000  # accumulators report 0 when not implemented
_NAN_SUNSSF = 0x8000

# Inverter model ids by layout.
INVERTER_MODELS_INT = (101, 102, 103)
INVERTER_MODELS_FLOAT = (111, 112, 113)
COMMON_MODEL = 1
NAMEPLATE_MODEL = 120
EXTENDED_MODEL = 122
CONTROL_MODEL = 123
MULTI_MPPT_MODEL = 160


@dataclass(frozen=True)
class Point:
    """A single SunSpec data point inside a model block.

    ``offset`` is the zero-based register index within the model's *data* block
    (i.e. the first register after the length register is offset 0).
    """

    offset: int
    dtype: str
    # Optional name of the scale-factor point that scales this value.
    scale: str | None = None


# --- Decoders ---------------------------------------------------------------


def _u16(regs: list[int], off: int) -> int | None:
    val = regs[off]
    return None if val == _NAN_UINT16 else val


def _s16(regs: list[int], off: int) -> int | None:
    val = regs[off]
    if val == _NAN_INT16:
        return None
    return val - 0x10000 if val >= 0x8000 else val


def _u32(regs: list[int], off: int) -> int | None:
    val = (regs[off] << 16) | regs[off + 1]
    return None if val == _NAN_UINT32 else val


def _acc32(regs: list[int], off: int) -> int | None:
    val = (regs[off] << 16) | regs[off + 1]
    return None if val == _NAN_ACC32 else val


def _f32(regs: list[int], off: int) -> float | None:
    raw = struct.pack(">HH", regs[off], regs[off + 1])
    val = struct.unpack(">f", raw)[0]
    # NaN / inf are SunSpec "not implemented" markers for float32.
    if val != val or val in (float("inf"), float("-inf")):
        return None
    return val


def _sunssf(regs: list[int], off: int) -> int | None:
    val = regs[off]
    if val == _NAN_SUNSSF:
        return None
    return val - 0x10000 if val >= 0x8000 else val


def _string(regs: list[int], off: int, length: int) -> str | None:
    raw = b"".join(struct.pack(">H", regs[off + i]) for i in range(length))
    text = raw.split(b"\x00", 1)[0].decode("ascii", errors="ignore").strip()
    return text or None


_DECODERS = {
    "uint16": _u16,
    "enum16": _u16,
    "int16": _s16,
    "uint32": _u32,
    "acc32": _acc32,
    "float32": _f32,
    "sunssf": _sunssf,
}

# Register width per data type.
_WIDTH = {
    "uint16": 1,
    "enum16": 1,
    "int16": 1,
    "sunssf": 1,
    "uint32": 2,
    "acc32": 2,
    "float32": 2,
}


def decode_point(regs: list[int], point: Point) -> int | float | None:
    """Decode a single point from a model data block (offset 0 = first reg)."""
    decoder = _DECODERS[point.dtype]
    if point.offset + _WIDTH[point.dtype] > len(regs):
        return None
    return decoder(regs, point.offset)


def decode_string(regs: list[int], offset: int, length: int) -> str | None:
    """Decode a fixed-length SunSpec string from a model data block."""
    if offset + length > len(regs):
        return None
    return _string(regs, offset, length)


def apply_scale(value: int | float | None, scale: int | None) -> float | None:
    """Apply a SunSpec sunssf scale factor (value * 10**scale)."""
    if value is None:
        return None
    if scale is None:
        return float(value)
    return float(value) * (10**scale)


# --- Model layouts ----------------------------------------------------------
#
# Offsets are zero-based register indices within the model data block.

# Common block (model 1) string fields. (offset, length-in-registers)
COMMON_FIELDS = {
    "manufacturer": (0, 16),
    "model": (16, 16),
    "options": (32, 8),
    "version": (40, 8),
    "serial": (48, 16),
}

# Inverter model layout for int+SF models (101/102/103), 50 data registers.
INVERTER_INT_POINTS: dict[str, Point] = {
    "ac_current": Point(0, "uint16", "ac_current_sf"),
    "ac_current_sf": Point(4, "sunssf"),
    "ac_current_a": Point(1, "uint16", "ac_current_sf"),
    "ac_current_b": Point(2, "uint16", "ac_current_sf"),
    "ac_current_c": Point(3, "uint16", "ac_current_sf"),
    "ac_voltage_ab": Point(5, "uint16", "ac_voltage_sf"),
    "ac_voltage_bc": Point(6, "uint16", "ac_voltage_sf"),
    "ac_voltage_ca": Point(7, "uint16", "ac_voltage_sf"),
    "ac_voltage_a": Point(8, "uint16", "ac_voltage_sf"),
    "ac_voltage_b": Point(9, "uint16", "ac_voltage_sf"),
    "ac_voltage_c": Point(10, "uint16", "ac_voltage_sf"),
    "ac_voltage_sf": Point(11, "sunssf"),
    "ac_power": Point(12, "int16", "ac_power_sf"),
    "ac_power_sf": Point(13, "sunssf"),
    "ac_frequency": Point(14, "uint16", "ac_frequency_sf"),
    "ac_frequency_sf": Point(15, "sunssf"),
    "ac_va": Point(16, "int16", "ac_va_sf"),
    "ac_va_sf": Point(17, "sunssf"),
    "ac_var": Point(18, "int16", "ac_var_sf"),
    "ac_var_sf": Point(19, "sunssf"),
    "ac_pf": Point(20, "int16", "ac_pf_sf"),
    "ac_pf_sf": Point(21, "sunssf"),
    "ac_energy": Point(22, "acc32", "ac_energy_sf"),
    "ac_energy_sf": Point(24, "sunssf"),
    "dc_current": Point(25, "uint16", "dc_current_sf"),
    "dc_current_sf": Point(26, "sunssf"),
    "dc_voltage": Point(27, "uint16", "dc_voltage_sf"),
    "dc_voltage_sf": Point(28, "sunssf"),
    "dc_power": Point(29, "int16", "dc_power_sf"),
    "dc_power_sf": Point(30, "sunssf"),
    "temp_cabinet": Point(31, "int16", "temp_sf"),
    "temp_heatsink": Point(32, "int16", "temp_sf"),
    "temp_sf": Point(35, "sunssf"),
    "operating_state": Point(36, "enum16"),
    "vendor_state": Point(37, "enum16"),
}

# Inverter model layout for float models (111/112/113), 60 data registers.
INVERTER_FLOAT_POINTS: dict[str, Point] = {
    "ac_current": Point(0, "float32"),
    "ac_current_a": Point(2, "float32"),
    "ac_current_b": Point(4, "float32"),
    "ac_current_c": Point(6, "float32"),
    "ac_voltage_ab": Point(8, "float32"),
    "ac_voltage_bc": Point(10, "float32"),
    "ac_voltage_ca": Point(12, "float32"),
    "ac_voltage_a": Point(14, "float32"),
    "ac_voltage_b": Point(16, "float32"),
    "ac_voltage_c": Point(18, "float32"),
    "ac_power": Point(20, "float32"),
    "ac_frequency": Point(22, "float32"),
    "ac_va": Point(24, "float32"),
    "ac_var": Point(26, "float32"),
    "ac_pf": Point(28, "float32"),
    "ac_energy": Point(30, "float32"),
    "dc_current": Point(32, "float32"),
    "dc_voltage": Point(34, "float32"),
    "dc_power": Point(36, "float32"),
    "temp_cabinet": Point(38, "float32"),
    "temp_heatsink": Point(40, "float32"),
    "operating_state": Point(46, "enum16"),
    "vendor_state": Point(47, "enum16"),
}

# Nameplate model (120) — always int+SF style. 26 data registers.
NAMEPLATE_POINTS: dict[str, Point] = {
    "der_type": Point(0, "enum16"),
    "wrtg": Point(1, "uint16", "wrtg_sf"),
    "wrtg_sf": Point(2, "sunssf"),
    "vartg": Point(3, "uint16", "vartg_sf"),
    "vartg_sf": Point(4, "sunssf"),
    "artg": Point(10, "uint16", "artg_sf"),
    "artg_sf": Point(11, "sunssf"),
}

# SunSpec inverter operating-state enum (St register) including Fronius codes.
OPERATING_STATES = {
    1: "off",
    2: "sleeping",
    3: "starting",
    4: "mppt",
    5: "throttled",
    6: "shutting_down",
    7: "fault",
    8: "standby",
    9: "no_businit",
    10: "no_comm_inv",
    11: "sn_overcurrent",
    12: "bootload",
    13: "afci",
}


@dataclass(frozen=True)
class ModelLocation:
    """Where a model lives in the register chain."""

    model_id: int
    # Address of the first *data* register (after id and length registers).
    data_address: int
    length: int


def parse_chain(header: list[int], base_address: int) -> dict[int, ModelLocation]:
    """Parse the SunSpec model chain from a contiguous register dump.

    ``header`` must start at ``base_address`` and contain the "SunS" marker
    followed by the model chain. Returns a mapping of model id -> location.

    Raises ValueError if the SunSpec marker is missing.
    """
    if len(header) < 2 or ((header[0] << 16) | header[1]) != SUNSPEC_MARKER:
        raise ValueError("SunSpec marker not found")

    models: dict[int, ModelLocation] = {}
    # Index into ``header``; start right after the 2-register marker.
    idx = 2
    while idx + 1 < len(header):
        model_id = header[idx]
        length = header[idx + 1]
        if model_id == SUNSPEC_END_MODEL:
            break
        data_address = base_address + idx + 2
        models[model_id] = ModelLocation(model_id, data_address, length)
        idx += 2 + length
    return models


def inverter_layout(model_id: int) -> dict[str, Point] | None:
    """Return the point layout for a given inverter model id."""
    if model_id in INVERTER_MODELS_INT:
        return INVERTER_INT_POINTS
    if model_id in INVERTER_MODELS_FLOAT:
        return INVERTER_FLOAT_POINTS
    return None


def find_inverter_model(models: dict[int, ModelLocation]) -> int | None:
    """Return the inverter model id present in the chain, if any."""
    for model_id in (*INVERTER_MODELS_INT, *INVERTER_MODELS_FLOAT):
        if model_id in models:
            return model_id
    return None


# --- Multi-MPPT model (160) -------------------------------------------------
#
# Fixed header (offsets within the model data block):
#   0 DCA_SF, 1 DCV_SF, 2 DCW_SF, 3 DCWH_SF, 4-5 Evt, 6 N, 7 TmsPer
# Then ``N`` repeating module blocks of 20 registers, module i at base 8+i*20:
#   +0 ID, +1..+8 IDStr(8), +9 DCA, +10 DCV, +11 DCW, +12..+13 DCWH(acc32),
#   +14..+15 Tms, +16 Tmp(int16), +17 DCSt(enum16), +18..+19 DCEvt
_MPPT_FIXED_LEN = 8
_MPPT_MODULE_LEN = 20

# DC operating-state enum for a single MPPT module (SunSpec DCEvt/DCSt).
MPPT_STATES = {
    1: "off",
    2: "sleeping",
    3: "starting",
    4: "mppt",
    5: "throttled",
    6: "shutting_down",
    7: "fault",
    8: "standby",
    9: "test",
}


def decode_multi_mppt(block: list[int]) -> dict[str, int | float | str | None]:
    """Decode the Multi-MPPT model (160) into per-string values.

    Returns a dict with ``num_strings`` plus, for each string ``n`` (1-based):
    ``string_{n}_dc_current/voltage/power/energy/temp`` and
    ``string_{n}_state`` / ``string_{n}_name``.
    """
    if len(block) < _MPPT_FIXED_LEN:
        return {"num_strings": 0}
    dca_sf = _sunssf(block, 0)
    dcv_sf = _sunssf(block, 1)
    dcw_sf = _sunssf(block, 2)
    dcwh_sf = _sunssf(block, 3)
    count = block[6]
    if count in (0, _NAN_UINT16):
        return {"num_strings": 0}

    result: dict[str, int | float | str | None] = {"num_strings": count}
    for i in range(count):
        base = _MPPT_FIXED_LEN + i * _MPPT_MODULE_LEN
        if base + _MPPT_MODULE_LEN > len(block):
            break
        n = i + 1
        result[f"string_{n}_name"] = _string(block, base + 1, 8)
        result[f"string_{n}_dc_current"] = apply_scale(_u16(block, base + 9), dca_sf)
        result[f"string_{n}_dc_voltage"] = apply_scale(_u16(block, base + 10), dcv_sf)
        result[f"string_{n}_dc_power"] = apply_scale(_u16(block, base + 11), dcw_sf)
        result[f"string_{n}_dc_energy"] = apply_scale(_acc32(block, base + 12), dcwh_sf)
        result[f"string_{n}_temp"] = _s16(block, base + 16)
        state = _u16(block, base + 17)
        result[f"string_{n}_state"] = (
            MPPT_STATES.get(int(state), "unknown") if state is not None else None
        )
    return result


# --- Extended Measurements & Status model (122) -----------------------------
#
# Notable offsets within the model data block:
#   42 Ris (uint16, isolation resistance), 43 Ris_SF (sunssf)


def decode_extended(block: list[int]) -> dict[str, int | float | str | None]:
    """Decode a useful subset of the Extended Measurements & Status model (122)."""
    result: dict[str, int | float | str | None] = {}
    # PVConn (offset 0) is a bitfield; bit 0 = CONNECTED.
    if len(block) > 0:
        pvconn = _u16(block, 0)
        result["pv_connection"] = (
            None if pvconn is None else ("connected" if pvconn & 0x1 else "disconnected")
        )
    if len(block) > 43:
        result["isolation_resistance"] = apply_scale(
            _u16(block, 42), _sunssf(block, 43)
        )
    return result


# --- Immediate Controls model (123) -----------------------------------------
#
# Writable inverter controls. Notable offsets within the model data block:
#   3 WMaxLimPct (uint16, active power limit, scaled by WMaxLimPct_SF)
#   7 WMaxLim_Ena (enum16: 0 = disabled, 1 = enabled)
#   21 WMaxLimPct_SF (sunssf)
WMAXLIMPCT_OFFSET = 3
WMAXLIM_ENA_OFFSET = 7
WMAXLIMPCT_SF_OFFSET = 21


def decode_controls(block: list[int]) -> dict[str, int | float | bool | None]:
    """Decode the writable active-power-limit controls from model 123.

    Returns ``power_limit_pct`` (0-100 %), ``power_limit_enabled`` (bool) and
    the raw ``power_limit_sf`` scale factor needed to encode a new setpoint.
    """
    result: dict[str, int | float | bool | None] = {
        "power_limit_pct": None,
        "power_limit_enabled": None,
        "power_limit_sf": None,
    }
    if len(block) <= WMAXLIMPCT_SF_OFFSET:
        return result
    sf = _sunssf(block, WMAXLIMPCT_SF_OFFSET)
    result["power_limit_sf"] = sf
    result["power_limit_pct"] = apply_scale(_u16(block, WMAXLIMPCT_OFFSET), sf)
    ena = _u16(block, WMAXLIM_ENA_OFFSET)
    result["power_limit_enabled"] = None if ena is None else bool(ena)
    return result


def encode_power_limit(pct: float, sf: int | None) -> int:
    """Encode an active-power-limit percentage into a raw register value.

    Inverse of ``apply_scale``: ``raw = round(pct / 10**sf)``. Clamped to the
    valid 0-100 % range and the uint16 register width.
    """
    pct = max(0.0, min(100.0, float(pct)))
    scale = 0 if sf is None else sf
    raw = round(pct / (10**scale))
    return max(0, min(0xFFFF, raw))
