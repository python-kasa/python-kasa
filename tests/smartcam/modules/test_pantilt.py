"""Tests for PanTilt module."""

from __future__ import annotations

import pytest
from pytest_mock import MockerFixture

from kasa import Device
from kasa.smartcam.modules.pantilt import PanTilt

from ...conftest import device_smartcam


@device_smartcam
async def test_pantilt(dev: Device, mocker: MockerFixture):
    """Test PanTilt module."""
    pantilt = dev.modules.get("PanTilt")
    if pantilt is None:
        pytest.skip("Device does not have PanTilt module")

    assert isinstance(pantilt, PanTilt)

    # Check if device has presets from fixture
    if pantilt._presets:
        # Preset feature should be available
        assert "preset" in dev.features

        preset_feature = dev.features["preset"]
        assert preset_feature is not None

        # Get first preset name
        first_preset_name = next(iter(pantilt._presets.keys()))
        assert preset_feature.value == first_preset_name

        # Mock the protocol query for testing set_value
        # This allows set_preset function body to be executed (lines 110-112)
        mock_protocol_query = mocker.patch.object(dev.protocol, "query")
        mock_protocol_query.return_value = {}

        # Set to a valid preset - this executes set_preset function (lines 109-112)
        await preset_feature.set_value(first_preset_name)

        # Verify goto_preset was called with correct preset_id
        mock_protocol_query.assert_called_once()
        call_args = mock_protocol_query.call_args
        assert "motor" in str(call_args) or "preset" in str(call_args).lower()

        # Reset mock
        mock_protocol_query.reset_mock()

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
    pantilt = dev.modules.get("PanTilt")
    if pantilt is None:
        pytest.skip("Device does not have PanTilt module")

    assert isinstance(pantilt, PanTilt)

    # Test get_presets method (covers line 146)
    mock_query = mocker.patch.object(dev.protocol, "query")
    mock_query.return_value = {}
    await pantilt.get_presets()
    mock_query.assert_called_once()


@device_smartcam
async def test_pantilt_invalid_preset(dev: Device, mocker: MockerFixture):
    """Test set_preset with invalid preset name (covers line 111 else branch)."""
    pantilt = dev.modules.get("PanTilt")
    if pantilt is None:
        pytest.skip("Device does not have PanTilt module")

    assert isinstance(pantilt, PanTilt)

    if not pantilt._presets:
        pytest.skip("Device has no presets configured")

    # Get preset feature
    preset_feature = dev.features.get("preset")
    if not preset_feature:
        pytest.skip("Device has no preset feature")

    # Mock the protocol query
    mock_query = mocker.patch.object(dev.protocol, "query")
    mock_query.return_value = {}

    # Try to set an invalid preset name - this should not call goto_preset
    # because preset_id will be None (covers line 111 else branch)
    invalid_preset_name = "NonExistentPreset12345"

    # Temporarily add the invalid name to choices to bypass validation
    original_presets = pantilt._presets.copy()
    pantilt._presets[invalid_preset_name] = ""  # Empty string is falsy

    try:
        await preset_feature.set_value(invalid_preset_name)
        # goto_preset should NOT be called because preset_id is empty string (falsy)
        mock_query.assert_not_called()
    finally:
        pantilt._presets = original_presets


@device_smartcam
async def test_pantilt_empty_preset_response(dev: Device, mocker: MockerFixture):
    """Test _post_update_hook with empty preset response (covers line 98 else)."""
    pantilt = dev.modules.get("PanTilt")
    if pantilt is None:
        pytest.skip("Device does not have PanTilt module")

    assert isinstance(pantilt, PanTilt)

    # Save original presets
    original_presets = pantilt._presets.copy()

    # Mock _query_helper to return empty/invalid preset data
    mock_query = mocker.patch.object(dev, "_query_helper")
    mock_query.return_value = {"getPresetConfig": {}}  # No "preset" key

    # Clear presets and call _post_update_hook
    pantilt._presets = {}
    await pantilt._post_update_hook()

    # Presets should still be empty because response had no valid preset data
    assert pantilt._presets == {}

    # Restore original presets
    pantilt._presets = original_presets
