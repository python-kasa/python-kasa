"""Tests for smartcam meow detection module."""

from __future__ import annotations

from kasa import Device
from kasa.smartcam.smartcammodule import SmartCamModule

from ...device_fixtures import parametrize

meowdetection = parametrize(
    "has meow detection",
    component_filter="meowDetection",
    protocol_filter={"SMARTCAM"},
)


@meowdetection
async def test_meowdetection(dev: Device):
    """Test device meow detection."""
    meow = dev.modules.get(SmartCamModule.SmartCamMeowDetection)
    assert meow

    pde_feat = dev.features.get("meow_detection")
    assert pde_feat

    original_enabled = meow.enabled

    try:
        await meow.set_enabled(not original_enabled)
        await dev.update()
        assert meow.enabled is not original_enabled
        assert pde_feat.value is not original_enabled

        await meow.set_enabled(original_enabled)
        await dev.update()
        assert meow.enabled is original_enabled
        assert pde_feat.value is original_enabled

        await pde_feat.set_value(not original_enabled)
        await dev.update()
        assert meow.enabled is not original_enabled
        assert pde_feat.value is not original_enabled

    finally:
        await meow.set_enabled(original_enabled)
