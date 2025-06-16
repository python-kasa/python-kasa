"""Tests for smartcam vehicle detection module."""

from __future__ import annotations

from kasa import Device
from kasa.smartcam.smartcammodule import SmartCamModule

from ...device_fixtures import parametrize

vehicledetection = parametrize(
    "has vehicle detection",
    component_filter="vehicleDetection",
    protocol_filter={"SMARTCAM"},
)


@vehicledetection
async def test_vehicledetection(dev: Device):
    """Test device vehicle detection."""
    vehicle = dev.modules.get(SmartCamModule.SmartCamVehicleDetection)
    assert vehicle

    pde_feat = dev.features.get("vehicle_detection")
    assert pde_feat

    original_enabled = vehicle.enabled

    try:
        await vehicle.set_enabled(not original_enabled)
        await dev.update()
        assert vehicle.enabled is not original_enabled
        assert pde_feat.value is not original_enabled

        await vehicle.set_enabled(original_enabled)
        await dev.update()
        assert vehicle.enabled is original_enabled
        assert pde_feat.value is original_enabled

        await pde_feat.set_value(not original_enabled)
        await dev.update()
        assert vehicle.enabled is not original_enabled
        assert pde_feat.value is not original_enabled

    finally:
        await vehicle.set_enabled(original_enabled)
