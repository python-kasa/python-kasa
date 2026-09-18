"""Module for testing device factory.

As this module tests the factory with discovery data and expects update to be
called on devices it uses the discovery_mock handles all the patching of the
query methods without actually replacing the device protocol class with one of
the testing fake protocols.
"""

import asyncio
import logging
from dataclasses import replace
from typing import cast
from unittest.mock import AsyncMock, MagicMock

import aiohttp
import pytest  # type: ignore # https://github.com/pytest-dev/pytest/issues/3342

from kasa import (
    BaseProtocol,
    Credentials,
    IotProtocol,
    KasaException,
    SmartCamProtocol,
    SmartProtocol,
)
from kasa.device_factory import (
    _CONNECTION_ROUTES,
    _DEVICE_FAMILIES,
    ConnectAttempt,
    Device,
    IotDevice,
    SmartCamDevice,
    SmartDevice,
    connect,
    create_device,
    get_device_class_from_family,
    get_device_class_from_sys_info,
    get_protocol,
    try_connect_all,
)
from kasa.deviceconfig import (
    DeviceConfig,
    DeviceConnectionParameters,
    DeviceEncryptionType,
    DeviceFamily,
)
from kasa.discover import DiscoveryResult
from kasa.iot import IotPlug, IotStrip
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
from .discovery_fixtures import get_device_class_from_discovery

# Device Factory tests are not relevant for real devices which run against
# a single device that has already been created via the factory.
pytestmark = [pytest.mark.requires_dummy]


def _get_connection_type_device_class(discovery_info, device_info):
    if "result" in discovery_info:
        device_type = discovery_info["result"]["device_type"]
        device_class = (
            get_device_class_from_sys_info(device_info)
            if device_type.startswith("IOT.")
            else get_device_class_from_discovery(discovery_info)
        )
        dr = DiscoveryResult.from_dict(discovery_info["result"])

        connection_type = dr.to_connection_parameters()
    else:
        connection_type = DeviceConnectionParameters.from_values(
            DeviceFamily.IotSmartPlugSwitch.value, DeviceEncryptionType.Xor.value
        )
        device_class = get_device_class_from_sys_info(device_info)

    return connection_type, device_class


async def test_connect(
    discovery_mock,
    mocker,
):
    """Test that if the protocol is passed in it gets set correctly."""
    host = DISCOVERY_MOCK_IP
    ctype, device_class = _get_connection_type_device_class(
        discovery_mock.discovery_data, discovery_mock.query_data
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

    if isinstance(dev, IotDevice):
        expected_family = (
            DeviceFamily.IotSmartBulb
            if dev.device_type in {Device.Type.Bulb, Device.Type.LightStrip}
            else DeviceFamily.IotSmartPlugSwitch
        )
        expected_config = replace(
            config,
            connection_type=replace(
                config.connection_type,
                device_family=expected_family,
            ),
        )
        assert dev.config == expected_config
    else:
        assert dev.config == config
    assert close_mock.call_count == 0
    await dev.disconnect()
    assert close_mock.call_count == 1


@pytest.mark.parametrize("custom_port", [123, None])
async def test_connect_custom_port(discovery_mock, mocker, custom_port):
    """Make sure that connect returns an initialized SmartDevice instance."""
    host = DISCOVERY_MOCK_IP

    discovery_data = discovery_mock.discovery_data
    ctype, _ = _get_connection_type_device_class(
        discovery_data, discovery_mock.query_data
    )
    config = DeviceConfig(
        host=host,
        port_override=custom_port,
        connection_type=ctype,
        credentials=Credentials("dummy_user", "dummy_password"),
    )
    default_port = discovery_mock.default_port

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
    ctype, _ = _get_connection_type_device_class(
        discovery_data, discovery_mock.query_data
    )

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

    ctype, _ = _get_connection_type_device_class(
        discovery_data, discovery_mock.query_data
    )
    config = DeviceConfig(
        host=host, credentials=Credentials("foor", "bar"), connection_type=ctype
    )
    protocol_class = get_protocol(config).__class__
    close_mock = mocker.patch.object(protocol_class, "close")
    assert close_mock.call_count == 0
    with pytest.raises(KasaException):
        await connect(config=config)
    assert close_mock.call_count == 1


async def test_create_device_closes_owned_protocol_on_cancellation(mocker):
    """Factory-owned protocols are closed when initialization is cancelled."""
    protocol = MagicMock(spec=BaseProtocol)
    protocol.close = AsyncMock()
    mocker.patch("kasa.device_factory.get_protocol", return_value=protocol)
    mocker.patch(
        "kasa.device_factory._resolve_device_class",
        side_effect=asyncio.CancelledError,
    )

    with pytest.raises(asyncio.CancelledError):
        await create_device(DeviceConfig("127.0.0.1"))

    protocol.close.assert_awaited_once()


async def test_try_connect_all_closes_protocol_when_success_callback_fails(mocker):
    """A callback failure cannot leak a successful attempt's protocol."""
    protocol = MagicMock(spec=BaseProtocol)
    protocol.close = AsyncMock()
    config = DeviceConfig("127.0.0.1")
    attempt = ConnectAttempt(
        IotProtocol,
        XorTransport,
        IotDevice,
        False,
        config.connection_type,
    )

    async def attempts(*args, **kwargs):
        yield attempt, protocol, config

    mocker.patch("kasa.device_factory._iter_connection_attempts", attempts)
    mocker.patch(
        "kasa.device_factory._connect", new=AsyncMock(return_value=MagicMock())
    )

    def on_attempt(*args):
        raise RuntimeError("callback failed")

    with pytest.raises(RuntimeError, match="callback failed"):
        await try_connect_all(config.host, on_attempt=on_attempt)

    protocol.close.assert_awaited_once()


async def test_try_connect_all_reports_resolved_device_class(mocker):
    """A successful attempt reports the concrete class resolved by the factory."""
    protocol = MagicMock(spec=BaseProtocol)
    protocol.close = AsyncMock()
    config = DeviceConfig("127.0.0.1")
    attempt = ConnectAttempt(
        IotProtocol,
        XorTransport,
        IotPlug,
        False,
        config.connection_type,
    )
    device = object.__new__(IotStrip)

    async def attempts(*args, **kwargs):
        yield attempt, protocol, config

    mocker.patch("kasa.device_factory._iter_connection_attempts", attempts)
    mocker.patch("kasa.device_factory._connect", new=AsyncMock(return_value=device))
    completed_attempts: list[ConnectAttempt] = []

    result = await try_connect_all(
        config.host,
        on_attempt=lambda completed, success: completed_attempts.append(completed),
    )

    assert result is device
    assert completed_attempts[0].device is IotStrip


async def test_try_connect_all_preserves_complete_connection_identity(mocker):
    """Distinct device families are not collapsed by implementation classes."""
    attempts: list[ConnectAttempt] = []
    mocker.patch(
        "kasa.device_factory._connect",
        new=AsyncMock(side_effect=KasaException("not this route")),
    )

    device = await try_connect_all(
        "127.0.0.1",
        on_attempt=lambda attempt, success: attempts.append(attempt),
    )

    assert device is None
    connection_types = [attempt.connection_type for attempt in attempts]
    families = {connection_type.device_family for connection_type in connection_types}
    assert DeviceFamily.SmartTapoPlug in families
    assert DeviceFamily.SmartTapoRobovac in families
    iot_klap_types = [
        connection_type
        for connection_type in connection_types
        if connection_type.device_family is DeviceFamily.IotSmartPlugSwitch
        and connection_type.encryption_type is DeviceEncryptionType.Klap
    ]
    assert {connection_type.klap_version for connection_type in iot_klap_types} == {
        None,
        1,
    }
    assert (
        next(
            connection_type
            for connection_type in iot_klap_types
            if connection_type.klap_version is None
        ).login_version
        is None
    )
    assert all(
        connection_type not in connection_types[:index]
        for index, connection_type in enumerate(connection_types)
    )


async def test_connect_http_client(discovery_mock, mocker):
    """Make sure that discover_single returns an initialized SmartDevice instance."""
    host = DISCOVERY_MOCK_IP
    discovery_data = discovery_mock.discovery_data
    ctype, _ = _get_connection_type_device_class(
        discovery_data, discovery_mock.query_data
    )

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


def test_all_supported_families_are_registered() -> None:
    """Every public supported family has one declarative factory definition."""
    assert set(_DEVICE_FAMILIES) == set(DeviceFamily)


def test_probeable_families_have_connection_routes() -> None:
    """Direct probing is derived from routes rather than a separate family list."""
    for family, definition in _DEVICE_FAMILIES.items():
        if not definition.probe:
            continue
        assert any(
            route.device_family is family
            or (
                route.device_family is None
                and route.protocol_type
                in {
                    definition.protocol_type,
                    definition.https_protocol_type,
                }
            )
            for route in _CONNECTION_ROUTES
        )


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
            CP(DF.SmartIpCamera, ET.Aes, https=False),
            SmartCamProtocol,
            SslAesTransport,
            id="smartcam-master-https-compatibility",
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
            CP(DF.SmartTapoDoorbell, ET.Aes, https=False),
            SmartCamProtocol,
            SslAesTransport,
            id="smartcam-doorbell-master-https-compatibility",
        ),
        pytest.param(
            CP(DF.IotIpCamera, ET.Aes, https=True),
            IotProtocol,
            LinkieTransportV2,
            id="kasacam",
        ),
        pytest.param(
            CP(DF.IotIpCamera, ET.Xor, https=False),
            IotProtocol,
            LinkieTransportV2,
            id="kasacam-master-https-compatibility",
        ),
        pytest.param(
            CP(DF.SmartTapoRobovac, ET.Aes, https=True),
            SmartProtocol,
            SslTransport,
            id="robovac",
        ),
        pytest.param(
            CP(DF.SmartTapoRobovac, ET.Aes, https=False),
            SmartProtocol,
            SslTransport,
            id="robovac-master-https-compatibility",
        ),
        pytest.param(
            CP(DF.SmartTapoHub, ET.Klap, https=True),
            SmartProtocol,
            KlapTransportV2,
            id="smart-hub-klap-https-master-compatibility",
        ),
        pytest.param(
            CP(DF.IotSmartPlugSwitch, ET.Klap, login_version=2, https=False),
            IotProtocol,
            KlapTransport,
            id="iot-klap-login-version-does-not-select-v2",
        ),
        pytest.param(
            CP(
                DF.IotSmartPlugSwitch,
                ET.Klap,
                login_version=2,
                https=False,
                klap_version=1,
            ),
            IotProtocol,
            KlapTransportV2,
            id="iot-klap-version-selects-v2",
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
            CP(DF.SmartTapoPlug, ET.Aes, https=True),
            SmartCamProtocol,
            SslAesTransport,
            id="smart-aes-https",
        ),
        pytest.param(
            CP(DF.SmartTapoPlug, ET.Klap, login_version=None, https=False),
            SmartProtocol,
            KlapTransportV2,
            id="smart-klap-does-not-require-login-version",
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


@pytest.mark.parametrize(
    "conn_params",
    [
        CP(DF.SmartIpCamera, ET.Klap, https=True),
        CP(DF.SmartTapoDoorbell, ET.Xor, https=False),
        CP(DF.IotIpCamera, ET.Klap, https=False),
    ],
)
def test_get_protocol_strict_rejects_fixed_encryption_mismatch(
    conn_params: DeviceConnectionParameters,
) -> None:
    """Strict direct parameters cannot fall through fixed family routes."""
    config = DeviceConfig("127.0.0.1", connection_type=conn_params)

    assert get_protocol(config, strict=True) is None
