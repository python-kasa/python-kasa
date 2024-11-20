from kasa import Device, Module

from ...device_fixtures import device_iot


@device_iot
def test_cloud(dev: Device):
    cloud = dev.modules.get(Module.IotCloud)
    assert cloud
    info = cloud.info
    assert info
    assert isinstance(info.binded, int)
    assert cloud.is_connected == bool(info.binded)
