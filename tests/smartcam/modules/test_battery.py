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
