"""Unit tests for the SunSpec discovery and decoding logic."""

from __future__ import annotations

import struct


def _f32_regs(value: float) -> list[int]:
    hi, lo = struct.unpack(">HH", struct.pack(">f", value))
    return [hi, lo]


def _string_regs(text: str, length: int) -> list[int]:
    raw = text.encode("ascii").ljust(length * 2, b"\x00")
    return list(struct.unpack(f">{length}H", raw))


def _marker() -> list[int]:
    return [0x5375, 0x6E53]  # "SunS"


def _common_block() -> list[int]:
    block = []
    block += _string_regs("Fronius", 16)
    block += _string_regs("Symo 10.0-3-M", 16)
    block += _string_regs("", 8)  # options
    block += _string_regs("1.2.3", 8)  # version
    block += _string_regs("30123456", 16)  # serial
    block += [1, 0]  # DA + pad -> 66 regs total
    assert len(block) == 66
    return block


def _float_inverter() -> list[int]:
    block = [0] * 60
    block[20:22] = _f32_regs(2500.0)  # ac_power
    block[30:32] = _f32_regs(123456.0)  # ac_energy
    block[36:38] = _f32_regs(2600.0)  # dc_power
    block[38:40] = _f32_regs(41.5)  # temp_cabinet
    block[46] = 4  # operating_state = MPPT
    return block


def _int_inverter() -> list[int]:
    block = [0] * 50
    block[12] = 250  # ac_power value
    block[13] = 1  # ac_power_sf  -> 250 * 10 = 2500
    # ac_energy acc32 = 123456, sf 0
    block[22] = (123456 >> 16) & 0xFFFF
    block[23] = 123456 & 0xFFFF
    block[24] = 0
    block[36] = 7  # operating_state = FAULT
    return block


def _nameplate() -> list[int]:
    block = [0] * 26
    block[0] = 4  # der_type = PV
    block[1] = 1000  # wrtg
    block[2] = 1  # wrtg_sf -> 10000 W
    return block


def _chain(inverter_id: int, inverter_block: list[int]) -> list[int]:
    header = _marker()
    header += [1, 66] + _common_block()
    header += [inverter_id, len(inverter_block)] + inverter_block
    header += [120, 26] + _nameplate()
    header += [0xFFFF, 0]
    return header


def test_parse_chain_locates_models(sunspec):
    header = _chain(113, _float_inverter())
    models = sunspec.parse_chain(header, 40000)
    assert set(models) == {1, 113, 120}
    assert models[1].data_address == 40004
    assert models[113].data_address == 40072
    assert models[120].data_address == 40134


def test_parse_chain_requires_marker(sunspec):
    import pytest

    with pytest.raises(ValueError):
        sunspec.parse_chain([0x0000, 0x0000, 1, 66], 40000)


def test_common_block_strings(sunspec):
    header = _chain(113, _float_inverter())
    models = sunspec.parse_chain(header, 40000)
    common = models[1]
    block = header[common.data_address - 40000 : common.data_address - 40000 + common.length]
    assert sunspec.decode_string(block, *sunspec.COMMON_FIELDS["manufacturer"]) == "Fronius"
    assert sunspec.decode_string(block, *sunspec.COMMON_FIELDS["serial"]) == "30123456"
    assert sunspec.decode_string(block, *sunspec.COMMON_FIELDS["version"]) == "1.2.3"


def test_float_inverter_decode(sunspec):
    block = _float_inverter()
    layout = sunspec.inverter_layout(113)
    assert sunspec.decode_point(block, layout["ac_power"]) == 2500.0
    assert sunspec.decode_point(block, layout["ac_energy"]) == 123456.0
    assert sunspec.decode_point(block, layout["operating_state"]) == 4


def test_int_inverter_decode_with_scale(sunspec):
    block = _int_inverter()
    layout = sunspec.inverter_layout(103)
    power = sunspec.decode_point(block, layout["ac_power"])
    power_sf = sunspec.decode_point(block, layout["ac_power_sf"])
    assert sunspec.apply_scale(power, power_sf) == 2500.0
    assert sunspec.decode_point(block, layout["ac_energy"]) == 123456
    assert sunspec.decode_point(block, layout["operating_state"]) == 7


def test_nameplate_decode_with_scale(sunspec):
    block = _nameplate()
    wrtg = sunspec.decode_point(block, sunspec.NAMEPLATE_POINTS["wrtg"])
    wrtg_sf = sunspec.decode_point(block, sunspec.NAMEPLATE_POINTS["wrtg_sf"])
    assert sunspec.apply_scale(wrtg, wrtg_sf) == 10000.0


def test_not_implemented_values(sunspec):
    block = _int_inverter()
    block[12] = 0x8000  # int16 NaN for ac_power
    layout = sunspec.inverter_layout(103)
    assert sunspec.decode_point(block, layout["ac_power"]) is None


def test_find_inverter_model(sunspec):
    assert sunspec.find_inverter_model({1: None, 103: None, 120: None}) == 103
    assert sunspec.find_inverter_model({1: None, 111: None}) == 111
    assert sunspec.find_inverter_model({1: None, 120: None}) is None
