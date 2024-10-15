from datetime import datetime

import pytest
from freezegun.api import FrozenDateTimeFactory
from pytest_mock import MockerFixture
from zoneinfo import ZoneInfo

from kasa import Device, LightState, Module
from kasa.tests.device_fixtures import (
    bulb_iot,
    bulb_smart,
    dimmable_iot,
    dimmer_iot,
    get_parent_and_child_modules,
    lightstrip_iot,
    parametrize,
    parametrize_combine,
    plug_iot,
    variable_temp_iot,
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

variable_temp_smart = parametrize(
    "variable temp smart",
    component_filter="color_temperature",
    protocol_filter={"SMART"},
)

variable_temp = parametrize_combine([variable_temp_iot, variable_temp_smart])

light_preset_smart = parametrize(
    "has light preset smart", component_filter="preset", protocol_filter={"SMART"}
)

light_preset = parametrize_combine([light_preset_smart, bulb_iot])

light = parametrize_combine([bulb_smart, bulb_iot, dimmable])


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

    call = mocker.spy(dev, "_query_helper")
    effect_list = light_effect_module.effect_list
    assert "Off" in effect_list
    assert effect_list.index("Off") == 0
    assert len(effect_list) > 1
    assert effect_list == feat.choices

    assert light_effect_module.has_custom_effects is not None

    await light_effect_module.set_effect("Off")
    call.assert_called()
    await dev.update()
    assert light_effect_module.effect == "Off"
    assert feat.value == "Off"
    call.reset_mock()

    second_effect = effect_list[1]
    await light_effect_module.set_effect(second_effect)
    call.assert_called()
    await dev.update()
    assert light_effect_module.effect == second_effect
    assert feat.value == second_effect
    call.reset_mock()

    last_effect = effect_list[len(effect_list) - 1]
    await light_effect_module.set_effect(last_effect)
    call.assert_called()
    await dev.update()
    assert light_effect_module.effect == last_effect
    assert feat.value == last_effect
    call.reset_mock()

    # Test feature set
    await feat.set_value(second_effect)
    call.assert_called()
    await dev.update()
    assert light_effect_module.effect == second_effect
    assert feat.value == second_effect
    call.reset_mock()

    with pytest.raises(ValueError, match="The effect foobar is not a built in effect."):
        await light_effect_module.set_effect("foobar")
    call.assert_not_called()


@light_effect
async def test_light_effect_brightness(dev: Device, mocker: MockerFixture):
    """Test that light module uses light_effect for brightness when active."""
    light_module = dev.modules[Module.Light]

    light_effect = dev.modules[Module.LightEffect]

    await light_effect.set_effect(light_effect.LIGHT_EFFECTS_OFF)
    await light_module.set_brightness(50)
    await dev.update()
    assert light_effect.effect == light_effect.LIGHT_EFFECTS_OFF
    assert light_module.brightness == 50
    await light_effect.set_effect(light_effect.effect_list[1])
    await dev.update()
    # assert light_module.brightness == 100

    await light_module.set_brightness(75)
    await dev.update()
    assert light_module.brightness == 75

    await light_effect.set_effect(light_effect.LIGHT_EFFECTS_OFF)
    await dev.update()
    assert light_module.brightness == 50


@dimmable
async def test_light_brightness(dev: Device):
    """Test brightness setter and getter."""
    assert isinstance(dev, Device)
    light = next(get_parent_and_child_modules(dev, Module.Light))
    assert light

    # Test getting the value
    feature = light._device.features["brightness"]
    assert feature.minimum_value == 0
    assert feature.maximum_value == 100

    await light.set_brightness(10)
    await dev.update()
    assert light.brightness == 10

    with pytest.raises(ValueError, match="Invalid brightness value: "):
        await light.set_brightness(feature.minimum_value - 10)

    with pytest.raises(ValueError, match="Invalid brightness value: "):
        await light.set_brightness(feature.maximum_value + 10)


@variable_temp
async def test_light_color_temp(dev: Device):
    """Test color temp setter and getter."""
    assert isinstance(dev, Device)

    light = next(get_parent_and_child_modules(dev, Module.Light))
    assert light
    if not light.is_variable_color_temp:
        pytest.skip(
            "Some smart light strips have color_temperature"
            " component but min and max are the same"
        )

    # Test getting the value
    feature = light._device.features["color_temperature"]
    assert isinstance(feature.minimum_value, int)
    assert isinstance(feature.maximum_value, int)

    await light.set_color_temp(feature.minimum_value + 10)
    await dev.update()
    assert light.color_temp == feature.minimum_value + 10

    # Test setting brightness with color temp
    await light.set_brightness(50)
    await dev.update()
    assert light.brightness == 50

    await light.set_color_temp(feature.minimum_value + 20, brightness=60)
    await dev.update()
    assert light.color_temp == feature.minimum_value + 20
    assert light.brightness == 60

    with pytest.raises(ValueError, match=r"Temperature should be between \d+ and \d+"):
        await light.set_color_temp(feature.minimum_value - 10)

    with pytest.raises(ValueError, match=r"Temperature should be between \d+ and \d+"):
        await light.set_color_temp(feature.maximum_value + 10)


@light
async def test_light_set_state(dev: Device):
    """Test brightness setter and getter."""
    assert isinstance(dev, Device)
    light = next(get_parent_and_child_modules(dev, Module.Light))
    assert light
    # For fixtures that have a light effect active switch off
    if light_effect := light._device.modules.get(Module.LightEffect):
        await light_effect.set_effect(light_effect.LIGHT_EFFECTS_OFF)

    await light.set_state(LightState(light_on=False))
    await dev.update()
    assert light.state.light_on is False

    await light.set_state(LightState(light_on=True))
    await dev.update()
    assert light.state.light_on is True

    await light.set_state(LightState(brightness=0))
    await dev.update()
    assert light.state.light_on is False

    await light.set_state(LightState(brightness=50))
    await dev.update()
    assert light.state.light_on is True


@light_preset
async def test_light_preset_module(dev: Device, mocker: MockerFixture):
    """Test light preset module."""
    preset_mod = next(get_parent_and_child_modules(dev, Module.LightPreset))
    assert preset_mod
    light_mod = next(get_parent_and_child_modules(dev, Module.Light))
    assert light_mod
    feat = preset_mod._device.features["light_preset"]

    preset_list = preset_mod.preset_list
    assert "Not set" in preset_list
    assert preset_list.index("Not set") == 0
    assert preset_list == feat.choices

    assert preset_mod.has_save_preset is True

    await light_mod.set_brightness(33)  # Value that should not be a preset
    await dev.update()
    assert preset_mod.preset == "Not set"
    assert feat.value == "Not set"

    if len(preset_list) == 1:
        return

    call = mocker.spy(light_mod, "set_state")
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

    with pytest.raises(ValueError, match="foobar is not a valid preset"):
        await preset_mod.set_preset("foobar")
    assert call.call_count == 3


@light_preset
async def test_light_preset_save(dev: Device, mocker: MockerFixture):
    """Test saving a new preset value."""
    preset_mod = next(get_parent_and_child_modules(dev, Module.LightPreset))
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
    assert new_preset_state.brightness == new_preset.brightness
    assert new_preset_state.hue == new_preset.hue
    assert new_preset_state.saturation == new_preset.saturation
    assert new_preset_state.color_temp == new_preset.color_temp


async def test_set_time(dev: Device, freezer: FrozenDateTimeFactory):
    """Test setting the device time."""
    freezer.move_to("2021-01-09 12:00:00+00:00")
    time_mod = dev.modules[Module.Time]
    tz_info = time_mod.timezone
    now = datetime.now(tz=tz_info)
    now = now.replace(microsecond=0)
    assert time_mod.time != now

    await time_mod.set_time(now)
    await dev.update()
    assert time_mod.time == now

    zone = ZoneInfo("Europe/Berlin")
    now = datetime.now(tz=zone)
    now = now.replace(microsecond=0)
    await time_mod.set_time(now)
    await dev.update()
    assert time_mod.time == now
