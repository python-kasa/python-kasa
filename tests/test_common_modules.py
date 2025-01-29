import importlib
import inspect
import pkgutil
import sys
from datetime import datetime
from zoneinfo import ZoneInfo

import pytest
from pytest_mock import MockerFixture

import kasa.interfaces
from kasa import Device, LightState, Module, ThermostatState
from kasa.module import _get_feature_attribute

from .device_fixtures import (
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

temp_control_smart = parametrize(
    "has temp control smart",
    component_filter="temp_control",
    protocol_filter={"SMART.CHILD"},
)


interfaces = pytest.mark.parametrize("interface", kasa.interfaces.__all__)


def _get_subclasses(of_class, package):
    """Get all the subclasses of a given class."""
    subclasses = set()
    # iter_modules returns ModuleInfo: (module_finder, name, ispkg)
    for _, modname, ispkg in pkgutil.iter_modules(package.__path__):
        importlib.import_module("." + modname, package=package.__name__)
        module = sys.modules[package.__name__ + "." + modname]
        for _, obj in inspect.getmembers(module):
            if (
                inspect.isclass(obj)
                and issubclass(obj, of_class)
                and obj is not of_class
            ):
                subclasses.add(obj)

        if ispkg:
            res = _get_subclasses(of_class, module)
            subclasses.update(res)
    return subclasses


@interfaces
def test_feature_attributes(interface):
    """Test that all common derived classes define the FeatureAttributes."""
    klass = getattr(kasa.interfaces, interface)

    package = sys.modules["kasa"]
    sub_classes = _get_subclasses(klass, package)

    feat_attributes: set[str] = set()
    attribute_names = [
        k
        for k, v in vars(klass).items()
        if (callable(v) and not inspect.isclass(v)) or isinstance(v, property)
    ]
    for attr_name in attribute_names:
        attribute = getattr(klass, attr_name)
        if _get_feature_attribute(attribute):
            feat_attributes.add(attr_name)

    for sub_class in sub_classes:
        for attr_name in feat_attributes:
            attribute = getattr(sub_class, attr_name)
            fa = _get_feature_attribute(attribute)
            assert fa, f"{attr_name} is not a defined module feature for {sub_class}"


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
    if not light.has_feature("color_temp"):
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


@temp_control_smart
async def test_thermostat(dev: Device, mocker: MockerFixture):
    """Test saving a new preset value."""
    therm_mod = next(get_parent_and_child_modules(dev, Module.Thermostat))
    assert therm_mod

    await therm_mod.set_state(False)
    await dev.update()
    assert therm_mod.state is False
    assert therm_mod.mode is ThermostatState.Off

    await therm_mod.set_target_temperature(10)
    await dev.update()
    assert therm_mod.state is True
    assert therm_mod.mode is ThermostatState.Heating
    assert therm_mod.target_temperature == 10

    target_temperature_feature = therm_mod.get_feature(therm_mod.set_target_temperature)
    temp_control = dev.modules.get(Module.TemperatureControl)
    assert temp_control
    allowed_range = temp_control.allowed_temperature_range
    assert target_temperature_feature.minimum_value == allowed_range[0]
    assert target_temperature_feature.maximum_value == allowed_range[1]

    await therm_mod.set_temperature_unit("celsius")
    await dev.update()
    assert therm_mod.temperature_unit == "celsius"

    await therm_mod.set_temperature_unit("fahrenheit")
    await dev.update()
    assert therm_mod.temperature_unit == "fahrenheit"


async def test_set_time(dev: Device):
    """Test setting the device time."""
    time_mod = dev.modules[Module.Time]

    original_time = time_mod.time
    original_timezone = time_mod.timezone

    test_time = datetime.fromisoformat("2021-01-09 12:00:00+00:00")
    test_time = test_time.astimezone(original_timezone)

    try:
        assert time_mod.time != test_time

        await time_mod.set_time(test_time)
        await dev.update()
        assert time_mod.time == test_time

        if (
            isinstance(original_timezone, ZoneInfo)
            and original_timezone.key != "Europe/Berlin"
        ):
            test_zonezone = ZoneInfo("Europe/Berlin")
        else:
            test_zonezone = ZoneInfo("Europe/London")

        # Just update the timezone
        new_time = time_mod.time.astimezone(test_zonezone)
        await time_mod.set_time(new_time)
        await dev.update()
        assert time_mod.time == new_time
    finally:
        # Reset back to the original
        await time_mod.set_time(original_time)
        await dev.update()
        assert time_mod.time == original_time
