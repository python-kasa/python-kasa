"""Tests for smartcam baby cry detection module."""

from __future__ import annotations

from kasa import Device
from kasa.smartcam.smartcammodule import SmartCamModule

from ...device_fixtures import parametrize

babycrydetection = parametrize(
    "has babycry detection",
    component_filter="babyCryDetection",
    protocol_filter={"SMARTCAM"},
)


@babycrydetection
async def test_babycrydetection(dev: Device):
    """Test device babycry detection."""
    babycry = dev.modules.get(SmartCamModule.SmartCamBabyCryDetection)
    assert babycry

    bcde_feat = dev.features.get("baby_cry_detection_enabled")
    assert bcde_feat

    original_enabled = babycry.enabled

    try:
        await babycry.set_enabled(not original_enabled)
        await dev.update()
        assert babycry.enabled is not original_enabled
        assert bcde_feat.value is not original_enabled

        await babycry.set_enabled(original_enabled)
        await dev.update()
        assert babycry.enabled is original_enabled
        assert bcde_feat.value is original_enabled

        await bcde_feat.set_value(not original_enabled)
        await dev.update()
        assert babycry.enabled is not original_enabled
        assert bcde_feat.value is not original_enabled

    finally:
        await babycry.set_enabled(original_enabled)
