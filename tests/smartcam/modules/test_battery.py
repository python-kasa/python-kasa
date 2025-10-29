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

    feat_ids = {
        "battery_level",
        "battery_low",
        "battery_temperature",
        "battery_voltage",
        "battery_charging",
    }
    for feat_id in feat_ids:
        feat = dev.features.get(feat_id)
        assert feat
        assert feat.value is not None


@battery_smartcam
async def test_battery_branches(dev: Device):
    """Exercise various battery property branches not covered by fixtures."""
    battery = dev.modules.get(SmartCamModule.SmartCamBattery)
    assert battery

    # Keep original sys_info and restore after test
    orig_sys = dict(battery._device.sys_info)
    try:
        # helper to replace the dict contents without rebinding the property
        def set_sys(d: dict):
            battery._device.sys_info.clear()
            battery._device.sys_info.update(d)

        # battery_temperature: reported
        set_sys({"battery_temperature": 12})
        assert battery.battery_temperature == 12

        # battery_temperature: not reported -> fallback 0
        set_sys({"battery_temperature": None})
        assert battery.battery_temperature == 0

        # battery_voltage: not available and no percent -> None
        set_sys({"battery_voltage": None, "battery_percent": None})
        assert battery.battery_voltage is None

        # battery_voltage: derive from battery_percent (50%)
        set_sys({"battery_voltage": None, "battery_percent": 50})
        assert battery.battery_voltage == pytest.approx(3.0 + (50.0 / 100.0) * 1.2)

        # battery_voltage: explicit NO and percent present
        set_sys({"battery_voltage": "NO", "battery_percent": 75})
        assert battery.battery_voltage == pytest.approx(3.0 + (75.0 / 100.0) * 1.2)

        # battery_voltage: numeric millivolts
        set_sys({"battery_voltage": 4022})
        assert battery.battery_voltage == pytest.approx(4.022)

        # battery_voltage: string numeric
        set_sys({"battery_voltage": "4022"})
        assert battery.battery_voltage == pytest.approx(4.022)

        # battery_voltage: unparseable string -> None
        set_sys({"battery_voltage": "N/A", "battery_percent": None})
        assert battery.battery_voltage is None

        # battery_charging: explicit boolean
        set_sys({"battery_charging": True})
        assert battery.battery_charging is True
        set_sys({"battery_charging": False})
        assert battery.battery_charging is False

        # battery_charging: explicit strings
        set_sys({"battery_charging": "NO"})
        assert battery.battery_charging is False
        set_sys({"battery_charging": "YES"})
        assert battery.battery_charging is True

        # battery_charging: fallback to voltage presence
        set_sys({"battery_charging": None, "battery_voltage": None})
        assert battery.battery_charging is False
        set_sys({"battery_charging": None, "battery_voltage": "NO"})
        assert battery.battery_charging is False
        set_sys({"battery_charging": None, "battery_voltage": 4000})
        assert battery.battery_charging is True

        # battery_percent and battery_low simple getters
        set_sys({"battery_percent": 42, "low_battery": True})
        assert battery.battery_percent == 42
        assert battery.battery_low is True
    finally:
        battery._device.sys_info.clear()
        battery._device.sys_info.update(orig_sys)
