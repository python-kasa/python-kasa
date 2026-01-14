"""Tests for smartcam battery module."""

from __future__ import annotations

import pytest

from kasa import Device
from kasa.smartcam.smartcammodule import SmartCamModule

from ...device_fixtures import parametrize

battery_smartcam = parametrize(
    "has battery",
    component_filter="battery",
    protocol_filter={"SMARTCAM", "SMARTCAM.CHILD"},
)


@battery_smartcam
async def test_battery(dev: Device):
    """Test device battery."""
    battery = dev.modules.get(SmartCamModule.SmartCamBattery)
    assert battery

    required = {"battery_level", "battery_low", "battery_charging"}
    optional = {"battery_temperature", "battery_voltage"}

    for feat_id in required:
        feat = dev.features.get(feat_id)
        assert feat
        assert feat.value is not None

    for feat_id in optional:
        feat = dev.features.get(feat_id)
        if feat is not None:
            assert feat.value is not None


@battery_smartcam
@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        (None, None),  # covers: v in (None, "NO") -> return None
        ("NO", None),  # covers: v in (None, "NO") -> return None
        ("nonsense", None),  # covers: ValueError -> except -> return None
        ("12.3", 12.3),  # sanity: happy path
    ],
)
async def test_battery_temperature_edge_cases(dev: Device, raw, expected):
    battery = dev.modules.get(SmartCamModule.SmartCamBattery)
    assert battery

    dev.sys_info["battery_temperature"] = raw
    assert battery.battery_temperature == expected


@battery_smartcam
@pytest.mark.parametrize(
    ("voltage_raw", "expected_v"),
    [
        (None, None),  # covers: battery_voltage -> return None
        ("NO", None),  # covers: battery_voltage -> return None
        ("12000", 12.0),  # sanity: parses string -> float(...) / 1000
    ],
)
async def test_battery_voltage_edge_cases(dev: Device, voltage_raw, expected_v):
    battery = dev.modules.get(SmartCamModule.SmartCamBattery)
    assert battery

    dev.sys_info["battery_voltage"] = voltage_raw
    assert battery.battery_voltage == expected_v


@battery_smartcam
@pytest.mark.parametrize(
    ("charging_raw", "expected"),
    [
        (True, True),  # covers: isinstance(v, bool) -> return v
        (False, False),  # covers: isinstance(v, bool) -> return v
        (None, False),  # covers: v is None -> return False
        ("yes", True),  # sanity: string normalization path
        ("NO", False),  # sanity: string normalization path
    ],
)
async def test_battery_charging_edge_cases(dev: Device, charging_raw, expected):
    battery = dev.modules.get(SmartCamModule.SmartCamBattery)
    assert battery

    dev.sys_info["battery_charging"] = charging_raw
    assert battery.battery_charging is expected
