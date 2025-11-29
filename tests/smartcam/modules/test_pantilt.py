"""Tests for PanTilt module."""

from __future__ import annotations

import pytest
from pytest_mock import MockerFixture

from kasa import Device, Module

from ...conftest import device_smartcam


@device_smartcam
async def test_pantilt(dev: Device, mocker: MockerFixture):
    """Test PanTilt module."""
    pantilt = dev.modules.get(Module.PanTilt)
    if not pantilt:
        pytest.skip("Device does not support PanTilt")

    mock_protocol_query = mocker.spy(dev.protocol, "query")

    # Test get_presets
    presets = await pantilt.get_presets()
    assert presets is not None
    assert "getPresetConfig" in presets
    assert "preset" in presets["getPresetConfig"]
    assert "preset" in presets["getPresetConfig"]["preset"]
    preset_data = presets["getPresetConfig"]["preset"]["preset"]
    assert "id" in preset_data
    assert "name" in preset_data
    assert len(preset_data["id"]) == len(preset_data["name"])

    # Test goto_preset - use a preset from the actual response
    if preset_data["id"]:
        first_preset_id = preset_data["id"][0]
        await pantilt.goto_preset(first_preset_id)

        mock_protocol_query.assert_called_with(
            request={
                "motorMoveToPreset": {
                    "preset": {"goto_preset": {"id": first_preset_id}}
                }
            }
        )

    # Test save_preset
    await pantilt.save_preset("NewPreset")

    # Note: The Tapo API has a typo in the method name (addMotorPostion instead of addMotorPosition)
    mock_protocol_query.assert_called_with(
        request={
            "addMotorPostion": {
                "preset": {"set_preset": {"name": "NewPreset", "save_ptz": "1"}}
            }
        }
    )


@device_smartcam
async def test_pantilt_no_presets(dev: Device, mocker: MockerFixture):
    """Test PanTilt module behavior when no presets are configured."""
    pantilt = dev.modules.get(Module.PanTilt)
    if not pantilt:
        pytest.skip("Device does not support PanTilt")

    # Mock empty presets response
    mocker.patch.object(
        dev,
        "_query_helper",
        return_value={"preset": {"preset": {"id": [], "name": []}}},
    )

    # Trigger update to refresh presets
    await dev.update()

    # When no presets exist, the preset feature should not be added
    preset_feature = dev.features.get("preset")
    assert preset_feature is None
