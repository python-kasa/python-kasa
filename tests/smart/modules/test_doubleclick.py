"""Tests for smart double click module."""

from __future__ import annotations

from kasa import Device
from kasa.smartcam.smartcammodule import SmartModule

from ...device_fixtures import parametrize

doubleclick = parametrize(
    "has double click", component_filter="double_click", protocol_filter={"SMART.CHILD"}
)


@doubleclick
async def test_doubleclick(dev: Device):
    """Test device double click."""
    doubleclick = dev.modules.get(SmartModule.SmartDoubleClick)
    assert doubleclick

    dc_feat = dev.features.get("double_click")
    assert dc_feat

    original_enabled = doubleclick.enabled

    try:
        await doubleclick.set_enabled(not original_enabled)
        await dev.update()
        assert doubleclick.enabled is not original_enabled
        assert dc_feat.value is not original_enabled

        await doubleclick.set_enabled(original_enabled)
        await dev.update()
        assert doubleclick.enabled is original_enabled
        assert dc_feat.value is original_enabled

        await dc_feat.set_value(not original_enabled)
        await dev.update()
        assert doubleclick.enabled is not original_enabled
        assert dc_feat.value is not original_enabled

    finally:
        await doubleclick.set_enabled(original_enabled)
