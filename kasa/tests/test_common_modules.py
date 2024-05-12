import pytest
from pytest_mock import MockerFixture

from kasa import Device, Module
from kasa.tests.device_fixtures import (
    dimmable_iot,
    dimmer_iot,
    lightstrip_iot,
    parametrize,
    parametrize_combine,
    plug_iot,
)

led_smart = parametrize(
    "has led smart", component_filter="led", protocol_filter={"SMART"}
)
led = parametrize_combine([led_smart, plug_iot])

light_effect_smart = parametrize(
    "has light effect smart", component_filter="light_effect", protocol_filter={"SMART"}
)
light_effect = parametrize_combine([light_effect_smart, lightstrip_iot])

dimmable_smart = parametrize(
    "dimmable smart", component_filter="brightness", protocol_filter={"SMART"}
)
dimmable_iot = parametrize_combine([dimmable_smart, dimmer_iot, dimmable_iot])


@led
async def test_led_module(dev: Device, mocker: MockerFixture):
    """Test fan speed feature."""
    led_module = dev.modules.get(Module.Led)
    assert led_module
    feat = led_module._module_features["led"]

    call = mocker.spy(led_module, "call")
    await led_module.set_led(True)
    assert call.call_count == 1
    await dev.update()
    assert led_module.led is True
    assert feat.value is True

    await led_module.set_led(False)
    assert call.call_count == 2
    await dev.update()
    assert led_module.led is False
    assert feat.value is False

    await feat.set_value(True)
    assert call.call_count == 3
    await dev.update()
    assert feat.value is True
    assert led_module.led is True


@light_effect
async def test_light_effect_module(dev: Device, mocker: MockerFixture):
    """Test fan speed feature."""
    light_effect_module = dev.modules[Module.LightEffect]
    assert light_effect_module
    feat = light_effect_module._module_features["light_effect"]

    call = mocker.spy(light_effect_module, "call")
    effect_list = light_effect_module.effect_list
    assert "Off" in effect_list
    assert effect_list.index("Off") == 0
    assert len(effect_list) > 1
    assert effect_list == feat.choices

    assert light_effect_module.has_custom_effects is not None

    await light_effect_module.set_effect("Off")
    assert call.call_count == 1
    await dev.update()
    assert light_effect_module.effect == "Off"
    assert feat.value == "Off"

    second_effect = effect_list[1]
    await light_effect_module.set_effect(second_effect)
    assert call.call_count == 2
    await dev.update()
    assert light_effect_module.effect == second_effect
    assert feat.value == second_effect

    last_effect = effect_list[len(effect_list) - 1]
    await light_effect_module.set_effect(last_effect)
    assert call.call_count == 3
    await dev.update()
    assert light_effect_module.effect == last_effect
    assert feat.value == last_effect

    # Test feature set
    await feat.set_value(second_effect)
    assert call.call_count == 4
    await dev.update()
    assert light_effect_module.effect == second_effect
    assert feat.value == second_effect

    with pytest.raises(ValueError):
        await light_effect_module.set_effect("foobar")
        assert call.call_count == 4


@dimmable_iot
async def test_light_brightness(dev: Device):
    """Test brightness setter and getter."""
    assert isinstance(dev, Device)
    brightness = dev.modules.get(Module.Brightness)
    assert brightness

    # Test getting the value
    feature = brightness._module_features["brightness"]
    assert feature.minimum_value == 0
    assert feature.maximum_value == 100

    await brightness.set_brightness(10)
    await dev.update()
    assert brightness.brightness == 10

    with pytest.raises(ValueError):
        await brightness.set_brightness(feature.minimum_value - 10)

    with pytest.raises(ValueError):
        await brightness.set_brightness(feature.maximum_value + 10)
