# type: ignore
import logging
from typing import Type

import pytest  # type: ignore # https://github.com/pytest-dev/pytest/issues/3342

from kasa import (
    Credentials,
    DeviceType,
    Discover,
    SmartBulb,
    SmartDevice,
    SmartDeviceException,
    SmartDimmer,
    SmartLightStrip,
    SmartPlug,
)
from kasa.device_factory import (
    DEVICE_TYPE_TO_CLASS,
    connect,
    get_protocol_from_connection_name,
)
from kasa.discover import DiscoveryResult
from kasa.iotprotocol import IotProtocol
from kasa.protocol import TPLinkProtocol, TPLinkSmartHomeProtocol


@pytest.mark.parametrize("custom_port", [123, None])
async def test_connect(discovery_data: dict, mocker, custom_port):
    """Make sure that connect returns an initialized SmartDevice instance."""
    host = "127.0.0.1"

    if "result" in discovery_data:
        with pytest.raises(SmartDeviceException):
            dev = await connect(host, port=custom_port)
    else:
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

    if "result" in discovery_data:
        with pytest.raises(SmartDeviceException):
            dev = await connect(host, port=custom_port)
    else:
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
    if "result" in discovery_data:
        with pytest.raises(SmartDeviceException):
            await connect(host)
    else:
        mocker.patch("kasa.TPLinkSmartHomeProtocol.query", return_value=discovery_data)
        logging.getLogger("kasa").setLevel(logging.DEBUG)
        await connect(host)
        assert "seconds to connect" in caplog.text


async def test_connect_pass_protocol(
    all_fixture_data: dict,
    mocker,
):
    """Test that if the protocol is passed in it's gets set correctly."""
    if "discovery_result" in all_fixture_data:
        discovery_info = {"result": all_fixture_data["discovery_result"]}
        device_class = Discover._get_device_class(discovery_info)
    else:
        device_class = Discover._get_device_class(all_fixture_data)

    device_type = list(DEVICE_TYPE_TO_CLASS.keys())[
        list(DEVICE_TYPE_TO_CLASS.values()).index(device_class)
    ]
    host = "127.0.0.1"
    if "discovery_result" in all_fixture_data:
        mocker.patch("kasa.IotProtocol.query", return_value=all_fixture_data)
        mocker.patch("kasa.SmartProtocol.query", return_value=all_fixture_data)

        dr = DiscoveryResult(**discovery_info["result"])
        connection_name = (
            dr.device_type.split(".")[0] + "." + dr.mgt_encrypt_schm.encrypt_type
        )
        protocol_class = get_protocol_from_connection_name(
            connection_name, host
        ).__class__
    else:
        mocker.patch(
            "kasa.TPLinkSmartHomeProtocol.query", return_value=all_fixture_data
        )
        protocol_class = TPLinkSmartHomeProtocol

    dev = await connect(
        host,
        device_type=device_type,
        protocol_class=protocol_class,
        credentials=Credentials("", ""),
    )
    assert isinstance(dev.protocol, protocol_class)
