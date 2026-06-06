"""Test fixtures: load the standalone sunspec module without Home Assistant."""

from __future__ import annotations

import importlib.util
import pathlib
import sys

import pytest

_SUNSPEC_PATH = (
    pathlib.Path(__file__).resolve().parents[1]
    / "custom_components"
    / "fronius_modbus"
    / "sunspec.py"
)


def _load_sunspec():
    spec = importlib.util.spec_from_file_location("fronius_sunspec", _SUNSPEC_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    # Register before exec so dataclasses can resolve the module by name.
    sys.modules["fronius_sunspec"] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="session")
def sunspec():
    """Return the loaded sunspec module."""
    return _load_sunspec()
