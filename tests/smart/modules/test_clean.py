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
async def test_clean_rooms(dev: SmartDevice, mocker: MockerFixture):
    """Test clean_rooms sends the correct setSwitchClean payload."""
    clean = next(get_parent_and_child_modules(dev, Module.Clean))
    call = mocker.spy(clean, "call")

    room_ids = [2, 3]
    await clean.clean_rooms(room_ids)

    call.assert_called_with(
        "setSwitchClean",
        {
            "clean_mode": 3,
            "clean_on": True,
            "clean_order": True,
            "force_clean": False,
            "map_id": clean.current_map_id,
            "room_list": room_ids,
            "start_type": 1,
        },
    )


@clean
async def test_clean_rooms_explicit_map_id(dev: SmartDevice, mocker: MockerFixture):
    """Test clean_rooms uses the provided map_id when given."""
    clean = next(get_parent_and_child_modules(dev, Module.Clean))
    call = mocker.spy(clean, "call")

    await clean.clean_rooms([5], map_id=12345)

    call.assert_called_with(
        "setSwitchClean",
        {
            "clean_mode": 3,
            "clean_on": True,
            "clean_order": True,
            "force_clean": False,
            "map_id": 12345,
            "room_list": [5],
            "start_type": 1,
        },
    )


@clean
async def test_clean_rooms_empty_raises(dev: SmartDevice):
    """Test clean_rooms raises ValueError when room_ids is empty."""
    clean = next(get_parent_and_child_modules(dev, Module.Clean))

    with pytest.raises(ValueError, match="room_ids must not be empty"):
        await clean.clean_rooms([])


@clean
async def test_get_rooms(dev: SmartDevice, mocker: MockerFixture):
    """Test get_rooms calls getMapData and filters to rooms only."""
    clean = next(get_parent_and_child_modules(dev, Module.Clean))

    map_data = {
        "area_list": [
            {"id": 2, "name": "Kitchen", "type": "room"},
            {"id": 3, "name": "Living Room", "type": "room"},
            {"id": 401, "type": "virtual_wall", "vertexs": []},
        ]
    }
    call_mock = mocker.patch.object(clean, "call", return_value=map_data)

    rooms = await clean.get_rooms()

    call_mock.assert_called_once_with(
        "getMapData", {"map_id": clean.current_map_id, "type": 0}
    )
    assert len(rooms) == 2
    assert all(r["type"] == "room" for r in rooms)


@clean
async def test_get_rooms_explicit_map_id(dev: SmartDevice, mocker: MockerFixture):
    """Test get_rooms uses the provided map_id when given."""
    clean = next(get_parent_and_child_modules(dev, Module.Clean))

    map_data = {"area_list": [{"id": 1, "name": "Hall", "type": "room"}]}
    call_mock = mocker.patch.object(clean, "call", return_value=map_data)

    rooms = await clean.get_rooms(map_id=99999)

    call_mock.assert_called_once_with("getMapData", {"map_id": 99999, "type": 0})
    assert len(rooms) == 1
