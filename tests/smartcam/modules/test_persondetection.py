"""Tests for smartcam person detection module."""

from __future__ import annotations

from kasa import Device
from kasa.smartcam.smartcammodule import SmartCamModule

from ...device_fixtures import parametrize

persondetection = parametrize(
    "has person detection",
    component_filter="personDetection",
    protocol_filter={"SMARTCAM"},
)


@persondetection
async def test_persondetection(dev: Device):
    """Test device person detection."""
    person = dev.modules.get(SmartCamModule.SmartCamPersonDetection)
    assert person

    pde_feat = dev.features.get("person_detection_enabled")
    assert pde_feat

    original_enabled = person.enabled

    try:
        await person.set_enabled(not original_enabled)
        await dev.update()
        assert person.enabled is not original_enabled
        assert pde_feat.value is not original_enabled

        await person.set_enabled(original_enabled)
        await dev.update()
        assert person.enabled is original_enabled
        assert pde_feat.value is original_enabled

        await pde_feat.set_value(not original_enabled)
        await dev.update()
        assert person.enabled is not original_enabled
        assert pde_feat.value is not original_enabled

    finally:
        await person.set_enabled(original_enabled)
