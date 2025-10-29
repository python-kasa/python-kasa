"""Tests for smartcam battery module."""

from __future__ import annotations

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
