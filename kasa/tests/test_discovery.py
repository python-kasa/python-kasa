# type: ignore
import pytest  # type: ignore # https://github.com/pytest-dev/pytest/issues/3342

from kasa import DeviceType, Discover, SmartDevice, SmartDeviceException

from .conftest import bulb, dimmer, plug, pytestmark, strip


@plug
async def test_type_detection_plug(dev: SmartDevice):
    d = Discover._get_device_class(dev.protocol.discovery_data)("localhost")
    assert d.is_plug
    assert d.device_type == DeviceType.Plug


@bulb
async def test_type_detection_bulb(dev: SmartDevice):
    d = Discover._get_device_class(dev.protocol.discovery_data)("localhost")
    assert d.is_bulb
    assert d.device_type == DeviceType.Bulb


@strip
async def test_type_detection_strip(dev: SmartDevice):
    d = Discover._get_device_class(dev.protocol.discovery_data)("localhost")
    assert d.is_strip
    assert d.device_type == DeviceType.Strip


@dimmer
async def test_type_detection_dimmer(dev: SmartDevice):
    d = Discover._get_device_class(dev.protocol.discovery_data)("localhost")
    assert d.is_dimmer
    assert d.device_type == DeviceType.Dimmer


async def test_type_unknown():
    invalid_info = {"system": {"get_sysinfo": {"type": "nosuchtype"}}}
    with pytest.raises(SmartDeviceException):
        Discover._get_device_class(invalid_info)
