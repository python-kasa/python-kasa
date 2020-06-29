from kasa import DeviceType

from .conftest import plug, pytestmark
from .newfakes import PLUG_SCHEMA


@plug
async def test_plug_sysinfo(dev):
    assert dev.sys_info is not None
    PLUG_SCHEMA(dev.sys_info)

    assert dev.model is not None

    assert dev.device_type == DeviceType.Plug or dev.device_type == DeviceType.Strip
    assert dev.is_plug or dev.is_strip


@plug
async def test_led(dev):
    original = dev.led

    await dev.set_led(False)
    assert not dev.led

    await dev.set_led(True)
    assert dev.led

    await dev.set_led(original)
