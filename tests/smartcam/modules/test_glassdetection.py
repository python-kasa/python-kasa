"""Tests for smartcam glass detection module."""

from __future__ import annotations

from kasa import Device
from kasa.smartcam.smartcammodule import SmartCamModule

from ...device_fixtures import parametrize

glassdetection = parametrize(
    "has glass detection",
    component_filter="glassDetection",
    protocol_filter={"SMARTCAM"},
)


@glassdetection
async def test_glassdetection(dev: Device):
    """Test device glass detection."""
    glass = dev.modules.get(SmartCamModule.SmartCamGlassDetection)
    assert glass

    pde_feat = dev.features.get("glass_detection")
    assert pde_feat

    original_enabled = glass.enabled

    try:
        await glass.set_enabled(not original_enabled)
        await dev.update()
        assert glass.enabled is not original_enabled
        assert pde_feat.value is not original_enabled

        await glass.set_enabled(original_enabled)
        await dev.update()
        assert glass.enabled is original_enabled
        assert pde_feat.value is original_enabled

        await pde_feat.set_value(not original_enabled)
        await dev.update()
        assert glass.enabled is not original_enabled
        assert pde_feat.value is not original_enabled

    finally:
        await glass.set_enabled(original_enabled)
