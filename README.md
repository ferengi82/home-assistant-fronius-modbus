# Fronius Symo Modbus — Home Assistant Integration

A custom [Home Assistant](https://www.home-assistant.io/) integration that reads
**Fronius Symo (Advanced)** inverters over **Modbus TCP** using the SunSpec
register map exposed by the Fronius Datamanager card.

Everything is configured from the Home Assistant UI — no YAML required.

> **Scope (v1):** read-only. Inverter measurements + device/nameplate
> information. Modbus TCP only (no RTU), no control/writing, and no Smart Meter
> entities yet. The architecture leaves room to add those later.

## Features

- 🔌 Modbus TCP, fully GUI-configurable (IP, port, unit ID, scan interval)
- 🧭 **Automatic SunSpec model discovery** — works with both the `float`
  (models 111/112/113) and `int+SF` (models 101/102/103) layouts the
  Datamanager can be set to, without hardcoded register addresses
- ⚡ Sensors: AC power, lifetime energy (Energy Dashboard ready), AC current,
  per-phase voltage, grid frequency, apparent/reactive power, power factor,
  DC power/voltage/current, cabinet temperature, operating state
- 🏷️ Device info from the SunSpec common block (manufacturer, model, serial,
  firmware) plus diagnostic nameplate sensors (rated power/current)

## Prerequisites

On the inverter's **Fronius Datamanager** web interface, open
**Settings → Modbus** and:

1. Enable **Modbus TCP** (default port `502`).
2. Note the **SunSpec Model Type** (`float` is the default; `int+SF` also works —
   the integration auto-detects either).

## Installation

### HACS (custom repository)

1. In HACS, open the three-dot menu → **Custom repositories**.
2. Add `https://github.com/ferengi82/home-assistant-fronius-modbus` with
   category **Integration**.
3. Install **Fronius Symo Modbus** and restart Home Assistant.

### Manual

Copy `custom_components/fronius_modbus` into your Home Assistant
`config/custom_components/` directory and restart.

## Configuration

**Settings → Devices & Services → Add Integration → Fronius Symo Modbus**

| Option | Default | Description |
| --- | --- | --- |
| Host / IP address | — | Inverter / Datamanager IP |
| Name | `Fronius Symo` | Device name in HA |
| Modbus TCP port | `502` | As configured on the Datamanager |
| Modbus unit / slave ID | `1` | Inverter Modbus ID |
| Scan interval | `30` s | Poll frequency (changeable later via the entry's options) |

## Verifying against your inverter

A standalone helper dumps the discovered SunSpec models and decoded values
straight from the device (no Home Assistant required):

```bash
pip install pymodbus
python scripts/dump_sunspec.py <inverter-ip> [--port 502] [--unit 1]
```

## Notes

- A custom integration icon/logo requires a separate submission to the
  [home-assistant/brands](https://github.com/home-assistant/brands) repository;
  until then Home Assistant shows a default icon.
- Reference for the GEN24 family (different device, similar approach):
  [redpomodoro/fronius_modbus](https://github.com/redpomodoro/fronius_modbus).

## License

[MIT](LICENSE)
