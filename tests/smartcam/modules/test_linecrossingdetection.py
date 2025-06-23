"""Tests for smartcam line crossing detection module."""

from __future__ import annotations

from kasa import Device
from kasa.smartcam.smartcammodule import SmartCamModule

from ...device_fixtures import parametrize

linecrossingdetection = parametrize(
    "has line crossing detection",
    component_filter="linecrossingDetection",
    protocol_filter={"SMARTCAM"},
    model_filter="C220(EU)_1.0_1.2.5",
)


@linecrossingdetection
async def test_line_crossing_detection(dev: Device):
    """Test device line crossing detection."""
    linecrossing = dev.modules.get(SmartCamModule.SmartCamLineCrossingDetection)
    assert linecrossing

    pde_feat = dev.features.get("line_crossing_detection")
    assert pde_feat

    original_enabled = linecrossing.enabled

    try:
        await linecrossing.set_enabled(not original_enabled)
        await dev.update()
        assert linecrossing.enabled is not original_enabled
        assert pde_feat.value is not original_enabled

        await linecrossing.set_enabled(original_enabled)
        await dev.update()
        assert linecrossing.enabled is original_enabled
        assert pde_feat.value is original_enabled

        await pde_feat.set_value(not original_enabled)
        await dev.update()
        assert linecrossing.enabled is not original_enabled
        assert pde_feat.value is not original_enabled

    finally:
        await linecrossing.set_enabled(original_enabled)
