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

    with pytest.raises(ValueError):
        await light_effect.set_effect("foobar")
