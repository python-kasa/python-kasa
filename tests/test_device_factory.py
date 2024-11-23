"""Module for testing device factory.

As this module tests the factory with discovery data and expects update to be
called on devices it uses the discovery_mock handles all the patching of the
query methods without actually replacing the device protocol class with one of
the testing fake protocols.
"""

import logging
from typing import cast

import aiohttp
import pytest  # type: ignore # https://github.com/pytest-dev/pytest/issues/3342

from kasa import (
    Credentials,
    Discover,
    KasaException,
)
from kasa.device_factory import (
    Device,
    IotDevice,
    SmartCamDevice,
    SmartDevice,
    connect,
    get_device_class_from_family,
    get_protocol,
)
from kasa.deviceconfig import (
    DeviceConfig,
    DeviceConnectionParameters,
    DeviceEncryptionType,
    DeviceFamily,
)
from kasa.discover import DiscoveryResult

from .conftest import DISCOVERY_MOCK_IP

# Device Factory tests are not relevant for real devices which run against
# a single device that has already been created via the factory.
pytestmark = [pytest.mark.requires_dummy]


def _get_connection_type_device_class(discovery_info):
    if "result" in discovery_info:
        device_class = Discover._get_device_class(discovery_info)
        dr = DiscoveryResult.from_dict(discovery_info["result"])

        connection_type = DeviceConnectionParameters.from_values(
            dr.device_type, dr.mgt_encrypt_schm.encrypt_type
        )
    else:
        connection_type = DeviceConnectionParameters.from_values(
            DeviceFamily.IotSmartPlugSwitch.value, DeviceEncryptionType.Xor.value
        )
        device_class = Discover._get_device_class(discovery_info)

    return connection_type, device_class


async def test_connect(
    discovery_mock,
    mocker,
):
    """Test that if the protocol is passed in it gets set correctly."""
    host = DISCOVERY_MOCK_IP
    ctype, device_class = _get_connection_type_device_class(
        discovery_mock.discovery_data
    )

    config = DeviceConfig(
        host=host, credentials=Credentials("foor", "bar"), connection_type=ctype
    )
    protocol_class = get_protocol(config).__class__
    close_mock = mocker.patch.object(protocol_class, "close")
    # mocker.patch.object(SmartDevice, "update")
    # mocker.patch.object(Device, "update")
    dev = await connect(
        config=config,
    )
    assert isinstance(dev, device_class)
    assert isinstance(dev.protocol, protocol_class)

    assert dev.config == config
    assert close_mock.call_count == 0
    await dev.disconnect()
    assert close_mock.call_count == 1


@pytest.mark.parametrize("custom_port", [123, None])
async def test_connect_custom_port(discovery_mock, mocker, custom_port):
    """Make sure that connect returns an initialized SmartDevice instance."""
    host = DISCOVERY_MOCK_IP

    discovery_data = discovery_mock.discovery_data
    ctype, _ = _get_connection_type_device_class(discovery_data)
    config = DeviceConfig(
        host=host,
        port_override=custom_port,
        connection_type=ctype,
        credentials=Credentials("dummy_user", "dummy_password"),
    )
    default_port = 80 if "result" in discovery_data else 9999

    ctype, _ = _get_connection_type_device_class(discovery_data)

    dev = await connect(config=config)
    assert issubclass(dev.__class__, Device)
    assert dev.port == custom_port or dev.port == default_port


@pytest.mark.xdist_group(name="caplog")
async def test_connect_logs_connect_time(
    discovery_mock,
    caplog: pytest.LogCaptureFixture,
):
    """Test that the connect time is logged when debug logging is enabled."""
    discovery_data = discovery_mock.discovery_data
    ctype, _ = _get_connection_type_device_class(discovery_data)

    host = DISCOVERY_MOCK_IP
    config = DeviceConfig(
        host=host, credentials=Credentials("foor", "bar"), connection_type=ctype
    )
    logging.getLogger("kasa").setLevel(logging.DEBUG)
    await connect(
        config=config,
    )
    assert "seconds to update" in caplog.text


async def test_connect_query_fails(discovery_mock, mocker):
    """Make sure that connect fails when query fails."""
    host = DISCOVERY_MOCK_IP
    discovery_data = discovery_mock.discovery_data
    mocker.patch("kasa.IotProtocol.query", side_effect=KasaException)
    mocker.patch("kasa.SmartProtocol.query", side_effect=KasaException)

    ctype, _ = _get_connection_type_device_class(discovery_data)
    config = DeviceConfig(
        host=host, credentials=Credentials("foor", "bar"), connection_type=ctype
    )
    protocol_class = get_protocol(config).__class__
    close_mock = mocker.patch.object(protocol_class, "close")
    assert close_mock.call_count == 0
    with pytest.raises(KasaException):
        await connect(config=config)
    assert close_mock.call_count == 1


async def test_connect_http_client(discovery_mock, mocker):
    """Make sure that discover_single returns an initialized SmartDevice instance."""
    host = DISCOVERY_MOCK_IP
    discovery_data = discovery_mock.discovery_data
    ctype, _ = _get_connection_type_device_class(discovery_data)

    http_client = aiohttp.ClientSession()

    config = DeviceConfig(
        host=host, credentials=Credentials("foor", "bar"), connection_type=ctype
    )
    dev = await connect(config=config)
    if ctype.encryption_type != DeviceEncryptionType.Xor:
        assert dev.protocol._transport._http_client.client != http_client
    await dev.disconnect()

    config = DeviceConfig(
        host=host,
        credentials=Credentials("foor", "bar"),
        connection_type=ctype,
        http_client=http_client,
    )
    dev = await connect(config=config)
    if ctype.encryption_type != DeviceEncryptionType.Xor:
        assert dev.protocol._transport._http_client.client == http_client
    await dev.disconnect()
    await http_client.close()


async def test_device_types(dev: Device):
    await dev.update()
    if isinstance(dev, SmartCamDevice):
        res = SmartCamDevice._get_device_type_from_sysinfo(dev.sys_info)
    elif isinstance(dev, SmartDevice):
        assert dev._discovery_info
        device_type = cast(str, dev._discovery_info["device_type"])
        res = SmartDevice._get_device_type_from_components(
            list(dev._components.keys()), device_type
        )
    else:
        res = IotDevice._get_device_type_from_sys_info(dev._last_update)

    assert dev.device_type == res


@pytest.mark.xdist_group(name="caplog")
async def test_device_class_from_unknown_family(caplog):
    """Verify that unknown SMART devices yield a warning and fallback to SmartDevice."""
    dummy_name = "SMART.foo"
    with caplog.at_level(logging.DEBUG):
        assert get_device_class_from_family(dummy_name, https=False) == SmartDevice
    assert f"Unknown SMART device with {dummy_name}" in caplog.text
