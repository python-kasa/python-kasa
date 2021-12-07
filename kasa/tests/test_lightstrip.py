from kasa import DeviceType, SmartLightStrip

from .conftest import lightstrip, pytestmark


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
