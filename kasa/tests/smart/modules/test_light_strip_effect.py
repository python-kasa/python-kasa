from __future__ import annotations

from itertools import chain

import pytest
from pytest_mock import MockerFixture

from kasa import Device, Feature, Module
from kasa.smart.modules import LightEffect, LightStripEffect
from kasa.tests.device_fixtures import parametrize

light_strip_effect = parametrize(
    "has light strip effect",
    component_filter="light_strip_lighting_effect",
    protocol_filter={"SMART"},
)


@light_strip_effect
async def test_light_strip_effect(dev: Device, mocker: MockerFixture):
    """Test light strip effect."""
    light_effect = dev.modules.get(Module.LightEffect)

    assert isinstance(light_effect, LightStripEffect)

    brightness = dev.modules[Module.Brightness]

    feature = dev.features["light_effect"]
    assert feature.type == Feature.Type.Choice

    call = mocker.spy(light_effect, "call")

    light = dev.modules[Module.Light]
    light_call = mocker.spy(light, "call")

    assert feature.choices == light_effect.effect_list
    assert feature.choices
    for effect in chain(reversed(feature.choices), feature.choices):
        await light_effect.set_effect(effect)

        if effect == LightEffect.LIGHT_EFFECTS_OFF:
            light_call.assert_called()
            continue

        # Start with the current effect data
        params = light_effect.data["lighting_effect"]
        enable = effect != LightEffect.LIGHT_EFFECTS_OFF
        params["enable"] = enable
        if enable:
            params = light_effect._effect_mapping[effect]
            params["enable"] = enable
            params["brightness"] = brightness.brightness  # use the existing brightness

        call.assert_called_with("set_lighting_effect", params)

        await dev.update()
        assert light_effect.effect == effect
        assert feature.value == effect

    with pytest.raises(ValueError):
        await light_effect.set_effect("foobar")


@light_strip_effect
@pytest.mark.parametrize("effect_active", [True, False])
async def test_light_effect_brightness(
    dev: Device, effect_active: bool, mocker: MockerFixture
):
    """Test that light module uses light_effect for brightness when active."""
    light_module = dev.modules[Module.Light]

    light_effect = dev.modules[Module.SmartLightEffect]
    light_effect_set_brightness = mocker.spy(light_effect, "set_brightness")
    mock_light_effect_call = mocker.patch.object(light_effect, "call")

    brightness = dev.modules[Module.Brightness]
    brightness_set_brightness = mocker.spy(brightness, "set_brightness")
    mock_brightness_call = mocker.patch.object(brightness, "call")

    mocker.patch.object(
        type(light_effect),
        "is_active",
        new_callable=mocker.PropertyMock,
        return_value=effect_active,
    )

    await light_module.set_brightness(10)

    if effect_active:
        assert light_effect.is_active
        assert light_effect.brightness == dev.brightness

        light_effect_set_brightness.assert_called_with(10)
        mock_light_effect_call.assert_called_with(
            "set_lighting_effect", {"brightness": 10, "bAdjusted": True}
        )
    else:
        assert not light_effect.is_active

        brightness_set_brightness.assert_called_with(10)
        mock_brightness_call.assert_called_with("set_device_info", {"brightness": 10})
