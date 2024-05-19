import pytest
from pytest_mock import MockerFixture

from kasa import Device, LightState, Module
from kasa.tests.device_fixtures import (
    bulb_iot,
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
light_strip_effect_smart = parametrize(
    "has light strip effect smart",
    component_filter="light_strip_lighting_effect",
    protocol_filter={"SMART"},
)
light_effect = parametrize_combine(
    [light_effect_smart, light_strip_effect_smart, lightstrip_iot]
)

dimmable_smart = parametrize(
    "dimmable smart", component_filter="brightness", protocol_filter={"SMART"}
)
dimmable = parametrize_combine([dimmable_smart, dimmer_iot, dimmable_iot])

light_preset_smart = parametrize(
    "has light preset smart", component_filter="preset", protocol_filter={"SMART"}
)

light_preset = parametrize_combine([light_preset_smart, bulb_iot])


@led
async def test_led_module(dev: Device, mocker: MockerFixture):
    """Test fan speed feature."""
    led_module = dev.modules.get(Module.Led)
    assert led_module
    feat = dev.features["led"]

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
    feat = dev.features["light_effect"]

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


@dimmable
async def test_light_brightness(dev: Device):
    """Test brightness setter and getter."""
    assert isinstance(dev, Device)
    light = dev.modules.get(Module.Light)
    assert light

    # Test getting the value
    feature = dev.features["brightness"]
    assert feature.minimum_value == 0
    assert feature.maximum_value == 100

    await light.set_brightness(10)
    await dev.update()
    assert light.brightness == 10

    with pytest.raises(ValueError):
        await light.set_brightness(feature.minimum_value - 10)

    with pytest.raises(ValueError):
        await light.set_brightness(feature.maximum_value + 10)


@light_preset
async def test_light_preset_module(dev: Device, mocker: MockerFixture):
    """Test light preset module."""
    preset_mod = dev.modules[Module.LightPreset]
    assert preset_mod
    light_mod = dev.modules[Module.Light]
    assert light_mod
    feat = dev.features["light_preset"]

    call = mocker.spy(light_mod, "set_state")
    preset_list = preset_mod.preset_list
    assert "Not set" in preset_list
    assert preset_list.index("Not set") == 0
    assert preset_list == feat.choices

    assert preset_mod.has_save_preset is True

    await light_mod.set_brightness(33)  # Value that should not be a preset
    assert call.call_count == 0
    await dev.update()
    assert preset_mod.preset == "Not set"
    assert feat.value == "Not set"

    if len(preset_list) == 1:
        return

    second_preset = preset_list[1]
    await preset_mod.set_preset(second_preset)
    assert call.call_count == 1
    await dev.update()
    assert preset_mod.preset == second_preset
    assert feat.value == second_preset

    last_preset = preset_list[len(preset_list) - 1]
    await preset_mod.set_preset(last_preset)
    assert call.call_count == 2
    await dev.update()
    assert preset_mod.preset == last_preset
    assert feat.value == last_preset

    # Test feature set
    await feat.set_value(second_preset)
    assert call.call_count == 3
    await dev.update()
    assert preset_mod.preset == second_preset
    assert feat.value == second_preset

    with pytest.raises(ValueError):
        await preset_mod.set_preset("foobar")
        assert call.call_count == 3


@light_preset
async def test_light_preset_save(dev: Device, mocker: MockerFixture):
    """Test saving a new preset value."""
    preset_mod = dev.modules[Module.LightPreset]
    assert preset_mod
    preset_list = preset_mod.preset_list
    if len(preset_list) == 1:
        return

    second_preset = preset_list[1]
    if preset_mod.preset_states_list[0].hue is None:
        new_preset = LightState(brightness=52)
    else:
        new_preset = LightState(brightness=52, color_temp=3000, hue=20, saturation=30)
    await preset_mod.save_preset(second_preset, new_preset)
    await dev.update()
    new_preset_state = preset_mod.preset_states_list[0]
    assert (
        new_preset_state.brightness == new_preset.brightness
        and new_preset_state.hue == new_preset.hue
        and new_preset_state.saturation == new_preset.saturation
        and new_preset_state.color_temp == new_preset.color_temp
    )
