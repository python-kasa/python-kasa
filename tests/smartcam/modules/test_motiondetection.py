"""Tests for smartcam motion detection module."""

from __future__ import annotations

from kasa import Device
from kasa.smartcam.smartcammodule import SmartCamModule

from ...device_fixtures import parametrize

motiondetection = parametrize(
    "has motion detection", component_filter="detection", protocol_filter={"SMARTCAM"}
)


@motiondetection
async def test_motiondetection(dev: Device):
    """Test device motion detection."""
    motion = dev.modules.get(SmartCamModule.SmartCamMotionDetection)
    assert motion

    mde_feat = dev.features.get("motion_detection_enabled")
    assert mde_feat

    original_enabled = motion.enabled

    try:
        await motion.set_enabled(not original_enabled)
        await dev.update()
        assert motion.enabled is not original_enabled
        assert mde_feat.value is not original_enabled

        await motion.set_enabled(original_enabled)
        await dev.update()
        assert motion.enabled is original_enabled
        assert mde_feat.value is original_enabled

        await mde_feat.set_value(not original_enabled)
        await dev.update()
        assert motion.enabled is not original_enabled
        assert mde_feat.value is not original_enabled

    finally:
        await motion.set_enabled(original_enabled)
