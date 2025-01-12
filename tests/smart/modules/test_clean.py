from __future__ import annotations

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
    speaker = next(get_parent_and_child_modules(dev, Module.Clean))
    call = mocker.spy(speaker, "call")

    await dev.features[feature].set_value(value)
    call.assert_called_with(method, params)
