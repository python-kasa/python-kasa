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
    ("err_status", "error"),
    [
        pytest.param([], ErrorCode.Ok, id="empty error"),
        pytest.param([0], ErrorCode.Ok, id="no error"),
        pytest.param([3], ErrorCode.MainBrushStuck, id="known error"),
        pytest.param([123], ErrorCode.UnknownInternal, id="unknown error"),
        pytest.param([3, 4], ErrorCode.MainBrushStuck, id="multi-error"),
    ],
)
@clean
async def test_post_update_hook(dev: SmartDevice, err_status: list, error: ErrorCode):
    """Test that post update hook sets error states correctly."""
    clean = next(get_parent_and_child_modules(dev, Module.Clean))
    clean.data["getVacStatus"]["err_status"] = err_status

    await clean._post_update_hook()

    assert clean._error_code is error

    if error is not ErrorCode.Ok:
        assert clean.status is Status.Error


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
