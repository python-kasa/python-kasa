# type: ignore
import logging
from typing import Type

import aiohttp
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
from kasa.device_factory import connect, get_protocol
from kasa.deviceconfig import (
    ConnectionType,
    DeviceConfig,
    DeviceFamilyType,
    EncryptType,
)
from kasa.discover import DiscoveryResult


def _get_connection_type_device_class(the_fixture_data):
    if "discovery_result" in the_fixture_data:
        discovery_info = {"result": the_fixture_data["discovery_result"]}
        device_class = Discover._get_device_class(discovery_info)
        dr = DiscoveryResult(**discovery_info["result"])

        connection_type = ConnectionType.from_values(
            dr.device_type, dr.mgt_encrypt_schm.encrypt_type
        )
    else:
        connection_type = ConnectionType.from_values(
            DeviceFamilyType.IotSmartPlugSwitch.value, EncryptType.Xor.value
        )
        device_class = Discover._get_device_class(the_fixture_data)

    return connection_type, device_class


async def test_connect(
    all_fixture_data: dict,
    mocker,
):
    """Test that if the protocol is passed in it gets set correctly."""
    host = "127.0.0.1"
    ctype, device_class = _get_connection_type_device_class(all_fixture_data)

    mocker.patch("kasa.IotProtocol.query", return_value=all_fixture_data)
    mocker.patch("kasa.SmartProtocol.query", return_value=all_fixture_data)
    mocker.patch("kasa.TPLinkSmartHomeProtocol.query", return_value=all_fixture_data)

    config = DeviceConfig(
        host=host, credentials=Credentials("foor", "bar"), connection_type=ctype
    )
    protocol_class = get_protocol(config).__class__

    dev = await connect(
        config=config,
    )
    assert isinstance(dev, device_class)
    assert isinstance(dev.protocol, protocol_class)

    assert dev.config == config


@pytest.mark.parametrize("custom_port", [123, None])
async def test_connect_custom_port(all_fixture_data: dict, mocker, custom_port):
    """Make sure that connect returns an initialized SmartDevice instance."""
    host = "127.0.0.1"

    ctype, _ = _get_connection_type_device_class(all_fixture_data)
    config = DeviceConfig(
        host=host,
        port_override=custom_port,
        connection_type=ctype,
        credentials=Credentials("dummy_user", "dummy_password"),
    )
    default_port = 80 if "discovery_result" in all_fixture_data else 9999

    ctype, _ = _get_connection_type_device_class(all_fixture_data)
    mocker.patch("kasa.TPLinkSmartHomeProtocol.query", return_value=all_fixture_data)
    mocker.patch("kasa.IotProtocol.query", return_value=all_fixture_data)
    mocker.patch("kasa.SmartProtocol.query", return_value=all_fixture_data)
    dev = await connect(config=config)
    assert issubclass(dev.__class__, SmartDevice)
    assert dev.port == custom_port or dev.port == default_port


async def test_connect_logs_connect_time(
    all_fixture_data: dict, caplog: pytest.LogCaptureFixture, mocker
):
    """Test that the connect time is logged when debug logging is enabled."""
    ctype, _ = _get_connection_type_device_class(all_fixture_data)
    mocker.patch("kasa.IotProtocol.query", return_value=all_fixture_data)
    mocker.patch("kasa.SmartProtocol.query", return_value=all_fixture_data)
    mocker.patch("kasa.TPLinkSmartHomeProtocol.query", return_value=all_fixture_data)

    host = "127.0.0.1"
    config = DeviceConfig(
        host=host, credentials=Credentials("foor", "bar"), connection_type=ctype
    )
    logging.getLogger("kasa").setLevel(logging.DEBUG)
    await connect(
        config=config,
    )
    assert "seconds to update" in caplog.text


async def test_connect_query_fails(all_fixture_data: dict, mocker):
    """Make sure that connect fails when query fails."""
    host = "127.0.0.1"
    mocker.patch("kasa.TPLinkSmartHomeProtocol.query", side_effect=SmartDeviceException)
    mocker.patch("kasa.IotProtocol.query", side_effect=SmartDeviceException)
    mocker.patch("kasa.SmartProtocol.query", side_effect=SmartDeviceException)

    ctype, _ = _get_connection_type_device_class(all_fixture_data)
    config = DeviceConfig(
        host=host, credentials=Credentials("foor", "bar"), connection_type=ctype
    )
    with pytest.raises(SmartDeviceException):
        await connect(config=config)


async def test_connect_http_client(all_fixture_data, mocker):
    """Make sure that discover_single returns an initialized SmartDevice instance."""
    host = "127.0.0.1"

    ctype, _ = _get_connection_type_device_class(all_fixture_data)

    mocker.patch("kasa.IotProtocol.query", return_value=all_fixture_data)
    mocker.patch("kasa.SmartProtocol.query", return_value=all_fixture_data)
    mocker.patch("kasa.TPLinkSmartHomeProtocol.query", return_value=all_fixture_data)

    http_client = aiohttp.ClientSession()

    config = DeviceConfig(
        host=host, credentials=Credentials("foor", "bar"), connection_type=ctype
    )
    dev = await connect(config=config)
    if ctype.encryption_type != EncryptType.Xor:
        assert dev.protocol._transport._http_client.client != http_client

    config = DeviceConfig(
        host=host,
        credentials=Credentials("foor", "bar"),
        connection_type=ctype,
        http_client=http_client,
    )
    dev = await connect(config=config)
    if ctype.encryption_type != EncryptType.Xor:
        assert dev.protocol._transport._http_client.client == http_client
