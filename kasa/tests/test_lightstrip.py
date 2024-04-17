from __future__ import annotations

import pytest

from kasa import DeviceType
from kasa.exceptions import KasaException
from kasa.iot import IotLightStrip

from .conftest import lightstrip


@lightstrip
async def test_lightstrip_length(dev: IotLightStrip):
    assert dev.is_light_strip
    assert dev.device_type == DeviceType.LightStrip
    assert dev.length == dev.sys_info["length"]


@lightstrip
async def test_lightstrip_effect(dev: IotLightStrip):
    assert isinstance(dev.effect, dict)
    for k in ["brightness", "custom", "enable", "id", "name"]:
        assert k in dev.effect


@lightstrip
async def test_effects_lightstrip_set_effect(dev: IotLightStrip):
    with pytest.raises(KasaException):
        await dev.set_effect("Not real")

    await dev.set_effect("Candy Cane")
    assert dev.effect["name"] == "Candy Cane"


@lightstrip
@pytest.mark.parametrize("brightness", [100, 50])
async def test_effects_lightstrip_set_effect_brightness(
    dev: IotLightStrip, brightness, mocker
):
    query_helper = mocker.patch("kasa.iot.IotLightStrip._query_helper")

    # test that default brightness works (100 for candy cane)
    if brightness == 100:
        await dev.set_effect("Candy Cane")
    else:
        await dev.set_effect("Candy Cane", brightness=brightness)

    args, kwargs = query_helper.call_args_list[0]
    payload = args[2]
    assert payload["brightness"] == brightness


@lightstrip
@pytest.mark.parametrize("transition", [500, 1000])
async def test_effects_lightstrip_set_effect_transition(
    dev: IotLightStrip, transition, mocker
):
    query_helper = mocker.patch("kasa.iot.IotLightStrip._query_helper")

    # test that default (500 for candy cane) transition works
    if transition == 500:
        await dev.set_effect("Candy Cane")
    else:
        await dev.set_effect("Candy Cane", transition=transition)

    args, kwargs = query_helper.call_args_list[0]
    payload = args[2]
    assert payload["transition"] == transition


@lightstrip
async def test_effects_lightstrip_has_effects(dev: IotLightStrip):
    assert dev.has_effects is True
    assert dev.effect_list


@lightstrip
def test_device_type_lightstrip(dev):
    assert dev.device_type == DeviceType.LightStrip
