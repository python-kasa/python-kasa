"""Tests for smartcam tamper detection module."""

from __future__ import annotations

from kasa import Device
from kasa.smartcam.smartcammodule import SmartCamModule

from ...device_fixtures import parametrize

tamperdetection = parametrize(
    "has tamper detection",
    component_filter="tamperDetection",
    protocol_filter={"SMARTCAM"},
)


@tamperdetection
async def test_tamperdetection(dev: Device):
    """Test device tamper detection."""
    tamper = dev.modules.get(SmartCamModule.SmartCamTamperDetection)
    assert tamper

    tde_feat = dev.features.get("tamper_detection_enabled")
    assert tde_feat

    original_enabled = tamper.enabled

    try:
        await tamper.set_enabled(not original_enabled)
        await dev.update()
        assert tamper.enabled is not original_enabled
        assert tde_feat.value is not original_enabled

        await tamper.set_enabled(original_enabled)
        await dev.update()
        assert tamper.enabled is original_enabled
        assert tde_feat.value is original_enabled

        await tde_feat.set_value(not original_enabled)
        await dev.update()
        assert tamper.enabled is not original_enabled
        assert tde_feat.value is not original_enabled

    finally:
        await tamper.set_enabled(original_enabled)
