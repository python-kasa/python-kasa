from __future__ import annotations

import logging

import pytest
from pytest_mock import MockerFixture

from kasa import Module
from kasa.smart import SmartDevice
from kasa.smart.modules.clean import ErrorCode, Status

from ...device_fixtures import get_parent_and_child_modules, parametrize

clean = parametrize("clean module", component_filter="clean", protocol_filter={"SMART"})


@clean
@pytest.mark.parametrize(
    ("feature", "prop_name", "type"),
    [
        ("vacuum_status", "status", Status),
        ("vacuum_error", "error", ErrorCode),
        ("vacuum_fan_speed", "fan_speed_preset", str),
        ("carpet_boost", "carpet_boost", bool),
        ("battery_level", "battery", int),
        ("selected_map", "current_map", str),
    ],
)
async def test_features(dev: SmartDevice, feature: str, prop_name: str, type: type):
    """Test that features are registered and work as expected."""
    clean = next(get_parent_and_child_modules(dev, Module.Clean))
    assert clean is not None

    prop = getattr(clean, prop_name)
    assert isinstance(prop, type)

    feat = clean._device.features[feature]
    assert feat.value == prop
    assert isinstance(feat.value, type)


@pytest.mark.parametrize(
    ("feature", "value", "method", "params"),
    [
        pytest.param(
            "vacuum_start",
            1,
            "setSwitchClean",
            {
                "clean_mode": 0,
                "clean_on": True,
                "clean_order": True,
                "force_clean": False,
            },
            id="vacuum_start",
        ),
        pytest.param(
            "vacuum_pause", 1, "setRobotPause", {"pause": True}, id="vacuum_pause"
        ),
        pytest.param(
            "vacuum_return_home",
            1,
            "setSwitchCharge",
            {"switch_charge": True},
            id="vacuum_return_home",
        ),
        pytest.param(
            "vacuum_fan_speed",
            "Quiet",
            "setCleanAttr",
            {"suction": 1, "type": "global"},
            id="vacuum_fan_speed",
        ),
        pytest.param(
            "carpet_boost",
            True,
            "setCarpetClean",
            {"carpet_clean_prefer": "boost"},
            id="carpet_boost",
        ),
        pytest.param(
            "clean_count",
            2,
            "setCleanAttr",
            {"clean_number": 2, "type": "global"},
            id="clean_count",
        ),
    ],
)
@clean
async def test_actions(
    dev: SmartDevice,
    mocker: MockerFixture,
    feature: str,
    value: str | int,
    method: str,
    params: dict,
):
    """Test the clean actions."""
    clean = next(get_parent_and_child_modules(dev, Module.Clean))
    call = mocker.spy(clean, "call")

    await dev.features[feature].set_value(value)
    call.assert_called_with(method, params)


@pytest.mark.parametrize(
    ("err_status", "error", "warning_msg"),
    [
        pytest.param([], ErrorCode.Ok, None, id="empty error"),
        pytest.param([0], ErrorCode.Ok, None, id="no error"),
        pytest.param([3], ErrorCode.MainBrushStuck, None, id="known error"),
        pytest.param(
            [123],
            ErrorCode.UnknownInternal,
            "Unknown error code, please create an issue describing the error: 123",
            id="unknown error",
        ),
        pytest.param(
            [3, 4],
            ErrorCode.MainBrushStuck,
            "Multiple error codes, using the first one only: [3, 4]",
            id="multi-error",
        ),
    ],
)
@clean
async def test_post_update_hook(
    dev: SmartDevice,
    err_status: list,
    error: ErrorCode,
    warning_msg: str | None,
    caplog: pytest.LogCaptureFixture,
):
    """Test that post update hook sets error states correctly."""
    clean = next(get_parent_and_child_modules(dev, Module.Clean))
    assert clean

    caplog.set_level(logging.DEBUG)

    # _post_update_hook will pop an item off the status list so create a copy.
    err_status = [e for e in err_status]
    clean.data["getVacStatus"]["err_status"] = err_status

    await clean._post_update_hook()

    assert clean._error_code is error

    if error is not ErrorCode.Ok:
        assert clean.status is Status.Error

    if warning_msg:
        assert warning_msg in caplog.text

    # Check doesn't log twice
    caplog.clear()
    await clean._post_update_hook()

    if warning_msg:
        assert warning_msg not in caplog.text


@clean
async def test_resume(dev: SmartDevice, mocker: MockerFixture):
    """Test that start calls resume if the state is paused."""
    clean = next(get_parent_and_child_modules(dev, Module.Clean))

    call = mocker.spy(clean, "call")
    resume = mocker.spy(clean, "resume")

    mocker.patch.object(
        type(clean),
        "status",
        new_callable=mocker.PropertyMock,
        return_value=Status.Paused,
    )
    await clean.start()

    call.assert_called_with("setRobotPause", {"pause": False})
    resume.assert_awaited()


@clean
async def test_unknown_status(
    dev: SmartDevice, mocker: MockerFixture, caplog: pytest.LogCaptureFixture
):
    """Test that unknown status is logged."""
    clean = next(get_parent_and_child_modules(dev, Module.Clean))

    caplog.set_level(logging.DEBUG)
    clean.data["getVacStatus"]["status"] = 123

    assert clean.status is Status.UnknownInternal
    assert "Got unknown status code: 123" in caplog.text

    # Check only logs once
    caplog.clear()

    assert clean.status is Status.UnknownInternal
    assert "Got unknown status code: 123" not in caplog.text

    # Check logs again for other errors

    caplog.clear()
    clean.data["getVacStatus"]["status"] = 123456

    assert clean.status is Status.UnknownInternal
    assert "Got unknown status code: 123456" in caplog.text


@clean
@pytest.mark.parametrize(
    ("setting", "value", "exc", "exc_message"),
    [
        pytest.param(
            "vacuum_fan_speed",
            "invalid speed",
            ValueError,
            "Invalid fan speed",
            id="vacuum_fan_speed",
        ),
    ],
)
async def test_invalid_settings(
    dev: SmartDevice,
    mocker: MockerFixture,
    setting: str,
    value: str,
    exc: type[Exception],
    exc_message: str,
):
    """Test invalid settings."""
    clean = next(get_parent_and_child_modules(dev, Module.Clean))

    # Not using feature.set_value() as it checks for valid values
    setter_name = dev.features[setting].attribute_setter
    assert isinstance(setter_name, str)

    setter = getattr(clean, setter_name)

    with pytest.raises(exc, match=exc_message):
        await setter(value)


@clean
@pytest.mark.parametrize(
    ("map_info", "expected_current", "expected_available"),
    [
        pytest.param(
            {},
            "No map",
            [],
            id="no_map_info",
        ),
        pytest.param(
            {"current_map_id": None, "map_list": []},
            "No map",
            [],
            id="no_current_map",
        ),
        pytest.param(
            {
                "current_map_id": "map1",
                "map_list": [
                    {"map_id": "map1", "map_name": "TGl2aW5nIFJvb20="},
                    {"map_id": "map2", "map_name": "S2l0Y2hlbg=="},
                ],
            },
            "Living Room",
            ["Living Room", "Kitchen"],
            id="valid_maps_with_current",
        ),
        pytest.param(
            {
                "current_map_id": "map3",
                "map_list": [
                    {"map_id": "map1", "map_name": "TGl2aW5nIFJvb20="},
                    {"map_id": "map2", "map_name": "S2l0Y2hlbg=="},
                ],
            },
            "No map",
            ["Living Room", "Kitchen"],
            id="current_map_not_in_list",
        ),
        pytest.param(
            {
                "current_map_id": "map1",
                "map_list": [
                    {"map_id": "map1", "map_name": ""},  # Empty name
                    {"map_id": "map2", "map_name": "S2l0Y2hlbg=="},
                ],
            },
            "map1",
            ["map1", "Kitchen"],
            id="empty_map_name",
        ),
        pytest.param(
            {
                "current_map_id": "map1",
                "map_list": [
                    {"map_id": "map1", "map_name": "invalid_base64!"},
                    {"map_id": "map2", "map_name": "S2l0Y2hlbg=="},
                ],
            },
            "map1",
            ["map1", "Kitchen"],
            id="invalid_base64_fallback_to_id",
        ),
    ],
)
async def test_map_properties(
    dev: SmartDevice,
    mocker: MockerFixture,
    map_info: dict,
    expected_current: str,
    expected_available: list[str | None],
):
    """Test map properties with various map configurations."""
    clean = next(get_parent_and_child_modules(dev, Module.Clean))

    mocker.patch.object(
        type(clean),
        "_map_info",
        new_callable=mocker.PropertyMock,
        return_value=map_info,
    )

    assert clean.current_map == expected_current
    assert clean.available_maps == expected_available


@clean
async def test_set_current_map_success(dev: SmartDevice, mocker: MockerFixture):
    """Test setting current map successfully."""
    clean = next(get_parent_and_child_modules(dev, Module.Clean))

    map_info = {
        "current_map_id": "map1",
        "map_list": [
            {"map_id": "map1", "map_name": "TGl2aW5nIFJvb20="},
            {"map_id": "map2", "map_name": "S2l0Y2hlbg=="},
        ],
    }

    mocker.patch.object(
        type(clean),
        "_map_info",
        new_callable=mocker.PropertyMock,
        return_value=map_info,
    )
    call = mocker.spy(clean, "call")

    _result = await clean.set_current_map("Kitchen")

    call.assert_called_with("setMapInfo", {"current_map_id": "map2"})


@clean
async def test_set_current_map_not_found(dev: SmartDevice, mocker: MockerFixture):
    """Test setting current map with invalid map name."""
    clean = next(get_parent_and_child_modules(dev, Module.Clean))

    map_info = {
        "current_map_id": "map1",
        "map_list": [
            {"map_id": "map1", "map_name": "TGl2aW5nIFJvb20="},
            {"map_id": "map2", "map_name": "S2l0Y2hlbg=="},
        ],
    }

    mocker.patch.object(
        type(clean),
        "_map_info",
        new_callable=mocker.PropertyMock,
        return_value=map_info,
    )

    with pytest.raises(ValueError, match="Map 'Bedroom' not found. Available maps:"):
        await clean.set_current_map("Bedroom")


@clean
async def test_get_map_name_edge_cases(
    dev: SmartDevice, caplog: pytest.LogCaptureFixture
):
    """Test _get_map_name method with edge cases."""
    clean = next(get_parent_and_child_modules(dev, Module.Clean))

    caplog.set_level(logging.DEBUG)

    # Test with empty map name - should return map_id as fallback
    assert clean._get_map_name({"map_id": "map1", "map_name": ""}) == "map1"

    # Test with no map name key - should return map_id as fallback
    assert clean._get_map_name({"map_id": "map1"}) == "map1"

    # Test with invalid base64 - should return map_id as fallback and log error
    result = clean._get_map_name({"map_id": "map1", "map_name": "invalid_base64!"})
    assert result == "map1"
    assert "Failed to decode map name" in caplog.text

    # Test with valid base64
    result = clean._get_map_name({"map_id": "map1", "map_name": "TGl2aW5nIFJvb20="})
    assert result == "Living Room"

    # Test with no map_id key - should return "Unknown Map"
    assert clean._get_map_name({"map_name": ""}) == "Unknown Map"


@clean
async def test_set_current_map_in_actions_test(dev: SmartDevice, mocker: MockerFixture):
    """Test that selected_map action calls set_current_map correctly."""
    clean = next(get_parent_and_child_modules(dev, Module.Clean))

    map_info = {
        "current_map_id": "map1",
        "map_list": [
            {"map_id": "map1", "map_name": "TGl2aW5nIFJvb20="},
        ],
    }
    mocker.patch.object(
        type(clean),
        "_map_info",
        new_callable=mocker.PropertyMock,
        return_value=map_info,
    )

    call = mocker.spy(clean, "call")

    await dev.features["selected_map"].set_value("Living Room")
    call.assert_called_with("setMapInfo", {"current_map_id": "map1"})


@clean
async def test_selected_map_action_with_mock_data(
    dev: SmartDevice, mocker: MockerFixture
):
    """Test the selected_map feature action with proper mocking."""
    clean = next(get_parent_and_child_modules(dev, Module.Clean))

    map_info = {
        "current_map_id": "map1",
        "map_list": [
            {"map_id": "map1", "map_name": "TGl2aW5nIFJvb20="},
            {"map_id": "map2", "map_name": "S2l0Y2hlbg=="},
        ],
    }
    mocker.patch.object(
        type(clean),
        "_map_info",
        new_callable=mocker.PropertyMock,
        return_value=map_info,
    )

    call = mocker.spy(clean, "call")

    await dev.features["selected_map"].set_value("Kitchen")
    call.assert_called_with("setMapInfo", {"current_map_id": "map2"})
