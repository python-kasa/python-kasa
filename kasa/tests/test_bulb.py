from __future__ import annotations

import pytest
from voluptuous import (
    All,
    Boolean,
    Optional,
    Range,
    Schema,
)

from kasa import Device, DeviceType, IotLightPreset, KasaException, Module
from kasa.iot import IotBulb, IotDimmer

from .conftest import (
    bulb,
    bulb_iot,
    color_bulb,
    color_bulb_iot,
    dimmable_iot,
    handle_turn_on,
    non_color_bulb,
    non_dimmable_iot,
    non_variable_temp,
    turn_on,
    variable_temp,
    variable_temp_iot,
    variable_temp_smart,
)
from .test_iotdevice import SYSINFO_SCHEMA


@bulb
async def test_bulb_sysinfo(dev: Device):
    assert dev.sys_info is not None
    SYSINFO_SCHEMA_BULB(dev.sys_info)

    assert dev.model is not None

    # TODO: remove special handling for lightstrip
    if not dev.is_light_strip:
        assert dev.device_type == DeviceType.Bulb
        assert dev.is_bulb


@bulb
async def test_state_attributes(dev: Device):
    assert "Cloud connection" in dev.state_information
    assert isinstance(dev.state_information["Cloud connection"], bool)


@bulb_iot
async def test_light_state_without_update(dev: IotBulb, monkeypatch):
    with pytest.raises(KasaException):
        monkeypatch.setitem(
            dev._last_update["system"]["get_sysinfo"], "light_state", None
        )
        print(dev.light_state)


@bulb_iot
async def test_get_light_state(dev: IotBulb):
    LIGHT_STATE_SCHEMA(await dev.get_light_state())


@color_bulb
@turn_on
async def test_hsv(dev: Device, turn_on):
    light = dev.modules.get(Module.Light)
    assert light
    await handle_turn_on(dev, turn_on)
    assert light.is_color

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


@color_bulb_iot
async def test_set_hsv_transition(dev: IotBulb, mocker):
    set_light_state = mocker.patch("kasa.iot.IotBulb._set_light_state")
    await dev.set_hsv(10, 10, 100, transition=1000)

    set_light_state.assert_called_with(
        {"hue": 10, "saturation": 10, "brightness": 100, "color_temp": 0},
        transition=1000,
    )


@color_bulb
@turn_on
async def test_invalid_hsv(dev: Device, turn_on):
    light = dev.modules.get(Module.Light)
    assert light
    await handle_turn_on(dev, turn_on)
    assert light.is_color

    for invalid_hue in [-1, 361, 0.5]:
        with pytest.raises(ValueError):
            await light.set_hsv(invalid_hue, 0, 0)  # type: ignore[arg-type]

    for invalid_saturation in [-1, 101, 0.5]:
        with pytest.raises(ValueError):
            await light.set_hsv(0, invalid_saturation, 0)  # type: ignore[arg-type]

    for invalid_brightness in [-1, 101, 0.5]:
        with pytest.raises(ValueError):
            await light.set_hsv(0, 0, invalid_brightness)  # type: ignore[arg-type]


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
    assert not light.is_color

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


@variable_temp_iot
async def test_set_color_temp_transition(dev: IotBulb, mocker):
    set_light_state = mocker.patch("kasa.iot.IotBulb._set_light_state")
    await dev.set_color_temp(2700, transition=100)

    set_light_state.assert_called_with({"color_temp": 2700}, transition=100)


@variable_temp_iot
async def test_unknown_temp_range(dev: IotBulb, monkeypatch, caplog):
    monkeypatch.setitem(dev._sys_info, "model", "unknown bulb")

    assert dev.valid_temperature_range == (2700, 5000)
    assert "Unknown color temperature range, fallback to 2700-5000" in caplog.text


@variable_temp_smart
async def test_smart_temp_range(dev: Device):
    light = dev.modules.get(Module.Light)
    assert light
    assert light.valid_temperature_range


@variable_temp
async def test_out_of_range_temperature(dev: Device):
    light = dev.modules.get(Module.Light)
    assert light
    with pytest.raises(ValueError):
        await light.set_color_temp(1000)
    with pytest.raises(ValueError):
        await light.set_color_temp(10000)


@non_variable_temp
async def test_non_variable_temp(dev: Device):
    light = dev.modules.get(Module.Light)
    assert light
    with pytest.raises(KasaException):
        await light.set_color_temp(2700)

    with pytest.raises(KasaException):
        print(light.valid_temperature_range)

    with pytest.raises(KasaException):
        print(light.color_temp)


@dimmable_iot
@turn_on
async def test_dimmable_brightness(dev: IotBulb, turn_on):
    assert isinstance(dev, (IotBulb, IotDimmer))
    await handle_turn_on(dev, turn_on)
    assert dev._is_dimmable

    await dev.set_brightness(50)
    await dev.update()
    assert dev.brightness == 50

    await dev.set_brightness(10)
    await dev.update()
    assert dev.brightness == 10

    with pytest.raises(ValueError):
        await dev.set_brightness("foo")  # type: ignore[arg-type]


@bulb_iot
async def test_turn_on_transition(dev: IotBulb, mocker):
    set_light_state = mocker.patch("kasa.iot.IotBulb._set_light_state")
    await dev.turn_on(transition=1000)

    set_light_state.assert_called_with({"on_off": 1}, transition=1000)

    await dev.turn_off(transition=100)

    set_light_state.assert_called_with({"on_off": 0}, transition=100)


@bulb_iot
async def test_dimmable_brightness_transition(dev: IotBulb, mocker):
    set_light_state = mocker.patch("kasa.iot.IotBulb._set_light_state")
    await dev.set_brightness(10, transition=1000)

    set_light_state.assert_called_with({"brightness": 10}, transition=1000)


@dimmable_iot
async def test_invalid_brightness(dev: IotBulb):
    assert dev._is_dimmable

    with pytest.raises(ValueError):
        await dev.set_brightness(110)

    with pytest.raises(ValueError):
        await dev.set_brightness(-100)


@non_dimmable_iot
async def test_non_dimmable(dev: IotBulb):
    assert not dev._is_dimmable

    with pytest.raises(KasaException):
        assert dev.brightness == 0
    with pytest.raises(KasaException):
        await dev.set_brightness(100)


@bulb_iot
async def test_ignore_default_not_set_without_color_mode_change_turn_on(
    dev: IotBulb, mocker
):
    query_helper = mocker.patch("kasa.iot.IotBulb._query_helper")
    # When turning back without settings, ignore default to restore the state
    await dev.turn_on()
    args, kwargs = query_helper.call_args_list[0]
    assert args[2] == {"on_off": 1, "ignore_default": 0}

    await dev.turn_off()
    args, kwargs = query_helper.call_args_list[1]
    assert args[2] == {"on_off": 0, "ignore_default": 1}


@bulb_iot
async def test_list_presets(dev: IotBulb):
    presets = dev.presets
    assert len(presets) == len(dev.sys_info["preferred_state"])

    for preset, raw in zip(presets, dev.sys_info["preferred_state"]):
        assert preset.index == raw["index"]
        assert preset.hue == raw["hue"]
        assert preset.brightness == raw["brightness"]
        assert preset.saturation == raw["saturation"]
        assert preset.color_temp == raw["color_temp"]


@bulb_iot
async def test_modify_preset(dev: IotBulb, mocker):
    """Verify that modifying preset calls the and exceptions are raised properly."""
    if not dev.presets:
        pytest.skip("Some strips do not support presets")

    data: dict[str, int | None] = {
        "index": 0,
        "brightness": 10,
        "hue": 0,
        "saturation": 0,
        "color_temp": 0,
    }
    preset = IotLightPreset(**data)  # type: ignore[call-arg, arg-type]

    assert preset.index == 0
    assert preset.brightness == 10
    assert preset.hue == 0
    assert preset.saturation == 0
    assert preset.color_temp == 0

    await dev.save_preset(preset)
    await dev.update()
    assert dev.presets[0].brightness == 10

    with pytest.raises(KasaException):
        await dev.save_preset(
            IotLightPreset(index=5, hue=0, brightness=0, saturation=0, color_temp=0)  # type: ignore[call-arg]
        )


@bulb_iot
@pytest.mark.parametrize(
    ("preset", "payload"),
    [
        (
            IotLightPreset(index=0, hue=0, brightness=1, saturation=0),  # type: ignore[call-arg]
            {"index": 0, "hue": 0, "brightness": 1, "saturation": 0},
        ),
        (
            IotLightPreset(index=0, brightness=1, id="testid", mode=2, custom=0),  # type: ignore[call-arg]
            {"index": 0, "brightness": 1, "id": "testid", "mode": 2, "custom": 0},
        ),
    ],
)
async def test_modify_preset_payloads(dev: IotBulb, preset, payload, mocker):
    """Test that modify preset payloads ignore none values."""
    if not dev.presets:
        pytest.skip("Some strips do not support presets")

    query_helper = mocker.patch("kasa.iot.IotBulb._query_helper")
    await dev.save_preset(preset)
    query_helper.assert_called_with(dev.LIGHT_SERVICE, "set_preferred_state", payload)


LIGHT_STATE_SCHEMA = Schema(
    {
        "brightness": All(int, Range(min=0, max=100)),
        "color_temp": int,
        "hue": All(int, Range(min=0, max=360)),
        "mode": str,
        "on_off": Boolean,
        "saturation": All(int, Range(min=0, max=100)),
        "dft_on_state": Optional(
            {
                "brightness": All(int, Range(min=0, max=100)),
                "color_temp": All(int, Range(min=0, max=9000)),
                "hue": All(int, Range(min=0, max=360)),
                "mode": str,
                "saturation": All(int, Range(min=0, max=100)),
            }
        ),
        "err_code": int,
    }
)

SYSINFO_SCHEMA_BULB = SYSINFO_SCHEMA.extend(
    {
        "ctrl_protocols": Optional(dict),
        "description": Optional(str),  # Seen on LBxxx, similar to dev_name
        "dev_state": str,
        "disco_ver": str,
        "heapsize": int,
        "is_color": Boolean,
        "is_dimmable": Boolean,
        "is_factory": Boolean,
        "is_variable_color_temp": Boolean,
        "light_state": LIGHT_STATE_SCHEMA,
        "preferred_state": [
            {
                "brightness": All(int, Range(min=0, max=100)),
                "color_temp": int,
                "hue": All(int, Range(min=0, max=360)),
                "index": int,
                "saturation": All(int, Range(min=0, max=100)),
            }
        ],
    }
)


@bulb
def test_device_type_bulb(dev: Device):
    if dev.is_light_strip:
        pytest.skip("bulb has also lightstrips to test the api")
    assert dev.device_type == DeviceType.Bulb
