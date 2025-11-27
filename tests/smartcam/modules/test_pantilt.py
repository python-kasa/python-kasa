"""Tests for PanTilt module."""

from __future__ import annotations

import pytest

from kasa import Device, Module

from ...conftest import device_smartcam


@device_smartcam
async def test_pantilt(dev: Device):
    """Test PanTilt module."""
    pantilt = dev.modules.get(Module.PanTilt)
    if not pantilt:
        pytest.skip("Device does not support PanTilt")

    # Test get_presets
    presets = await pantilt.get_presets()
    assert presets is not None
    # The fixture C210(EU)_1.0_1.4.7.json has presets: Default, Door, Mid
    # We can check if the response structure is correct
    # The mock protocol returns what is in the fixture for the request.
    # Since we added the fixture with the responses, it should work.

    # Test goto_preset
    # We need to pick a valid preset ID from the fixture or just any ID if the mock is simple
    # In the fixture:
    # 'getPresetConfig': {'preset': {'preset': {'id': ['1', '2', '3'], ...}}}
    # So we can try goto_preset('1')

    await pantilt.goto_preset("1")

    # Test save_preset
    await pantilt.save_preset("NewPreset")
