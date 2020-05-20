import pytest

from kasa import DeviceType, SmartDeviceException

from .conftest import (
    bulb,
    color_bulb,
    dimmable,
    handle_turn_on,
    non_color_bulb,
    non_dimmable,
    non_variable_temp,
    turn_on,
    variable_temp,
)
from .newfakes import BULB_SCHEMA


@bulb
async def test_bulb_sysinfo(dev):
    assert dev.sys_info is not None
    BULB_SCHEMA(dev.sys_info)

    assert dev.model is not None

    assert dev.device_type == DeviceType.Bulb
    assert dev.is_bulb


@color_bulb
@turn_on
async def test_hsv(dev, turn_on):
    await handle_turn_on(dev, turn_on)
    assert dev.is_color

    hue, saturation, brightness = dev.hsv
    assert 0 <= hue <= 255
    assert 0 <= saturation <= 100
    assert 0 <= brightness <= 100

    await dev.set_hsv(hue=1, saturation=1, value=1)

    hue, saturation, brightness = dev.hsv
    assert hue == 1
    assert saturation == 1
    assert brightness == 1


@color_bulb
@turn_on
async def test_invalid_hsv(dev, turn_on):
    await handle_turn_on(dev, turn_on)
    assert dev.is_color

    for invalid_hue in [-1, 361, 0.5]:
        with pytest.raises(ValueError):
            await dev.set_hsv(invalid_hue, 0, 0)

    for invalid_saturation in [-1, 101, 0.5]:
        with pytest.raises(ValueError):
            await dev.set_hsv(0, invalid_saturation, 0)

    for invalid_brightness in [-1, 101, 0.5]:
        with pytest.raises(ValueError):
            await dev.set_hsv(0, 0, invalid_brightness)


@non_color_bulb
async def test_hsv_on_non_color(dev):
    assert not dev.is_color

    with pytest.raises(SmartDeviceException):
        await dev.set_hsv(0, 0, 0)
    with pytest.raises(SmartDeviceException):
        print(dev.hsv)


@variable_temp
@turn_on
async def test_try_set_colortemp(dev, turn_on):
    await handle_turn_on(dev, turn_on)
    await dev.set_color_temp(2700)
    assert dev.color_temp == 2700


@non_variable_temp
async def test_non_variable_temp(dev):
    with pytest.raises(SmartDeviceException):
        await dev.set_color_temp(2700)


@non_variable_temp
async def test_temperature_on_nonsupporting(dev):
    assert dev.valid_temperature_range == (0, 0)

    # TODO test when device does not support temperature range
    with pytest.raises(SmartDeviceException):
        await dev.set_color_temp(2700)
    with pytest.raises(SmartDeviceException):
        print(dev.color_temp)


@variable_temp
async def test_out_of_range_temperature(dev):
    with pytest.raises(ValueError):
        await dev.set_color_temp(1000)
    with pytest.raises(ValueError):
        await dev.set_color_temp(10000)


@non_dimmable
async def test_non_dimmable(dev):
    assert not dev.is_dimmable

    with pytest.raises(SmartDeviceException):
        assert dev.brightness == 0
    with pytest.raises(SmartDeviceException):
        await dev.set_brightness(100)


@dimmable
@turn_on
async def test_dimmable_brightness(dev, turn_on):
    await handle_turn_on(dev, turn_on)
    assert dev.is_dimmable

    await dev.set_brightness(50)
    assert dev.brightness == 50

    await dev.set_brightness(10)
    assert dev.brightness == 10

    with pytest.raises(ValueError):
        await dev.set_brightness("foo")


@dimmable
async def test_invalid_brightness(dev):
    assert dev.is_dimmable

    with pytest.raises(ValueError):
        await dev.set_brightness(110)

    with pytest.raises(ValueError):
        await dev.set_brightness(-100)
