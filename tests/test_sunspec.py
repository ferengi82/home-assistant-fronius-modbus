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


def _mppt_block(n=2):
    """Build a Multi-MPPT (160) data block with n modules."""
    block = [0] * (8 + n * 20)
    # SF: DCA=-2, DCV=-1, DCW=0, DCWH=0
    block[0] = 0x10000 - 2  # -2 as uint16 (sunssf decoder converts back)
    block[1] = 0x10000 - 1  # -1
    block[2] = 0
    block[3] = 0
    block[6] = n  # N modules
    for i in range(n):
        base = 8 + i * 20
        # IDStr "String {i+1}"
        for j, reg in enumerate(_string_regs(f"String {i + 1}", 8)):
            block[base + 1 + j] = reg
        block[base + 9] = 150  # DCA -> 150 * 10^-2 = 1.5 A
        block[base + 10] = 4000  # DCV -> 4000 * 10^-1 = 400.0 V
        block[base + 11] = 600  # DCW -> 600 W
        energy = 6390110
        block[base + 12] = (energy >> 16) & 0xFFFF
        block[base + 13] = energy & 0xFFFF
        block[base + 16] = 35  # Tmp
        block[base + 17] = 4  # DCSt -> mppt
    return block


def test_decode_multi_mppt(sunspec):
    data = sunspec.decode_multi_mppt(_mppt_block(2))
    assert data["num_strings"] == 2
    assert data["string_1_name"] == "String 1"
    assert data["string_1_dc_current"] == 1.5
    assert data["string_1_dc_voltage"] == 400.0
    assert data["string_1_dc_power"] == 600.0
    assert data["string_1_dc_energy"] == 6390110
    assert data["string_1_temp"] == 35
    assert data["string_1_state"] == "mppt"
    # Second string present too.
    assert data["string_2_name"] == "String 2"
    assert data["string_2_dc_power"] == 600.0


def test_decode_multi_mppt_zero_strings(sunspec):
    block = [0] * 8  # N = 0
    assert sunspec.decode_multi_mppt(block) == {"num_strings": 0}


def test_decode_extended_isolation(sunspec):
    block = [0] * 44
    block[42] = 10613  # Ris
    block[43] = 0  # Ris_SF
    data = sunspec.decode_extended(block)
    assert data["isolation_resistance"] == 10613.0


def test_decode_extended_pv_connection(sunspec):
    block = [0] * 44
    block[0] = 7  # PVConn = CONNECTED | AVAILABLE | OPERATING
    assert sunspec.decode_extended(block)["pv_connection"] == "connected"
    block[0] = 0  # not connected
    assert sunspec.decode_extended(block)["pv_connection"] == "disconnected"
    block[0] = 0xFFFF  # not implemented
    assert sunspec.decode_extended(block)["pv_connection"] is None


def _control_block(pct_raw=10000, ena=0, sf=-2):
    """Build an Immediate Controls (123) data block.

    Fixed offsets: WMaxLimPct@3, WMaxLim_Ena@7, WMaxLimPct_SF@21.
    """
    block = [0] * 24
    block[3] = pct_raw
    block[7] = ena
    block[21] = sf & 0xFFFF  # store as uint16
    return block


def test_decode_controls(sunspec):
    data = sunspec.decode_controls(_control_block(pct_raw=5000, ena=1, sf=-2))
    assert data["power_limit_pct"] == 50.0
    assert data["power_limit_enabled"] is True
    assert data["power_limit_sf"] == -2
    off = sunspec.decode_controls(_control_block(pct_raw=10000, ena=0, sf=-2))
    assert off["power_limit_pct"] == 100.0
    assert off["power_limit_enabled"] is False


def test_encode_power_limit_roundtrip(sunspec):
    for pct in (0, 25, 50, 75, 100):
        raw = sunspec.encode_power_limit(pct, -2)
        assert raw == pct * 100
        assert sunspec.apply_scale(raw, -2) == float(pct)
    # Clamping to the valid range.
    assert sunspec.encode_power_limit(150, -2) == 10000
    assert sunspec.encode_power_limit(-5, -2) == 0


def test_full_chain_with_mppt(sunspec):
    # marker + common + inverter(113) + nameplate + 122 + 160 + end
    header = _marker()
    header += [1, 66] + _common_block()
    header += [113, 60] + _float_inverter()
    header += [120, 26] + _nameplate()
    header += [122, 44] + [0] * 44
    header += [160, 48] + _mppt_block(2)
    header += [0xFFFF, 0]
    models = sunspec.parse_chain(header, 40000)
    assert set(models) == {1, 113, 120, 122, 160}
    assert sunspec.MULTI_MPPT_MODEL == 160
    assert sunspec.EXTENDED_MODEL == 122
