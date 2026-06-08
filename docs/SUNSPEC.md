# SunSpec register reference (Fronius Datamanager)

> 🤖 AI-generated documentation. Source of truth is the official Fronius "Datamanager Modbus TCP & RTU" manual + the SunSpec model specifications. This file documents what `custom_components/fronius_symo_modbus/sunspec.py` implements and was verified against a real Symo Advanced 10.0-3-M.

## Addressing

- SunSpec base register is **40001** (Modicon notation). Modbus protocol addresses are zero-based, so register 40001 → protocol address **40000** (use this with pymodbus).
- The first two registers hold the `SunS` marker `0x53756E53`.
- After the marker, models are chained: `[id][length][length data registers]…`, terminated by id `0xFFFF`.
- **Offsets in the tables below are zero-based within a model's *data* block** (the first register after the model's `length` register = offset 0).

## Model chain observed on the test device (float layout)

| Model | Meaning | data @ (protocol addr) | length |
| --- | --- | --- | --- |
| 1   | Common (device info) | 40004 | 65 |
| 113 | Inverter, 3-phase, **float** | 40071 | 60 |
| 120 | Nameplate (ratings) | 40133 | 26 |
| 121 | Basic settings | 40161 | 30 |
| 122 | Extended measurements & status | 40193 | 44 |
| 123 | Immediate controls (active-power limit, **write**) | 40239 | 24 |
| 160 | Multi-MPPT (per string) | 40265 | 48 |
| 0xFFFF | end | 40313 | — |

Addresses shift with layout/firmware, so the code **never hardcodes them** — it walks the chain. The `int+SF` layout uses inverter models `101/102/103` (and would shift everything after).

## Inverter model (101/102/103 int+SF, 111/112/113 float)

Same logical points in both layouts; int+SF uses `uint16/int16` values + `sunssf` scale factors, float uses `float32` (no scale factors). Key points (logical name → meaning):

`ac_current` (+ per phase `a/b/c`), `ac_voltage_a/b/c` (line-neutral) and `ac_voltage_ab/bc/ca` (line-line), `ac_power` (W), `ac_frequency` (Hz), `ac_va`, `ac_var`, `ac_pf`, `ac_energy` (Wh lifetime, acc32/float), `dc_current`, `dc_voltage`, `dc_power`, `temp_cabinet`/`temp_heatsink`, `operating_state` (St), `vendor_state`.

Exact offsets are in `INVERTER_INT_POINTS` / `INVERTER_FLOAT_POINTS` in `sunspec.py`.

Operating-state enum (`St`): 1 off, 2 sleeping, 3 starting, 4 MPPT (producing), 5 throttled, 6 shutting down, 7 fault, 8 standby, plus Fronius codes 9–13 (see `OPERATING_STATES`).

## Nameplate model (120)

`der_type`, `wrtg` (rated power, W, scaled by `wrtg_sf`), `vartg`, `artg` (rated current). Read once and exposed as diagnostic sensors.

## Extended measurements & status (122)

Implemented subset:
- `pv_connection` = `PVConn` (offset 0, bitfield) bit 0 → `connected` / `disconnected`.
- `isolation_resistance` = `Ris` (offset 42, `uint16`) × `10**Ris_SF` (offset 43). On the test device `Ris` is not-implemented (`0xFFFF`) → the sensor stays unavailable.

Other fields (storage/grid connection state, accumulated energy variants as `acc64`, time source) exist but are not exposed yet.

## Multi-MPPT model (160) — per-string data

Fixed header (data offsets): `0 DCA_SF, 1 DCV_SF, 2 DCW_SF, 3 DCWH_SF, 4-5 Evt, 6 N (module count), 7 TmsPer`.

Then `N` repeating **20-register** module blocks; module `i` starts at `8 + i*20`:

| rel. offset | field | type | exposed as |
| --- | --- | --- | --- |
| +0 | ID | uint16 | — |
| +1..+8 | IDStr | string(8) | `string_{n}_name` |
| +9 | DCA | uint16 ×DCA_SF | `string_{n}_dc_current` |
| +10 | DCV | uint16 ×DCV_SF | `string_{n}_dc_voltage` |
| +11 | DCW | uint16 ×DCW_SF | `string_{n}_dc_power` |
| +12..+13 | DCWH | acc32 ×DCWH_SF | `string_{n}_dc_energy` |
| +14..+15 | Tms | uint32 | — |
| +16 | Tmp | int16 | `string_{n}_temp` (often NaN → unavailable) |
| +17 | DCSt | enum16 | `string_{n}_state` (see `MPPT_STATES`) |
| +18..+19 | DCEvt | bitfield32 | — |

The test device reports `N = 2` ("String 1", "String 2"), each with its own lifetime energy counter (sum ≈ inverter lifetime energy).

> **Aggregate DC current/voltage:** the inverter block (113) reports `dc_current` and `dc_voltage` as not-implemented (NaN) on this firmware — only `dc_power` is filled. The coordinator therefore **derives `dc_current` as the sum of the per-string currents**. No aggregate DC voltage is exposed (two independent MPPT strings have no single meaningful voltage); use the per-string voltages.

## Immediate controls (123) — active-power limit (write)

Writable; only exposed when **inverter control is enabled** in the options flow (default off) and the model is present. Requires *"inverter control via Modbus"* to be enabled in the Fronius Datamanager, otherwise writes are rejected.

| data offset | field | type | exposed as |
| --- | --- | --- | --- |
| +3 | WMaxLimPct | uint16 ×WMaxLimPct_SF | `number` "Active power limit" (0–100 %) |
| +7 | WMaxLim_Ena | enum16 (0/1) | `switch` "Active power limit active" |
| +21 | WMaxLimPct_SF | sunssf | scale factor (e.g. −2 → write `pct × 100`) |

Write: `raw = round(pct / 10**WMaxLimPct_SF)` (see `sunspec.encode_power_limit`). Other model-123 points (Conn connect/disconnect, OutPFSet power factor, reactive-power VArPct) are present but intentionally not exposed.

Verified on the test device: writing `WMaxLimPct = 50 %` with `WMaxLim_Ena = 1` throttled AC output from ~6.9 kW to ~5.0 kW (50 % of the 10 kW rating); disabling the limit and writing 100 % restored full output.

## Not implemented (intentional)

- Model 123: only the active-power limit; not connect/disconnect (`Conn`) or power factor (`OutPFSet`).
- Meter models (2xx) — Fronius Smart Meter; not present on the test device's Modbus chain.
- RTU transport — TCP only.
