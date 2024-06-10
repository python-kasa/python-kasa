import pytest
from pytest_mock import MockerFixture

from kasa import Module
from kasa.smart import SmartDevice
from kasa.tests.device_fixtures import get_parent_and_child_modules, parametrize

fan = parametrize("has fan", component_filter="fan_control", protocol_filter={"SMART"})


@fan
async def test_fan_speed(dev: SmartDevice, mocker: MockerFixture):
    """Test fan speed feature."""
    fan = next(get_parent_and_child_modules(dev, Module.Fan))
    assert fan
    level_feature = fan._module_features["fan_speed_level"]
    assert (
        level_feature.minimum_value
        <= level_feature.value
        <= level_feature.maximum_value
    )

    call = mocker.spy(fan, "call")
    await fan.set_fan_speed_level(3)
    call.assert_called_with(
        "set_device_info", {"device_on": True, "fan_speed_level": 3}
    )

    await dev.update()

    assert fan.fan_speed_level == 3
    assert level_feature.value == 3


@fan
async def test_sleep_mode(dev: SmartDevice, mocker: MockerFixture):
    """Test sleep mode feature."""
    fan = next(get_parent_and_child_modules(dev, Module.Fan))
    assert fan
    sleep_feature = fan._module_features["fan_sleep_mode"]
    assert isinstance(sleep_feature.value, bool)

    call = mocker.spy(fan, "call")
    await fan.set_sleep_mode(True)
    call.assert_called_with("set_device_info", {"fan_sleep_mode_on": True})

    await dev.update()

    assert fan.sleep_mode is True
    assert sleep_feature.value is True


@fan
async def test_fan_module(dev: SmartDevice, mocker: MockerFixture):
    """Test fan speed on device interface."""
    assert isinstance(dev, SmartDevice)
    fan = next(get_parent_and_child_modules(dev, Module.Fan))
    assert fan
    device = fan._device

    await fan.set_fan_speed_level(1)
    await dev.update()
    assert fan.fan_speed_level == 1
    assert device.is_on

    # Check that if the device is off the speed level is 0.
    await device.set_state(False)
    await dev.update()
    assert fan.fan_speed_level == 0

    await fan.set_fan_speed_level(4)
    await dev.update()
    assert fan.fan_speed_level == 4

    await fan.set_fan_speed_level(0)
    await dev.update()
    assert not device.is_on

    with pytest.raises(ValueError):
        await fan.set_fan_speed_level(-1)

    with pytest.raises(ValueError):
        await fan.set_fan_speed_level(5)
