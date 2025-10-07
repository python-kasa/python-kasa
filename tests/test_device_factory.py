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
    BaseProtocol,
    Credentials,
    Discover,
    IotProtocol,
    KasaException,
    SmartCamProtocol,
    SmartProtocol,
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
from kasa.transports import (
    AesTransport,
    BaseTransport,
    KlapTransport,
    KlapTransportV2,
    LinkieTransportV2,
    SslAesTransport,
    SslTransport,
    XorTransport,
)

from .conftest import DISCOVERY_MOCK_IP

# Device Factory tests are not relevant for real devices which run against
# a single device that has already been created via the factory.
pytestmark = [pytest.mark.requires_dummy]


def _get_connection_type_device_class(discovery_info):
    if "result" in discovery_info:
        device_class = Discover._get_device_class(discovery_info)
        dr = DiscoveryResult.from_dict(discovery_info["result"])

        connection_type = Discover._get_connection_parameters(dr)
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
    default_port = discovery_mock.default_port

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


# Aliases to make the test params more readable
CP = DeviceConnectionParameters
DF = DeviceFamily
ET = DeviceEncryptionType


@pytest.mark.parametrize(
    ("conn_params", "expected_protocol", "expected_transport"),
    [
        pytest.param(
            CP(DF.SmartIpCamera, ET.Aes, https=True),
            SmartCamProtocol,
            SslAesTransport,
            id="smartcam",
        ),
        pytest.param(
            CP(DF.SmartTapoHub, ET.Aes, https=True),
            SmartCamProtocol,
            SslAesTransport,
            id="smartcam-hub",
        ),
        pytest.param(
            CP(DF.SmartTapoDoorbell, ET.Aes, https=True),
            SmartCamProtocol,
            SslAesTransport,
            id="smartcam-doorbell",
        ),
        pytest.param(
            CP(DF.IotIpCamera, ET.Aes, https=True),
            IotProtocol,
            LinkieTransportV2,
            id="kasacam",
        ),
        pytest.param(
            CP(DF.SmartTapoRobovac, ET.Aes, https=True),
            SmartProtocol,
            SslTransport,
            id="robovac",
        ),
        pytest.param(
            CP(DF.IotSmartPlugSwitch, ET.Klap, https=False),
            IotProtocol,
            KlapTransport,
            id="iot-klap",
        ),
        pytest.param(
            CP(DF.IotSmartPlugSwitch, ET.Klap, https=False, new_klap=1),
            IotProtocol,
            KlapTransportV2,
            id="iot-new-klap",
        ),
        pytest.param(
            CP(DF.IotSmartPlugSwitch, ET.Xor, https=False),
            IotProtocol,
            XorTransport,
            id="iot-xor",
        ),
        pytest.param(
            CP(DF.SmartTapoPlug, ET.Aes, https=False),
            SmartProtocol,
            AesTransport,
            id="smart-aes",
        ),
        pytest.param(
            CP(DF.SmartTapoPlug, ET.Klap, https=False),
            SmartProtocol,
            KlapTransportV2,
            id="smart-klap",
        ),
        pytest.param(
            CP(DF.SmartTapoChime, ET.Klap, https=False),
            SmartProtocol,
            KlapTransportV2,
            id="smart-chime",
        ),
    ],
)
async def test_get_protocol(
    conn_params: DeviceConnectionParameters,
    expected_protocol: type[BaseProtocol],
    expected_transport: type[BaseTransport],
):
    """Test get_protocol returns the right protocol."""
    config = DeviceConfig("127.0.0.1", connection_type=conn_params)
    protocol = get_protocol(config)
    assert isinstance(protocol, expected_protocol)
    assert isinstance(protocol._transport, expected_transport)
