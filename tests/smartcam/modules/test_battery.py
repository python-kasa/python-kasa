"""Tests for smartcam battery module."""

from __future__ import annotations

from kasa import Device
from kasa.smartcam.smartcammodule import SmartCamModule

from ...device_fixtures import doorlock_smartcam, parametrize, parametrize_subtract

battery_smartcam = parametrize(
    "has battery",
    component_filter="battery",
    protocol_filter={"SMARTCAM", "SMARTCAM.CHILD"},
)
# Exclude door locks as they have incomplete battery data
battery_smartcam = parametrize_subtract(battery_smartcam, doorlock_smartcam)


@battery_smartcam
async def test_battery(dev: Device):
    """Test device battery."""
    battery = dev.modules.get(SmartCamModule.SmartCamBattery)
    assert battery

    feat_ids = {
        "battery_level",
        "battery_low",
    }
    for feat_id in feat_ids:
        feat = dev.features.get(feat_id)
        assert feat
        assert feat.value is not None

    # These features may not be available on all devices (e.g., door locks)
    optional_feat_ids = {
        "battery_temperature",
        "battery_voltage",
        "battery_charging",
    }
    for feat_id in optional_feat_ids:
        feat = dev.features.get(feat_id)
        if feat:
            # Just check it can be accessed, value may be None
            _ = feat.value
