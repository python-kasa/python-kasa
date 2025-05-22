from __future__ import annotations

import re

import pytest
from voluptuous import (
    All,
    Boolean,
    Optional,
    Range,
    Schema,
)

from kasa import Device, IotLightPreset, KasaException, LightState, Module
from kasa.iot import IotBulb, IotDimmer
from kasa.iot.modules import LightPreset as IotLightPresetModule
from tests.conftest import (
    bulb_iot,
    color_bulb_iot,
    dimmable_iot,
    handle_turn_on,
    non_dimmable_iot,
    turn_on,
    variable_temp_iot,
)
from tests.iot.test_iotdevice import SYSINFO_SCHEMA


@bulb_iot
async def test_bulb_sysinfo(dev: Device):
    assert dev.sys_info is not None
    SYSINFO_SCHEMA_BULB(dev.sys_info)

    assert dev.model is not None


@bulb_iot
async def test_light_state_without_update(dev: IotBulb, monkeypatch):
    monkeypatch.setitem(dev._last_update["system"]["get_sysinfo"], "light_state", None)
    with pytest.raises(KasaException):
        print(dev.light_state)


@bulb_iot
async def test_get_light_state(dev: IotBulb):
    LIGHT_STATE_SCHEMA(await dev.get_light_state())


@color_bulb_iot
async def test_set_hsv_transition(dev: IotBulb, mocker):
    set_light_state = mocker.patch("kasa.iot.IotBulb._set_light_state")
    light = dev.modules.get(Module.Light)
    assert light
    await light.set_hsv(10, 10, 100, transition=1000)

    set_light_state.assert_called_with(
        {"hue": 10, "saturation": 10, "brightness": 100, "color_temp": 0},
        transition=1000,
    )


@bulb_iot
async def test_light_set_state(dev: IotBulb, mocker):
    """Testing setting LightState on the light module."""
    light = dev.modules.get(Module.Light)
    assert light
    set_light_state = mocker.spy(dev, "_set_light_state")
    state = LightState(light_on=True)
    await light.set_state(state)

    set_light_state.assert_called_with({"on_off": 1}, transition=None)
    state = LightState(light_on=False)
    await light.set_state(state)

    set_light_state.assert_called_with({"on_off": 0}, transition=None)


@variable_temp_iot
async def test_set_color_temp_transition(dev: IotBulb, mocker):
    set_light_state = mocker.patch("kasa.iot.IotBulb._set_light_state")
    light = dev.modules.get(Module.Light)
    assert light
    await light.set_color_temp(2700, transition=100)

    set_light_state.assert_called_with({"color_temp": 2700}, transition=100)


@variable_temp_iot
@pytest.mark.xdist_group(name="caplog")
async def test_unknown_temp_range(dev: IotBulb, monkeypatch, caplog):
    monkeypatch.setitem(dev._sys_info, "model", "unknown bulb")
    light = dev.modules.get(Module.Light)
    assert light
    color_temp_feat = light.get_feature("color_temp")
    assert color_temp_feat
    assert color_temp_feat.range == (2700, 5000)
    assert "Unknown color temperature range, fallback to 2700-5000" in caplog.text


@dimmable_iot
@turn_on
async def test_dimmable_brightness(dev: IotBulb, turn_on):
    assert isinstance(dev, IotBulb | IotDimmer)
    light = dev.modules.get(Module.Light)
    assert light
    await handle_turn_on(dev, turn_on)
    assert dev._is_dimmable

    await light.set_brightness(50)
    await dev.update()
    assert light.brightness == 50

    await light.set_brightness(10)
    await dev.update()
    assert light.brightness == 10

    with pytest.raises(TypeError, match="Brightness must be an integer"):
        await light.set_brightness("foo")  # type: ignore[arg-type]


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
    light = dev.modules.get(Module.Light)
    assert light
    await light.set_brightness(10, transition=1000)

    set_light_state.assert_called_with({"brightness": 10, "on_off": 1}, transition=1000)


@dimmable_iot
async def test_invalid_brightness(dev: IotBulb):
    assert dev._is_dimmable
    light = dev.modules.get(Module.Light)
    assert light
    with pytest.raises(
        ValueError,
        match=re.escape("Invalid brightness value: 110 (valid range: 0-100%)"),
    ):
        await light.set_brightness(110)

    with pytest.raises(
        ValueError,
        match=re.escape("Invalid brightness value: -100 (valid range: 0-100%)"),
    ):
        await light.set_brightness(-100)


@non_dimmable_iot
async def test_non_dimmable(dev: IotBulb):
    assert not dev._is_dimmable
    light = dev.modules.get(Module.Light)
    assert light
    with pytest.raises(KasaException):
        assert light.brightness == 0
    with pytest.raises(KasaException):
        await light.set_brightness(100)


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
    light_preset = dev.modules.get(Module.LightPreset)
    assert light_preset
    assert isinstance(light_preset, IotLightPresetModule)
    presets = light_preset._deprecated_presets
    # Light strip devices may list some light effects along with normal presets but these
    # are handled by the LightEffect module so exclude preferred states with id
    raw_presets = [
        pstate for pstate in dev.sys_info["preferred_state"] if "id" not in pstate
    ]
    assert len(presets) == len(raw_presets)

    for preset, raw in zip(presets, raw_presets, strict=False):
        assert preset.index == raw["index"]
        assert preset.brightness == raw["brightness"]
        assert preset.hue == raw["hue"]
        assert preset.saturation == raw["saturation"]
        assert preset.color_temp == raw["color_temp"]


@bulb_iot
async def test_modify_preset(dev: IotBulb, mocker):
    """Verify that modifying preset calls the and exceptions are raised properly."""
    if (
        not (light_preset := dev.modules.get(Module.LightPreset))
        or not light_preset._deprecated_presets
    ):
        pytest.skip("Some strips do not support presets")

    assert isinstance(light_preset, IotLightPresetModule)
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

    await light_preset._deprecated_save_preset(preset)
    await dev.update()
    assert light_preset._deprecated_presets[0].brightness == 10

    with pytest.raises(KasaException):
        await light_preset._deprecated_save_preset(
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
    if (
        not (light_preset := dev.modules.get(Module.LightPreset))
        or not light_preset._deprecated_presets
    ):
        pytest.skip("Some strips do not support presets")

    query_helper = mocker.patch("kasa.iot.IotBulb._query_helper")
    await light_preset._deprecated_save_preset(preset)
    query_helper.assert_called_with(dev.LIGHT_SERVICE, "set_preferred_state", payload)


LIGHT_STATE_SCHEMA = Schema(
    {
        "brightness": All(int, Range(min=0, max=100)),
        "color_temp": int,
        "hue": All(int, Range(min=0, max=360)),
        "mode": str,
        "on_off": Boolean,
        "saturation": All(int, Range(min=0, max=100)),
        "length": Optional(int),
        "transition": Optional(int),
        "dft_on_state": Optional(
            {
                "brightness": All(int, Range(min=0, max=100)),
                "color_temp": All(int, Range(min=0, max=9000)),
                "hue": All(int, Range(min=0, max=360)),
                "mode": str,
                "saturation": All(int, Range(min=0, max=100)),
                "groups": Optional(list[int]),
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


@bulb_iot
async def test_turn_on_behaviours(dev: IotBulb):
    behavior = await dev.get_turn_on_behavior()
    assert behavior
