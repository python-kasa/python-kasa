import pytest

from kasa import DeviceType, Module
from kasa.iot import IotLightStrip
from kasa.iot.modules import LightEffect
from tests.conftest import lightstrip_iot


@lightstrip_iot
async def test_lightstrip_length(dev: IotLightStrip):
    assert dev.device_type == DeviceType.LightStrip
    assert dev.length == dev.sys_info["length"]


@lightstrip_iot
async def test_lightstrip_effect(dev: IotLightStrip):
    le: LightEffect = dev.modules[Module.LightEffect]
    assert isinstance(le._deprecated_effect, dict)
    for k in ["brightness", "custom", "enable", "id", "name"]:
        assert k in le._deprecated_effect


@lightstrip_iot
async def test_effects_lightstrip_set_effect(dev: IotLightStrip):
    le: LightEffect = dev.modules[Module.LightEffect]
    with pytest.raises(
        ValueError, match="The effect Not real is not a built in effect"
    ):
        await le.set_effect("Not real")

    await le.set_effect("Candy Cane")
    await dev.update()
    assert le.effect == "Candy Cane"


@lightstrip_iot
@pytest.mark.parametrize("brightness", [100, 50])
async def test_effects_lightstrip_set_effect_brightness(
    dev: IotLightStrip, brightness, mocker
):
    query_helper = mocker.patch("kasa.iot.IotLightStrip._query_helper")
    le: LightEffect = dev.modules[Module.LightEffect]

    # test that default brightness works (100 for candy cane)
    if brightness == 100:
        await le.set_effect("Candy Cane")
    else:
        await le.set_effect("Candy Cane", brightness=brightness)

    args, kwargs = query_helper.call_args_list[0]
    payload = args[2]
    assert payload["brightness"] == brightness


@lightstrip_iot
@pytest.mark.parametrize("transition", [500, 1000])
async def test_effects_lightstrip_set_effect_transition(
    dev: IotLightStrip, transition, mocker
):
    query_helper = mocker.patch("kasa.iot.IotLightStrip._query_helper")
    le: LightEffect = dev.modules[Module.LightEffect]

    # test that default (500 for candy cane) transition works
    if transition == 500:
        await le.set_effect("Candy Cane")
    else:
        await le.set_effect("Candy Cane", transition=transition)

    args, kwargs = query_helper.call_args_list[0]
    payload = args[2]
    assert payload["transition"] == transition


@lightstrip_iot
async def test_effects_lightstrip_has_effects(dev: IotLightStrip):
    le: LightEffect = dev.modules[Module.LightEffect]
    assert le is not None
    assert le.effect_list


@lightstrip_iot
def test_device_type_lightstrip(dev):
    assert dev.device_type == DeviceType.LightStrip
