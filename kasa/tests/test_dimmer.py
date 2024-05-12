import pytest

from kasa import DeviceType
from kasa.iot import IotDimmer

from .conftest import dimmer_iot, handle_turn_on, turn_on


@dimmer_iot
@turn_on
async def test_set_brightness(dev, turn_on):
    await handle_turn_on(dev, turn_on)

    await dev.set_brightness(99)
    await dev.update()
    assert dev.brightness == 99
    assert dev.is_on == turn_on

    await dev.set_brightness(0)
    await dev.update()
    assert dev.brightness == 1
    assert dev.is_on == turn_on


@dimmer_iot
@turn_on
async def test_set_brightness_transition(dev, turn_on, mocker):
    await handle_turn_on(dev, turn_on)
    query_helper = mocker.spy(IotDimmer, "_query_helper")

    await dev.set_brightness(99, transition=1000)
    query_helper.assert_called_with(
        mocker.ANY,
        "smartlife.iot.dimmer",
        "set_dimmer_transition",
        {"brightness": 99, "duration": 1000},
    )
    await dev.update()
    assert dev.brightness == 99
    assert dev.is_on

    await dev.set_brightness(0, transition=1000)
    await dev.update()
    assert dev.brightness == 1


@dimmer_iot
async def test_set_brightness_invalid(dev):
    for invalid_brightness in [-1, 101, 0.5]:
        with pytest.raises(ValueError):
            await dev.set_brightness(invalid_brightness)

    for invalid_transition in [-1, 0, 0.5]:
        with pytest.raises(ValueError):
            await dev.set_brightness(1, transition=invalid_transition)


@dimmer_iot
async def test_turn_on_transition(dev, mocker):
    query_helper = mocker.spy(IotDimmer, "_query_helper")
    original_brightness = dev.brightness

    await dev.turn_on(transition=1000)
    query_helper.assert_called_with(
        mocker.ANY,
        "smartlife.iot.dimmer",
        "set_dimmer_transition",
        {"brightness": original_brightness, "duration": 1000},
    )
    await dev.update()
    assert dev.is_on
    assert dev.brightness == original_brightness


@dimmer_iot
async def test_turn_off_transition(dev, mocker):
    await handle_turn_on(dev, True)
    query_helper = mocker.spy(IotDimmer, "_query_helper")
    original_brightness = dev.brightness

    await dev.turn_off(transition=1000)

    assert dev.is_off
    assert dev.brightness == original_brightness
    query_helper.assert_called_with(
        mocker.ANY,
        "smartlife.iot.dimmer",
        "set_dimmer_transition",
        {"brightness": 0, "duration": 1000},
    )


@dimmer_iot
@turn_on
async def test_set_dimmer_transition(dev, turn_on, mocker):
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
    assert dev.brightness == 99


@dimmer_iot
@turn_on
async def test_set_dimmer_transition_to_off(dev, turn_on, mocker):
    await handle_turn_on(dev, turn_on)
    original_brightness = dev.brightness
    query_helper = mocker.spy(IotDimmer, "_query_helper")

    await dev.set_dimmer_transition(0, 1000)

    assert dev.is_off
    assert dev.brightness == original_brightness
    query_helper.assert_called_with(
        mocker.ANY,
        "smartlife.iot.dimmer",
        "set_dimmer_transition",
        {"brightness": 0, "duration": 1000},
    )


@dimmer_iot
async def test_set_dimmer_transition_invalid(dev):
    for invalid_brightness in [-1, 101, 0.5]:
        with pytest.raises(ValueError):
            await dev.set_dimmer_transition(invalid_brightness, 1000)

    for invalid_transition in [-1, 0, 0.5]:
        with pytest.raises(ValueError):
            await dev.set_dimmer_transition(1, invalid_transition)


@dimmer_iot
def test_device_type_dimmer(dev):
    assert dev.device_type == DeviceType.Dimmer
