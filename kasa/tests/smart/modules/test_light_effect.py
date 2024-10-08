from __future__ import annotations

from itertools import chain

import pytest
from pytest_mock import MockerFixture

from kasa import Device, Feature, Module
from kasa.smart.modules import LightEffect
from kasa.tests.device_fixtures import parametrize

light_effect = parametrize(
    "has light effect", component_filter="light_effect", protocol_filter={"SMART"}
)


@light_effect
async def test_light_effect(dev: Device, mocker: MockerFixture):
    """Test light effect."""
    light_effect = dev.modules.get(Module.LightEffect)
    assert isinstance(light_effect, LightEffect)

    feature = dev.features["light_effect"]
    assert feature.type == Feature.Type.Choice

    call = mocker.spy(light_effect, "call")
    assert feature.choices == light_effect.effect_list
    assert feature.choices
    for effect in chain(reversed(feature.choices), feature.choices):
        await light_effect.set_effect(effect)
        enable = effect != LightEffect.LIGHT_EFFECTS_OFF
        params: dict[str, bool | str] = {"enable": enable}
        if enable:
            params["id"] = light_effect._scenes_names_to_id[effect]
        call.assert_called_with("set_dynamic_light_effect_rule_enable", params)
        await dev.update()
        assert light_effect.effect == effect
        assert feature.value == effect

    with pytest.raises(ValueError, match="The effect foobar is not a built in effect"):
        await light_effect.set_effect("foobar")


@light_effect
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
    if effect_active:  # Set the rule L1 active for testing
        light_effect.data["current_rule_id"] = "L1"

    await light_module.set_brightness(10)

    if effect_active:
        assert light_effect.is_active
        assert light_effect.brightness == dev.brightness

        light_effect_set_brightness.assert_called_with(10)
        mock_light_effect_call.assert_called_with(
            "edit_dynamic_light_effect_rule", mocker.ANY
        )
    else:
        assert not light_effect.is_active

        brightness_set_brightness.assert_called_with(10)
        mock_brightness_call.assert_called_with("set_device_info", {"brightness": 10})
