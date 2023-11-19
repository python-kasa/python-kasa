# type: ignore
import re
import socket
import sys
from typing import Type

import pytest  # type: ignore # https://github.com/pytest-dev/pytest/issues/3342

from kasa import (
    DeviceType,
    Discover,
    SmartBulb,
    SmartDevice,
    SmartDeviceException,
    SmartDimmer,
    SmartLightStrip,
    SmartPlug,
    protocol,
)
from kasa.device_factory import DEVICE_TYPE_TO_CLASS, connect
from kasa.discover import _DiscoverProtocol, json_dumps
from kasa.exceptions import UnsupportedDeviceException

from .conftest import bulb, dimmer, lightstrip, plug, strip


@pytest.mark.parametrize("custom_port", [123, None])
async def test_connect(discovery_data: dict, mocker, custom_port):
    """Make sure that connect_single returns an initialized SmartDevice instance."""
    host = "127.0.0.1"
    mocker.patch("kasa.TPLinkSmartHomeProtocol.query", return_value=discovery_data)

    dev = await connect(host, port=custom_port)
    assert issubclass(dev.__class__, SmartDevice)
    assert dev.port == custom_port or dev.port == 9999


@pytest.mark.parametrize("custom_port", [123, None])
@pytest.mark.parametrize(
    ("device_type", "klass"),
    (
        (DeviceType.Plug, SmartPlug),
        (DeviceType.Bulb, SmartBulb),
        (DeviceType.Dimmer, SmartDimmer),
        (DeviceType.LightStrip, SmartLightStrip),
        (DeviceType.Unknown, SmartDevice),
    ),
)
async def test_connect_passed_device_type(
    discovery_data: dict,
    mocker,
    device_type: DeviceType,
    klass: Type[SmartDevice],
    custom_port,
):
    """Make sure that connect_single with a passed device type."""
    host = "127.0.0.1"
    mocker.patch("kasa.TPLinkSmartHomeProtocol.query", return_value=discovery_data)

    dev = await connect(host, port=custom_port, device_type=device_type)
    assert isinstance(dev, klass)
    assert dev.port == custom_port or dev.port == 9999


async def test_connect_query_fails(discovery_data: dict, mocker):
    """Make sure that connect_single fails when query fails."""
    host = "127.0.0.1"
    mocker.patch("kasa.TPLinkSmartHomeProtocol.query", side_effect=SmartDeviceException)

    with pytest.raises(SmartDeviceException):
        await connect(host)
