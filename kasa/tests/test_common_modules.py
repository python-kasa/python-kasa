import pytest
from pytest_mock import MockerFixture

from kasa import Device
from kasa.modules import LedModule, LightEffectModule
from kasa.tests.device_fixtures import (
    lightstrip,
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
light_effect = parametrize_combine([light_effect_smart, lightstrip])


@led
async def test_led_module(dev: Device, mocker: MockerFixture):
    """Test fan speed feature."""
    led_module = dev.get_module(LedModule)
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
    light_effect_module = dev.get_module(LightEffectModule)
    assert light_effect_module

    call = mocker.spy(light_effect_module, "call")
    effect_list = light_effect_module.effect_list
    assert "Off" in effect_list
    assert effect_list.index("Off") == 0
    assert len(effect_list) > 1

    assert light_effect_module.has_custom_effects is not None

    await light_effect_module.set_effect("Off")
    assert call.call_count == 1
    await dev.update()
    assert light_effect_module.effect == "Off"

    await light_effect_module.set_effect(effect_list[1])
    assert call.call_count == 2
    await dev.update()
    assert light_effect_module.effect == effect_list[1]

    await light_effect_module.set_effect(effect_list[len(effect_list) - 1])
    assert call.call_count == 3
    await dev.update()
    assert light_effect_module.effect == effect_list[len(effect_list) - 1]

    with pytest.raises(ValueError):
        await light_effect_module.set_effect("foobar")
        assert call.call_count == 2
