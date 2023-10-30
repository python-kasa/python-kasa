import pytest

from kasa import DeviceType, SmartCamera

from ..modules.ptz import Position
from ..smartdevice import SmartDeviceException
from .conftest import camera


@camera
async def test_camera_sysinfo(dev: SmartCamera):
    assert dev.sys_info is not None
    assert dev.model is not None
    assert dev.device_type == DeviceType.Camera
    assert dev.is_camera


@camera
async def test_go_to_xy(dev: SmartCamera, mocker):
    query = mocker.spy(dev.protocol, "query")
    await dev.go_to(x=0, y=99)
    query.assert_called_with(
        {"smartlife.cam.ipcamera.ptz": {"set_move": {"x": 0, "y": 99}}}
    )


@camera
async def test_go_to_position(dev: SmartCamera, mocker):
    query = mocker.spy(dev.protocol, "query")
    position = Position(x=0, y=99)
    await dev.go_to(position)
    query.assert_called_with(
        {"smartlife.cam.ipcamera.ptz": {"set_move": {"x": 0, "y": 99}}}
    )


@camera
async def test_go_to_needs_both_coords(dev: SmartCamera, mocker):
    with pytest.raises(SmartDeviceException):
        await dev.go_to(x=5)


@camera
async def test_is_patrol_enabled_property(dev: SmartCamera, mocker):
    await dev.set_enable_patrol(True)
    await dev.update()
    assert dev.is_patrol_enabled
    await dev.set_enable_patrol(False)
    await dev.update()
    assert not dev.is_patrol_enabled


@camera
async def test_enable_patrolling(dev: SmartCamera, mocker):
    query = mocker.spy(dev.protocol, "query")
    await dev.set_enable_patrol(True)
    query.assert_called_with(
        {"smartlife.cam.ipcamera.ptz": {"set_patrol_is_enable": {"value": "on"}}}
    )


@camera
async def test_disable_patrolling(dev: SmartCamera, mocker):
    query = mocker.spy(dev.protocol, "query")
    await dev.set_enable_patrol(False)
    query.assert_called_with(
        {"smartlife.cam.ipcamera.ptz": {"set_patrol_is_enable": {"value": "off"}}}
    )


@camera
async def test_move(dev: SmartCamera, mocker):
    query = mocker.spy(dev.protocol, "query")
    await dev.move("up", 5)
    query.assert_called_with(
        {"smartlife.cam.ipcamera.ptz": {"set_target": {"direction": "up", "speed": 5}}}
    )


@camera
async def test_stop(dev: SmartCamera, mocker):
    query = mocker.spy(dev.protocol, "query")
    await dev.stop()
    query.assert_called_with({"smartlife.cam.ipcamera.ptz": {"set_stop": {}}})
