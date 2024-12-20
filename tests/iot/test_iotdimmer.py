import pytest

from kasa import DeviceType, Module
from kasa.iot import IotDimmer
from tests.conftest import dimmer_iot, handle_turn_on, turn_on


@dimmer_iot
async def test_set_brightness(dev):
    light = dev.modules.get(Module.Light)
    assert light
    await handle_turn_on(dev, False)
    await dev.update()
    assert dev.is_on is False

    await light.set_brightness(99)
    await dev.update()
    assert light.brightness == 99
    assert dev.is_on is True

    await light.set_brightness(0)
    await dev.update()
    assert light.brightness == 99
    assert dev.is_on is False


@dimmer_iot
@turn_on
async def test_set_brightness_transition(dev, turn_on, mocker):
    light = dev.modules.get(Module.Light)
    assert light
    await handle_turn_on(dev, turn_on)
    query_helper = mocker.spy(IotDimmer, "_query_helper")

    await light.set_brightness(99, transition=1000)
    query_helper.assert_called_with(
        mocker.ANY,
        "smartlife.iot.dimmer",
        "set_dimmer_transition",
        {"brightness": 99, "duration": 1000},
    )
    await dev.update()
    assert light.brightness == 99
    assert dev.is_on

    await light.set_brightness(0, transition=1000)
    await dev.update()
    assert dev.is_on is False


@dimmer_iot
async def test_set_brightness_invalid(dev):
    light = dev.modules.get(Module.Light)
    assert light
    for invalid_brightness in [-1, 101]:
        with pytest.raises(ValueError, match="Invalid brightness"):
            await light.set_brightness(invalid_brightness)

    for invalid_type in [0.5, "foo"]:
        with pytest.raises(TypeError, match="Brightness must be an integer"):
            await light.set_brightness(invalid_type)


@dimmer_iot
async def test_set_brightness_invalid_transition(dev):
    light = dev.modules.get(Module.Light)
    assert light
    for invalid_transition in [-1]:
        with pytest.raises(ValueError, match="Transition value .+? is not valid."):
            await light.set_brightness(1, transition=invalid_transition)
    for invalid_type in [0.5, "foo"]:
        with pytest.raises(TypeError, match="Transition must be integer"):
            await light.set_brightness(1, transition=invalid_type)


@dimmer_iot
async def test_turn_on_transition(dev, mocker):
    light = dev.modules.get(Module.Light)
    assert light
    query_helper = mocker.spy(IotDimmer, "_query_helper")
    original_brightness = light.brightness

    await dev.turn_on(transition=1000)
    query_helper.assert_called_with(
        mocker.ANY,
        "smartlife.iot.dimmer",
        "set_dimmer_transition",
        {"brightness": original_brightness, "duration": 1000},
    )
    await dev.update()
    assert dev.is_on
    assert light.brightness == original_brightness


@dimmer_iot
async def test_turn_off_transition(dev, mocker):
    light = dev.modules.get(Module.Light)
    assert light
    await handle_turn_on(dev, True)
    query_helper = mocker.spy(IotDimmer, "_query_helper")
    original_brightness = light.brightness

    await dev.turn_off(transition=1000)
    await dev.update()

    assert dev.is_off
    assert light.brightness == original_brightness
    query_helper.assert_called_with(
        mocker.ANY,
        "smartlife.iot.dimmer",
        "set_dimmer_transition",
        {"brightness": 0, "duration": 1000},
    )


@dimmer_iot
@turn_on
async def test_set_dimmer_transition(dev, turn_on, mocker):
    light = dev.modules.get(Module.Light)
    assert light
    await handle_turn_on(dev, turn_on)
    query_helper = mocker.spy(IotDimmer, "_query_helper")

    await dev.set_dimmer_transition(99, 1000)
    query_helper.assert_called_with(
        mocker.ANY,
        "smartlife.iot.dimmer",
        "set_dimmer_transition",
        {"brightness": 99, "duration": 1000},
    )
    await dev.update()
    assert dev.is_on
    assert light.brightness == 99


@dimmer_iot
@turn_on
async def test_set_dimmer_transition_to_off(dev, turn_on, mocker):
    light = dev.modules.get(Module.Light)
    assert light
    await handle_turn_on(dev, turn_on)
    original_brightness = light.brightness
    query_helper = mocker.spy(IotDimmer, "_query_helper")

    await dev.set_dimmer_transition(0, 1000)
    await dev.update()

    assert dev.is_off
    assert light.brightness == original_brightness
    query_helper.assert_called_with(
        mocker.ANY,
        "smartlife.iot.dimmer",
        "set_dimmer_transition",
        {"brightness": 0, "duration": 1000},
    )


@dimmer_iot
async def test_set_dimmer_transition_invalid_brightness(dev):
    for invalid_brightness in [-1, 101]:
        with pytest.raises(ValueError, match="Invalid brightness value: "):
            await dev.set_dimmer_transition(invalid_brightness, 1000)

    for invalid_type in [0.5, "foo"]:
        with pytest.raises(TypeError, match="Transition must be integer"):
            await dev.set_dimmer_transition(1, invalid_type)


@dimmer_iot
async def test_set_dimmer_transition_invalid_transition(dev):
    for invalid_transition in [-1]:
        with pytest.raises(ValueError, match="Transition value .+? is not valid."):
            await dev.set_dimmer_transition(1, transition=invalid_transition)
    for invalid_type in [0.5, "foo"]:
        with pytest.raises(TypeError, match="Transition must be integer"):
            await dev.set_dimmer_transition(1, transition=invalid_type)


@dimmer_iot
def test_device_type_dimmer(dev):
    assert dev.device_type == DeviceType.Dimmer
