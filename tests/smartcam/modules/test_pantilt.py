"""Tests for PanTilt module."""

from __future__ import annotations

import pytest
from pytest_mock import MockerFixture

from kasa import Device, Module

from ...device_fixtures import parametrize

pantilt = parametrize(
    "has pantilt", component_filter="ptz", protocol_filter={"SMARTCAM"}
)


@pantilt
async def test_pantilt_presets(dev: Device, mocker: MockerFixture):
    """Test PanTilt module preset functionality."""
    pantilt_mod = dev.modules.get(Module.PanTilt)
    assert pantilt_mod is not None

    presets = pantilt_mod.presets
    if not presets:
        pytest.skip("Device has no presets configured")

    assert "ptz_preset" in dev.features
    preset_feature = dev.features["ptz_preset"]
    assert preset_feature is not None

    first_preset_name = next(iter(presets.keys()))
    assert preset_feature.value == first_preset_name

    mock_protocol_query = mocker.patch.object(dev.protocol, "query")
    mock_protocol_query.return_value = {}

    await preset_feature.set_value(first_preset_name)

    mock_protocol_query.assert_called_once()
    call_args = mock_protocol_query.call_args
    assert "motorMoveToPreset" in str(call_args)


@pantilt
async def test_pantilt_save_preset(dev: Device, mocker: MockerFixture):
    """Test PanTilt save_preset functionality."""
    pantilt_mod = dev.modules.get(Module.PanTilt)
    assert pantilt_mod is not None

    mock_protocol_query = mocker.patch.object(dev.protocol, "query")
    mock_protocol_query.return_value = {}

    await pantilt_mod.save_preset("NewPreset")

    mock_protocol_query.assert_called_with(
        request={
            "addMotorPostion": {
                "preset": {"set_preset": {"name": "NewPreset", "save_ptz": "1"}}
            }
        }
    )


@pantilt
async def test_pantilt_invalid_preset(dev: Device, mocker: MockerFixture):
    """Test set_preset with invalid preset name raises ValueError."""
    pantilt_mod = dev.modules.get(Module.PanTilt)
    assert pantilt_mod is not None

    if not pantilt_mod.presets:
        pytest.skip("Device has no presets configured")

    preset_feature = dev.features.get("ptz_preset")
    if not preset_feature:
        pytest.skip("Device has no preset feature")

    mocker.patch.object(dev.protocol, "query", return_value={})

    with pytest.raises(ValueError, match="Unexpected value"):
        await preset_feature.set_value("NonExistentPreset12345")


@pantilt
async def test_pantilt_move(dev: Device, mocker: MockerFixture):
    """Test PanTilt move commands."""
    pantilt_mod = dev.modules.get(Module.PanTilt)
    assert pantilt_mod is not None

    mock_protocol_query = mocker.patch.object(dev.protocol, "query")
    mock_protocol_query.return_value = {}

    await pantilt_mod.pan(30)
    call_args = mock_protocol_query.call_args
    assert "motor" in str(call_args)
    assert "move" in str(call_args)

    mock_protocol_query.reset_mock()

    await pantilt_mod.tilt(10)
    call_args = mock_protocol_query.call_args
    assert "motor" in str(call_args)
    assert "move" in str(call_args)


@pantilt
async def test_pantilt_goto_preset(dev: Device, mocker: MockerFixture):
    """Test PanTilt goto_preset command."""
    pantilt_mod = dev.modules.get(Module.PanTilt)
    assert pantilt_mod is not None

    mock_protocol_query = mocker.patch.object(dev.protocol, "query")
    mock_protocol_query.return_value = {}

    await pantilt_mod.goto_preset("1")

    mock_protocol_query.assert_called_with(
        request={"motorMoveToPreset": {"preset": {"goto_preset": {"id": "1"}}}}
    )


@pantilt
async def test_pantilt_get_presets(dev: Device, mocker: MockerFixture):
    """Test PanTilt get_presets command."""
    pantilt_mod = dev.modules.get(Module.PanTilt)
    assert pantilt_mod is not None

    mock_protocol_query = mocker.patch.object(dev.protocol, "query")
    mock_protocol_query.return_value = {}

    await pantilt_mod.get_presets()

    mock_protocol_query.assert_called_with(
        request={"getPresetConfig": {"preset": {"name": ["preset"]}}}
    )


@pantilt
async def test_pantilt_set_preset_by_id(dev: Device, mocker: MockerFixture):
    """Test set_preset with preset ID instead of name."""
    pantilt_mod = dev.modules.get(Module.PanTilt)
    assert pantilt_mod is not None

    if not pantilt_mod.presets:
        pytest.skip("Device has no presets configured")

    mock_protocol_query = mocker.patch.object(dev.protocol, "query")
    mock_protocol_query.return_value = {}

    # Get the first preset ID
    first_preset_id = next(iter(pantilt_mod.presets.values()))

    # Call set_preset with ID instead of name
    await pantilt_mod.set_preset(first_preset_id)

    mock_protocol_query.assert_called_with(
        request={
            "motorMoveToPreset": {"preset": {"goto_preset": {"id": first_preset_id}}}
        }
    )


@pantilt
async def test_pantilt_set_preset_not_found(dev: Device, mocker: MockerFixture):
    """Test set_preset with non-existent preset returns empty dict."""
    pantilt_mod = dev.modules.get(Module.PanTilt)
    assert pantilt_mod is not None

    mock_protocol_query = mocker.patch.object(dev.protocol, "query")
    mock_protocol_query.return_value = {}

    # Call set_preset with a non-existent preset
    result = await pantilt_mod.set_preset("NonExistentPreset99999")

    # Should return empty dict and not call API
    assert result == {}
    mock_protocol_query.assert_not_called()


@pantilt
async def test_pantilt_step_features(dev: Device, mocker: MockerFixture):
    """Test pan/tilt step features."""
    pantilt_mod = dev.modules.get(Module.PanTilt)
    assert pantilt_mod is not None

    # Test pan_step feature
    pan_step_feature = dev.features.get("pan_step")
    assert pan_step_feature is not None
    assert pan_step_feature.value == 30  # DEFAULT_PAN_STEP

    await pan_step_feature.set_value(45)
    assert pantilt_mod._pan_step == 45

    # Test tilt_step feature
    tilt_step_feature = dev.features.get("tilt_step")
    assert tilt_step_feature is not None
    assert tilt_step_feature.value == 10  # DEFAULT_TILT_STEP

    await tilt_step_feature.set_value(20)
    assert pantilt_mod._tilt_step == 20


@pantilt
async def test_pantilt_no_presets_in_data(dev: Device, mocker: MockerFixture):
    """Test _presets returns empty dict when no preset data."""
    pantilt_mod = dev.modules.get(Module.PanTilt)
    assert pantilt_mod is not None

    # Mock data property to return empty dict (no preset key)
    mocker.patch.object(type(pantilt_mod), "data", property(lambda self: {}))

    assert pantilt_mod._presets == {}
    assert pantilt_mod.presets == {}
