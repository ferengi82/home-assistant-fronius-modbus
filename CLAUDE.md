# CLAUDE.md — guide for AI agents & developers

> 🤖 This repository was generated and is maintained with **AI (Anthropic Claude Code)**. This file gives an AI agent (or human) the context to continue the work safely and idiomatically. Other AI tools: see [AGENTS.md](AGENTS.md).

## What this is

A Home Assistant **custom integration** (`fronius_symo_modbus`) that reads a **Fronius Symo Advanced** PV inverter over **Modbus TCP** via the Fronius Datamanager card's **SunSpec** register map. Read-only by default, with an **opt-in active-power-limit control** (SunSpec model 123, write). HACS-installable. Fully UI-configured (config flow + options flow). Other Fronius devices (e.g. GEN24) are explicitly out of scope.

## Repository layout

```
custom_components/fronius_symo_modbus/
  __init__.py        # async_setup_entry/unload; reads conn params options-over-data; reload on options change
  manifest.json      # domain=fronius_symo_modbus, version, requirements (pymodbus), iot_class=local_polling
  const.py           # DOMAIN, CONF_* keys, defaults (PORT 502, UNIT_ID 1, SCAN_INTERVAL 10, MIN 5/MAX 600)
  config_flow.py     # user step (validates by connecting) + OptionsFlow (host/port/unit_id/scan_interval)
  coordinator.py     # DataUpdateCoordinator: pymodbus AsyncModbusTcpClient, header-walk discovery, polling
  sunspec.py         # PURE module (no HA/pymodbus imports): model layouts + decoders. Unit-tested.
  models.py          # declarative SensorEntityDescription tables + per-string description builder
  entity.py          # base entity + DeviceInfo (from device_registry)
  sensor.py          # builds sensors from models.py + dynamic per-string sensors
  number.py          # active-power-limit % (write, only when control enabled)
  switch.py          # active-power-limit enable (write, only when control enabled)
  diagnostics.py     # config entry diagnostics (serial redacted)
  brand/             # bundled Fronius icon/logo (icon.png, [email protected], logo.png, [email protected])
  strings.json, translations/{en,de}.json
scripts/dump_sunspec.py   # standalone (pymodbus-only) tool to dump the chain from a real device
tests/                    # pytest; loads sunspec.py standalone (no HA needed)
docs/SUNSPEC.md           # SunSpec model & register reference
hacs.json, .github/workflows/validate.yml
```

## How it works

- **Discovery (`coordinator._walk_chain`)**: verifies the `SunS` marker at register 40001, then reads each model header (2 registers: `id`, `length`) and follows the chain until the `0xFFFF` end marker. This never reads past the end (the Datamanager errors on out-of-range reads) and adapts to both SunSpec layouts.
- **Layout auto-detection**: the inverter model id tells the layout — `101/102/103` = int+SF (integers + `sunssf` scale factors), `111/112/113` = float32. `sunspec.inverter_layout()` returns the right point map.
- **Static vs polled**: common block (device info) and nameplate are read once at discovery and cached; the inverter model, multi-MPPT (160) and extended (122) models are read every poll.
- **Decoding (`sunspec.py`)**: typed decoders (`uint16/int16/uint32/acc32/float32/sunssf/string`) return `None` for SunSpec "not implemented" sentinels (e.g. `0x8000`, `0xFFFF`, NaN). `apply_scale` applies `value * 10**sunssf`.
- **Sensors**: `models.py` holds static `SensorEntityDescription` tables keyed to coordinator data dict keys; `sensor.py` only creates entities whose key is present. Per-string sensors are built dynamically for `coordinator.num_strings` using one translation key per metric with a `{string}` placeholder.

See [docs/SUNSPEC.md](docs/SUNSPEC.md) for the exact model list and register offsets.

## Conventions

- Match the existing style: declarative description tables, pure/testable `sunspec.py`, German + English translations for every new entity (`strings.json` is the English source; copy it to `translations/en.json`; mirror keys in `translations/de.json`).
- Keep `sunspec.py` free of HA/pymodbus imports so the unit tests run without Home Assistant.
- Redundant/raw/diagnostic sensors are `entity_registry_enabled_default=False`; primary + per-string sensors are enabled.
- pymodbus 3.x: read calls use `slave=` with a `device_id=` fallback (`coordinator._read_holding`) for cross-version compatibility.

## Build / test / verify

```bash
python -m venv .venv && .venv/bin/pip install pytest
.venv/bin/python -m pytest tests -q          # unit tests (no HA required)
python -m py_compile custom_components/fronius_symo_modbus/*.py
# Against a real inverter (read-only):
.venv/bin/pip install pymodbus
.venv/bin/python scripts/dump_sunspec.py <inverter-ip>
```

CI (`.github/workflows/validate.yml`) runs **hassfest**, the **HACS** action and **pytest** on every push/PR. All three must stay green.

## Release / deploy

- Workflow: feature branch → PR → squash-merge to `main`. A repository ruleset (`non_fast_forward`, admin bypass) protects `main`; don't force-push.
- **HACS installs tagged releases.** After merging, create a GitHub release (`gh release create vX.Y.Z --target main`) and bump `manifest.json` `version`. Without a release tag, HACS users won't get the update.
- The domain is `fronius_symo_modbus` (do **not** rename to `fronius_modbus` — that collides with the unrelated `redpomodoro/fronius_modbus` project and breaks HACS).

## Gotchas

- **Datamanager is slow**: a full poll is ~0.85–1.3 s and the device caps at ~1 read/s. `MIN_SCAN_INTERVAL` is 5 s for good reason; don't lower it.
- **Don't over-read**: always discover via the header-walk; a bulk read spanning past the chain end returns a Modbus error.
- **Not-implemented values** are normal (e.g. cabinet/string temperature is NaN on some firmware) → decoders return `None` and the sensor stays unavailable.
- **Hardware tested** so far only against a Symo Advanced 10.0-3-M in the **float** (113) layout with **2 MPPT strings**; the int+SF path is unit-tested but not hardware-verified. The active-power-limit **write path is hardware-verified** on this device (setting 50 % throttled AC output from ~6.9 kW to ~5.0 kW and reset cleanly).
- **Aggregate DC current/voltage**: this firmware reports model-113 `dc_current`/`dc_voltage` as NaN (only `dc_power` is filled). `coordinator._derive_dc_aggregates` fills `dc_current` from the per-string sum; no aggregate DC voltage is exposed by design.
- **Control writes (model 123)**: gated behind the options toggle `enable_control` (default off) **and** require *"inverter control via Modbus"* enabled on the Datamanager — otherwise `write_register` is rejected and surfaces as `HomeAssistantError`. Only the active-power limit is implemented; connect/disconnect and power factor are intentionally left out. Smart Meter (2xx) is not present on the test device.
