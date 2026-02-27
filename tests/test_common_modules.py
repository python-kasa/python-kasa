import importlib
import inspect
import pkgutil
import sys
from datetime import UTC, datetime, timedelta, timezone
from unittest.mock import AsyncMock
from zoneinfo import ZoneInfo

import pytest
from pytest_mock import MockerFixture

import kasa.interfaces
from kasa import Device, KasaException, LightState, Module, ThermostatState
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
    feature = light.device.features["brightness"]
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
    feature = light.device.features["color_temperature"]
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
    if light_effect := light.device.modules.get(Module.LightEffect):
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
    feat = preset_mod.device.features["light_preset"]

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


async def test_time_post_update_no_time_uses_utc_unit(monkeypatch: pytest.MonkeyPatch):
    """If neither get_timezone nor get_time are present, timezone falls back to UTC."""
    from kasa.iot.modules.time import Time as TimeModule

    inst = object.__new__(TimeModule)
    monkeypatch.setattr(TimeModule, "data", property(lambda self: {}))

    await TimeModule._post_update_hook(inst)
    assert inst.timezone is UTC


async def test_time_post_update_uses_offset_when_index_missing_unit(
    monkeypatch: pytest.MonkeyPatch, mocker: MockerFixture
):
    """When index present but zone not on host, fall back to offset-based guess."""
    from zoneinfo import ZoneInfoNotFoundError

    from kasa.iot.modules.time import Time as TimeModule

    inst = object.__new__(TimeModule)

    now = datetime.now(UTC)
    data = {
        "get_timezone": {"index": 39},  # any index; we'll force failure to load it
        "get_time": {
            "year": now.year,
            "month": now.month,
            "mday": now.day,
            "hour": now.hour,
            "min": now.minute,
            "sec": now.second,
        },
    }
    monkeypatch.setattr(TimeModule, "data", property(lambda self: data))

    mocker.patch(
        "kasa.iot.modules.time.get_timezone",
        new=AsyncMock(side_effect=ZoneInfoNotFoundError("missing on host")),
    )
    mock_guess = mocker.patch(
        "kasa.iot.modules.time._guess_timezone_by_offset",
        new=AsyncMock(return_value=timezone(timedelta(0))),
    )

    await TimeModule._post_update_hook(inst)
    mock_guess.assert_awaited_once()
    # timezone should be set to a valid tzinfo after fallback
    assert inst.timezone.utcoffset(now) == timedelta(0)


async def test_time_get_time_exception_returns_none_unit(mocker: MockerFixture):
    """Cover Time.get_time exception path (unit test of iot Time)."""
    from kasa.iot.modules.time import Time as TimeModule

    inst = object.__new__(TimeModule)
    mocker.patch.object(inst, "call", new=AsyncMock(side_effect=KasaException("boom")))

    assert await TimeModule.get_time(inst) is None


async def test_time_get_time_success_unit(mocker: MockerFixture):
    """Cover the success path of Time.get_time."""
    from kasa.iot.modules.time import Time as TimeModule

    inst = object.__new__(TimeModule)
    # Ensure timezone is available on the instance
    inst._timezone = UTC
    ret = {
        "year": 2024,
        "month": 1,
        "mday": 2,
        "hour": 3,
        "min": 4,
        "sec": 5,
    }
    mocker.patch.object(inst, "call", new=AsyncMock(return_value=ret))

    dt = await TimeModule.get_time(inst)
    assert dt is not None
    assert (dt.year, dt.month, dt.day, dt.hour, dt.minute, dt.second) == (
        2024,
        1,
        2,
        3,
        4,
        5,
    )
    assert dt.tzinfo == inst.timezone


async def test_time_post_update_with_time_no_tz_uses_guess_unit(
    monkeypatch: pytest.MonkeyPatch, mocker: MockerFixture
):
    """When get_time is present but get_timezone is missing, use offset-based guess (dst_expected None)."""
    from kasa.iot.modules.time import Time as TimeModule

    inst = object.__new__(TimeModule)
    now = datetime.now(UTC)
    data = {
        "get_time": {
            "year": now.year,
            "month": now.month,
            "mday": now.day,
            "hour": now.hour,
            "min": now.minute,
            "sec": now.second,
        }
        # Note: no "get_timezone" key
    }
    monkeypatch.setattr(TimeModule, "data", property(lambda self: data))

    mock_guess = mocker.patch(
        "kasa.iot.modules.time._guess_timezone_by_offset",
        new=AsyncMock(return_value=timezone(timedelta(hours=2))),
    )

    await TimeModule._post_update_hook(inst)
    mock_guess.assert_awaited_once()
    assert inst.timezone.utcoffset(now) == timedelta(hours=2)


async def test_time_set_time_wraps_exception_unit(
    monkeypatch: pytest.MonkeyPatch, mocker: MockerFixture
):
    """Cover exception wrapping in Time.set_time (unit test of iot Time)."""
    from kasa.iot.modules.time import Time as TimeModule

    inst = object.__new__(TimeModule)
    # Keep data empty so set_time path is chosen (no timezone change)
    monkeypatch.setattr(TimeModule, "data", property(lambda self: {}))
    mocker.patch.object(inst, "call", new=AsyncMock(side_effect=RuntimeError("err")))

    with pytest.raises(KasaException):
        await TimeModule.set_time(inst, datetime.now())


# New tests to cover remaining smart and smartcam time.py branches


async def test_smart_time_set_time_no_region_added_when_tzname_none_unit(
    mocker: MockerFixture,
):
    """In smart Time.set_time, ensure we cover the branch where tzname() returns None, so 'region' is omitted."""
    from datetime import tzinfo as _tzinfo

    from kasa.smart.modules.time import Time as SmartTimeModule

    class NullNameTZ(_tzinfo):
        def utcoffset(self, dt):
            return timedelta(hours=1)

        def dst(self, dt):
            return timedelta(0)

        def tzname(self, dt):
            return None

    inst = object.__new__(SmartTimeModule)
    call_mock = mocker.patch.object(inst, "call", new=AsyncMock(return_value={}))

    aware_dt = datetime(2024, 1, 1, 12, 0, 0, tzinfo=NullNameTZ())
    await SmartTimeModule.set_time(inst, aware_dt)

    call_mock.assert_awaited_once()
    args, _ = call_mock.call_args
    assert args[0] == "set_device_time"
    params = args[1]
    # 'region' must not be present when tzname() is None
    assert "region" not in params
    # sanity: timestamp and time_diff still provided
    assert isinstance(params["timestamp"], int)
    assert isinstance(params["time_diff"], int)


async def test_smartcam_time_post_update_fallback_parses_timezone_str_unit(
    monkeypatch: pytest.MonkeyPatch, mocker: MockerFixture
):
    """Exercise smartcam Time._post_update_hook fallback when ZoneInfo not found, parsing 'timezone' string."""
    from zoneinfo import ZoneInfoNotFoundError

    from kasa.smartcam.modules.time import Time as CamTimeModule

    inst = object.__new__(CamTimeModule)
    # Provide data with an unknown zone_id but with a 'timezone' string like 'UTC+02:00'
    ts = 1_700_000_000
    data = {
        "getClockStatus": {"system": {"clock_status": {"seconds_from_1970": ts}}},
        "getTimezone": {
            "system": {"basic": {"zone_id": "Nowhere/Unknown", "timezone": "UTC+02:00"}}
        },
    }
    monkeypatch.setattr(CamTimeModule, "data", property(lambda self: data))

    # Patch directly via the module path instead of sys.modules lookup
    mocker.patch(
        "kasa.smartcam.modules.time.CachedZoneInfo.get_cached_zone_info",
        new=AsyncMock(side_effect=ZoneInfoNotFoundError("missing on host")),
    )

    await CamTimeModule._post_update_hook(inst)

    # Check timezone fallback parsed to +02:00
    now_local = datetime.now(inst.timezone)
    assert inst.timezone.utcoffset(now_local) == timedelta(hours=2)

    # Check time set from seconds_from_1970 and is tz-aware with the chosen tz
    assert isinstance(inst.time, datetime)
    assert inst.time.tzinfo == inst.timezone
    assert int(inst.time.timestamp()) == ts


async def test_smartcam_set_time_separate_timezone_and_clock_calls_unit(
    monkeypatch: pytest.MonkeyPatch,
    mocker: MockerFixture,
):
    """Smartcam set_time should call setTimezone first, then setClockStatus."""
    from kasa.smartcam.modules.time import Time as CamTimeModule

    inst = object.__new__(CamTimeModule)
    fake_data = {
        "getTimezone": {
            "system": {
                "basic": {
                    "timing_mode": "ntp",
                    "zone_id": "UTC",
                    "timezone": "UTC+00:00",
                }
            }
        }
    }
    monkeypatch.setattr(CamTimeModule, "data", property(lambda self: fake_data))
    call_mock = mocker.patch.object(
        inst,
        "call",
        new=AsyncMock(side_effect=[{"tz": True}, {"clock": True}]),
    )

    test_dt = datetime(2026, 2, 24, 20, 30, 0, tzinfo=ZoneInfo("America/New_York"))
    res = await CamTimeModule.set_time(inst, test_dt)

    assert call_mock.await_count == 2
    first_args, _ = call_mock.await_args_list[0]
    second_args, _ = call_mock.await_args_list[1]

    assert first_args[0] == "setTimezone"
    assert second_args[0] == "setClockStatus"

    basic = first_args[1]["system"]["basic"]
    assert basic["timing_mode"] == "manual"
    assert basic["zone_id"] == "America/New_York"
    assert basic["timezone"] == "UTC-05:00"

    clock = second_args[1]["system"]["clock_status"]
    assert clock["local_time"] == "2026-02-25 01:30:00"
    assert clock["seconds_from_1970"] == int(test_dt.timestamp())

    assert res == {"setTimezone": {"tz": True}, "setClockStatus": {"clock": True}}


async def test_smartcam_set_time_naive_datetime_uses_device_timezone_unit(
    monkeypatch: pytest.MonkeyPatch,
    mocker: MockerFixture,
):
    """Naive datetime should use current device timezone for timestamp/offset."""
    from kasa.smartcam.modules.time import Time as CamTimeModule

    inst = object.__new__(CamTimeModule)
    inst._timezone = ZoneInfo("America/New_York")
    fake_data = {
        "getTimezone": {
            "system": {
                "basic": {
                    "timing_mode": "ntp",
                    "zone_id": "UTC",
                    "timezone": "UTC+00:00",
                }
            }
        }
    }
    monkeypatch.setattr(CamTimeModule, "data", property(lambda self: fake_data))
    call_mock = mocker.patch.object(
        inst,
        "call",
        new=AsyncMock(side_effect=[{}, {}]),
    )

    naive_dt = datetime(2026, 2, 24, 20, 30, 0)
    await CamTimeModule.set_time(inst, naive_dt)

    first_args, _ = call_mock.await_args_list[0]
    second_args, _ = call_mock.await_args_list[1]

    basic = first_args[1]["system"]["basic"]
    assert basic["timezone"] == "UTC-05:00"
    assert "zone_id" not in basic

    clock = second_args[1]["system"]["clock_status"]
    expected_ts = int(naive_dt.replace(tzinfo=inst.timezone).timestamp())
    assert clock["seconds_from_1970"] == expected_ts
