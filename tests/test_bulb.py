from __future__ import annotations

import pytest

from kasa import Device, DeviceType, KasaException, Module
from tests.conftest import handle_turn_on, turn_on
from tests.device_fixtures import (
    bulb,
    color_bulb,
    non_color_bulb,
    non_variable_temp,
    variable_temp,
)


@bulb
async def test_state_attributes(dev: Device):
    assert "Cloud connection" in dev.state_information
    assert isinstance(dev.state_information["Cloud connection"], bool)


@color_bulb
@turn_on
async def test_hsv(dev: Device, turn_on):
    light = dev.modules.get(Module.Light)
    assert light
    await handle_turn_on(dev, turn_on)
    assert light.has_feature("hsv")

    hue, saturation, brightness = light.hsv
    assert 0 <= hue <= 360
    assert 0 <= saturation <= 100
    assert 0 <= brightness <= 100

    await light.set_hsv(hue=1, saturation=1, value=1)

    await dev.update()
    hue, saturation, brightness = light.hsv
    assert hue == 1
    assert saturation == 1
    assert brightness == 1


@color_bulb
@turn_on
@pytest.mark.parametrize(
    ("hue", "sat", "brightness", "exception_cls", "error"),
    [
        pytest.param(-1, 0, 0, ValueError, "Invalid hue", id="hue out of range"),
        pytest.param(361, 0, 0, ValueError, "Invalid hue", id="hue out of range"),
        pytest.param(
            0.5, 0, 0, TypeError, "Hue must be an integer", id="hue invalid type"
        ),
        pytest.param(
            "foo", 0, 0, TypeError, "Hue must be an integer", id="hue invalid type"
        ),
        pytest.param(
            0, -1, 0, ValueError, "Invalid saturation", id="saturation out of range"
        ),
        pytest.param(
            0, 101, 0, ValueError, "Invalid saturation", id="saturation out of range"
        ),
        pytest.param(
            0,
            0.5,
            0,
            TypeError,
            "Saturation must be an integer",
            id="saturation invalid type",
        ),
        pytest.param(
            0,
            "foo",
            0,
            TypeError,
            "Saturation must be an integer",
            id="saturation invalid type",
        ),
        pytest.param(
            0, 0, -1, ValueError, "Invalid brightness", id="brightness out of range"
        ),
        pytest.param(
            0, 0, 101, ValueError, "Invalid brightness", id="brightness out of range"
        ),
        pytest.param(
            0,
            0,
            0.5,
            TypeError,
            "Brightness must be an integer",
            id="brightness invalid type",
        ),
        pytest.param(
            0,
            0,
            "foo",
            TypeError,
            "Brightness must be an integer",
            id="brightness invalid type",
        ),
    ],
)
async def test_invalid_hsv(
    dev: Device, turn_on, hue, sat, brightness, exception_cls, error
):
    light = dev.modules.get(Module.Light)
    assert light
    await handle_turn_on(dev, turn_on)
    assert light.has_feature("hsv")
    with pytest.raises(exception_cls, match=error):
        await light.set_hsv(hue, sat, brightness)


@color_bulb
@pytest.mark.skip("requires color feature")
async def test_color_state_information(dev: Device):
    light = dev.modules.get(Module.Light)
    assert light
    assert "HSV" in dev.state_information
    assert dev.state_information["HSV"] == light.hsv


@non_color_bulb
async def test_hsv_on_non_color(dev: Device):
    light = dev.modules.get(Module.Light)
    assert light
    assert not light.has_feature("hsv")

    with pytest.raises(KasaException):
        await light.set_hsv(0, 0, 0)
    with pytest.raises(KasaException):
        print(light.hsv)


@variable_temp
@pytest.mark.skip("requires colortemp module")
async def test_variable_temp_state_information(dev: Device):
    light = dev.modules.get(Module.Light)
    assert light
    assert "Color temperature" in dev.state_information
    assert dev.state_information["Color temperature"] == light.color_temp


@variable_temp
@turn_on
async def test_try_set_colortemp(dev: Device, turn_on):
    light = dev.modules.get(Module.Light)
    assert light
    await handle_turn_on(dev, turn_on)
    await light.set_color_temp(2700)
    await dev.update()
    assert light.color_temp == 2700


@variable_temp
async def test_out_of_range_temperature(dev: Device):
    light = dev.modules.get(Module.Light)
    assert light
    with pytest.raises(
        ValueError, match=r"Temperature should be between \d+ and \d+, was 1000"
    ):
        await light.set_color_temp(1000)
    with pytest.raises(
        ValueError, match=r"Temperature should be between \d+ and \d+, was 10000"
    ):
        await light.set_color_temp(10000)


@non_variable_temp
async def test_non_variable_temp(dev: Device):
    light = dev.modules.get(Module.Light)
    assert light
    with pytest.raises(KasaException):
        await light.set_color_temp(2700)

    with pytest.raises(KasaException):
        print(light.color_temp)


@bulb
def test_device_type_bulb(dev: Device):
    assert dev.device_type in {DeviceType.Bulb, DeviceType.LightStrip}
