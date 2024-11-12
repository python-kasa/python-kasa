from kasa import DeviceType

from .conftest import plug, plug_iot, plug_smart, switch_smart, wallswitch_iot
from .test_iotdevice import SYSINFO_SCHEMA

# these schemas should go to the mainlib as
# they can be useful when adding support for new features/devices
# as well as to check that faked devices are operating properly.


@plug_iot
async def test_plug_sysinfo(dev):
    assert dev.sys_info is not None
    SYSINFO_SCHEMA(dev.sys_info)

    assert dev.model is not None

    assert dev.device_type == DeviceType.Plug or dev.device_type == DeviceType.Strip
    assert dev.is_plug or dev.is_strip


@wallswitch_iot
async def test_switch_sysinfo(dev):
    assert dev.sys_info is not None
    SYSINFO_SCHEMA(dev.sys_info)

    assert dev.model is not None

    assert dev.device_type == DeviceType.WallSwitch
    assert dev.is_wallswitch


@plug_iot
async def test_plug_led(dev):
    original = dev.led

    await dev.set_led(False)
    await dev.update()
    assert not dev.led

    await dev.set_led(True)
    await dev.update()
    assert dev.led

    await dev.set_led(original)


@wallswitch_iot
async def test_switch_led(dev):
    original = dev.led

    await dev.set_led(False)
    await dev.update()
    assert not dev.led

    await dev.set_led(True)
    await dev.update()
    assert dev.led

    await dev.set_led(original)


@plug_smart
async def test_plug_device_info(dev):
    assert dev._info is not None
    assert dev.model is not None

    assert dev.device_type == DeviceType.Plug or dev.device_type == DeviceType.Strip


@switch_smart
async def test_switch_device_info(dev):
    assert dev._info is not None
    assert dev.model is not None

    assert (
        dev.device_type == DeviceType.WallSwitch or dev.device_type == DeviceType.Dimmer
    )


@plug
def test_device_type_plug(dev):
    assert dev.device_type == DeviceType.Plug
