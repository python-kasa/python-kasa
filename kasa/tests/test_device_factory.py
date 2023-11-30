# type: ignore
import logging
from typing import Type

import pytest  # type: ignore # https://github.com/pytest-dev/pytest/issues/3342

from kasa import (
    DeviceType,
    SmartBulb,
    SmartDevice,
    SmartDeviceException,
    SmartDimmer,
    SmartLightStrip,
    SmartPlug,
)
from kasa.device_factory import connect
from kasa.iotprotocol import TPLinkIotProtocol
from kasa.protocol import TPLinkProtocol, TPLinkSmartHomeProtocol


@pytest.mark.parametrize("custom_port", [123, None])
async def test_connect(discovery_data: dict, mocker, custom_port):
    """Make sure that connect returns an initialized SmartDevice instance."""
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
    """Make sure that connect with a passed device type."""
    host = "127.0.0.1"
    mocker.patch("kasa.TPLinkSmartHomeProtocol.query", return_value=discovery_data)

    dev = await connect(host, port=custom_port, device_type=device_type)
    assert isinstance(dev, klass)
    assert dev.port == custom_port or dev.port == 9999


async def test_connect_query_fails(discovery_data: dict, mocker):
    """Make sure that connect fails when query fails."""
    host = "127.0.0.1"
    mocker.patch("kasa.TPLinkSmartHomeProtocol.query", side_effect=SmartDeviceException)

    with pytest.raises(SmartDeviceException):
        await connect(host)


async def test_connect_logs_connect_time(
    discovery_data: dict, caplog: pytest.LogCaptureFixture, mocker
):
    """Test that the connect time is logged when debug logging is enabled."""
    host = "127.0.0.1"
    mocker.patch("kasa.TPLinkSmartHomeProtocol.query", return_value=discovery_data)
    logging.getLogger("kasa").setLevel(logging.DEBUG)
    await connect(host)
    assert "seconds to connect" in caplog.text


@pytest.mark.parametrize("device_type", [DeviceType.Plug, None])
@pytest.mark.parametrize(
    ("protocol_in", "protocol_result"),
    (
        (None, TPLinkSmartHomeProtocol),
        (TPLinkIotProtocol, TPLinkIotProtocol),
        (TPLinkSmartHomeProtocol, TPLinkSmartHomeProtocol),
    ),
)
async def test_connect_pass_protocol(
    discovery_data: dict,
    mocker,
    device_type: DeviceType,
    protocol_in: Type[TPLinkProtocol],
    protocol_result: Type[TPLinkProtocol],
):
    """Test that if the protocol is passed in it's gets set correctly."""
    host = "127.0.0.1"
    mocker.patch("kasa.TPLinkSmartHomeProtocol.query", return_value=discovery_data)
    mocker.patch("kasa.TPLinkIotProtocol.query", return_value=discovery_data)

    dev = await connect(host, device_type=device_type, protocol_class=protocol_in)
    assert isinstance(dev.protocol, protocol_result)
