"""Tests for smartcam bark detection module."""

from __future__ import annotations

from kasa import Device
from kasa.smartcam.smartcammodule import SmartCamModule

from ...device_fixtures import parametrize

barkdetection = parametrize(
    "has bark detection",
    component_filter="barkDetection",
    protocol_filter={"SMARTCAM"},
)


@barkdetection
async def test_barkdetection(dev: Device):
    """Test device bark detection."""
    bark = dev.modules.get(SmartCamModule.SmartCamBarkDetection)
    assert bark

    pde_feat = dev.features.get("bark_detection")
    assert pde_feat

    original_enabled = bark.enabled

    try:
        await bark.set_enabled(not original_enabled)
        await dev.update()
        assert bark.enabled is not original_enabled
        assert pde_feat.value is not original_enabled

        await bark.set_enabled(original_enabled)
        await dev.update()
        assert bark.enabled is original_enabled
        assert pde_feat.value is original_enabled

        await pde_feat.set_value(not original_enabled)
        await dev.update()
        assert bark.enabled is not original_enabled
        assert pde_feat.value is not original_enabled

    finally:
        await bark.set_enabled(original_enabled)
