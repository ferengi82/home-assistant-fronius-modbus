#!/usr/bin/env python3
"""Dump the SunSpec model chain and decoded inverter values from a Fronius device.

Standalone diagnostic tool — requires only ``pymodbus`` (no Home Assistant).
Use it to verify connectivity and the register map against a real Symo Advanced.

    pip install pymodbus
    python scripts/dump_sunspec.py 192.168.1.50 --port 502 --unit 1
"""

from __future__ import annotations

import argparse
import asyncio
import struct

from pymodbus.client import AsyncModbusTcpClient

BASE = 40000
MARKER = 0x53756E53
END = 0xFFFF


async def read_block(client, address, count, unit):
    """Read holding registers in <=124 register chunks."""
    regs = []
    off = 0
    while off < count:
        chunk = min(124, count - off)
        try:
            res = await client.read_holding_registers(address + off, count=chunk, slave=unit)
        except TypeError:
            res = await client.read_holding_registers(address + off, count=chunk, device_id=unit)
        if res.isError():
            raise SystemExit(f"Modbus error reading {address + off} (+{chunk}): {res}")
        regs.extend(res.registers)
        off += chunk
    return regs


def parse_chain(header):
    if ((header[0] << 16) | header[1]) != MARKER:
        raise SystemExit("No SunSpec 'SunS' marker found at base register 40001.")
    models = {}
    idx = 2
    while idx + 1 < len(header):
        mid, length = header[idx], header[idx + 1]
        if mid == END:
            break
        models[mid] = (BASE + idx + 2, length)
        idx += 2 + length
    return models


def s16(v):
    return v - 0x10000 if v >= 0x8000 else v


def f32(regs, off):
    return struct.unpack(">f", struct.pack(">HH", regs[off], regs[off + 1]))[0]


def decode_string(regs, off, length):
    raw = b"".join(struct.pack(">H", regs[off + i]) for i in range(length))
    return raw.split(b"\x00", 1)[0].decode("ascii", "ignore").strip()


async def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("host")
    ap.add_argument("--port", type=int, default=502)
    ap.add_argument("--unit", type=int, default=1)
    args = ap.parse_args()

    client = AsyncModbusTcpClient(args.host, port=args.port, timeout=10)
    if not await client.connect():
        raise SystemExit(f"Could not connect to {args.host}:{args.port}")

    header = await read_block(client, BASE, 180, args.unit)
    models = parse_chain(header)

    print(f"Discovered SunSpec models: {sorted(models)}")
    for mid in sorted(models):
        addr, length = models[mid]
        print(f"  model {mid:>5}: data @ {addr}, length {length}")

    if 1 in models:
        addr, length = models[1]
        block = await read_block(client, addr, length, args.unit)
        print("\nCommon block:")
        print("  Manufacturer:", decode_string(block, 0, 16))
        print("  Model       :", decode_string(block, 16, 16))
        print("  Version     :", decode_string(block, 40, 8))
        print("  Serial      :", decode_string(block, 48, 16))

    inv = next((m for m in (101, 102, 103, 111, 112, 113) if m in models), None)
    if inv:
        addr, length = models[inv]
        block = await read_block(client, addr, length, args.unit)
        print(f"\nInverter model {inv} ({'float' if inv >= 111 else 'int+SF'}):")
        if inv >= 111:
            print(f"  AC power : {f32(block, 20):.1f} W")
            print(f"  Energy   : {f32(block, 30):.0f} Wh")
            print(f"  DC power : {f32(block, 36):.1f} W")
            print(f"  Temp     : {f32(block, 38):.1f} °C")
            print(f"  State    : {block[46]}")
        else:
            sf = lambda i: s16(block[i])  # noqa: E731
            print(f"  AC power : {s16(block[12]) * 10 ** sf(13):.1f} W")
            energy = (block[22] << 16) | block[23]
            print(f"  Energy   : {energy * 10 ** sf(24):.0f} Wh")
            print(f"  DC power : {s16(block[29]) * 10 ** sf(30):.1f} W")
            print(f"  Temp     : {s16(block[31]) * 10 ** sf(35):.1f} °C")
            print(f"  State    : {block[36]}")

    client.close()


if __name__ == "__main__":
    asyncio.run(main())
