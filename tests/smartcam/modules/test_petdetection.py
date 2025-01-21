"""Tests for smartcam pet detection module."""

from __future__ import annotations

from kasa import Device
from kasa.smartcam.smartcammodule import SmartCamModule

from ...device_fixtures import parametrize

petdetection = parametrize(
    "has pet detection",
    component_filter="petDetection",
    protocol_filter={"SMARTCAM"},
)


@petdetection
async def test_petdetection(dev: Device):
    """Test device pet detection."""
    pet = dev.modules.get(SmartCamModule.SmartCamPetDetection)
    assert pet

    pde_feat = dev.features.get("pet_detection")
    assert pde_feat

    original_enabled = pet.enabled

    try:
        await pet.set_enabled(not original_enabled)
        await dev.update()
        assert pet.enabled is not original_enabled
        assert pde_feat.value is not original_enabled

        await pet.set_enabled(original_enabled)
        await dev.update()
        assert pet.enabled is original_enabled
        assert pde_feat.value is original_enabled

        await pde_feat.set_value(not original_enabled)
        await dev.update()
        assert pet.enabled is not original_enabled
        assert pde_feat.value is not original_enabled

    finally:
        await pet.set_enabled(original_enabled)
