import pytest

from kasa import DeviceType, SmartLightStrip
from kasa.exceptions import SmartDeviceException

from .conftest import lightstrip


@lightstrip
async def test_lightstrip_length(dev: SmartLightStrip):
    assert dev.is_light_strip
    assert dev.device_type == DeviceType.LightStrip
    assert dev.length == dev.sys_info["length"]


@lightstrip
async def test_lightstrip_effect(dev: SmartLightStrip):
    assert isinstance(dev.effect, dict)
    for k in ["brightness", "custom", "enable", "id", "name"]:
        assert k in dev.effect


@lightstrip
async def test_effects_lightstrip_set_effect(dev: SmartLightStrip):
    with pytest.raises(SmartDeviceException):
        await dev.set_effect("Not real")

    await dev.set_effect("Candy Cane")
    assert dev.effect["name"] == "Candy Cane"
    assert dev.state_information["Effect"] == "Candy Cane"


@lightstrip
@pytest.mark.parametrize("brightness", [100, 50])
async def test_effects_lightstrip_set_effect_brightness(
    dev: SmartLightStrip, brightness, mocker
):
    query_helper = mocker.patch("kasa.SmartLightStrip._query_helper")

    if brightness == 100:  # test that default brightness works
        await dev.set_effect("Candy Cane")
    else:
        await dev.set_effect("Candy Cane", brightness=brightness)

    args, kwargs = query_helper.call_args_list[0]
    payload = args[2]
    assert payload["brightness"] == brightness


@lightstrip
async def test_effects_lightstrip_has_effects(dev: SmartLightStrip):
    assert dev.has_effects is True
    assert dev.effect_list
