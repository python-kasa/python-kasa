# type: ignore
# ruff: noqa: S106

import asyncio
import base64
import json
import logging
import re
import socket
from asyncio import timeout as asyncio_timeout
from unittest.mock import AsyncMock, MagicMock

import aiohttp
import pytest  # type: ignore # https://github.com/pytest-dev/pytest/issues/3342
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import padding as asymmetric_padding

from kasa import (
    Credentials,
    Device,
    DeviceType,
    Discover,
    IotProtocol,
    KasaException,
)
from kasa.device_factory import get_device_class_from_sys_info, get_protocol
from kasa.deviceconfig import (
    DeviceConfig,
    DeviceConnectionParameters,
    DeviceFamily,
)
from kasa.discover import (
    DiscoveryResult,
    _AesDiscoveryQuery,
    _DiscoverProtocol,
    _DiscoverySource,
    _TdpDiscovery,
    _UdpDiscovery,
    json_dumps,
    select_discovery_response,
)
from kasa.exceptions import (
    AuthenticationError,
    DiscoveryAuthenticationError,
    UnsupportedAuthenticationError,
    UnsupportedDeviceError,
)
from kasa.iot import IotDevice, IotStrip
from kasa.transports.aestransport import AesEncyptionSession
from kasa.transports.xortransport import XorEncryption, XorTransport

from .conftest import (
    bulb_iot,
    dimmer_iot,
    lightstrip_iot,
    new_discovery,
    plug_iot,
    strip_iot,
    wallswitch_iot,
)
from .discovery_fixtures import get_device_class_from_discovery

# A physical device has to respond to discovery for the tests to work.
pytestmark = [pytest.mark.requires_dummy]

UNSUPPORTED = {
    "result": {
        "device_id": "xx",
        "owner": "xx",
        "device_type": "SMART.TAPOXMASTREE",
        "device_model": "P110(EU)",
        "ip": "127.0.0.1",
        "mac": "48-22xxx",
        "is_support_iot_cloud": True,
        "obd_src": "tplink",
        "factory_default": False,
        "mgt_encrypt_schm": {
            "is_support_https": False,
            "encrypt_type": "AES",
            "http_port": 80,
            "lv": 2,
        },
    },
    "error_code": 0,
}


@pytest.mark.parametrize(
    ("device_type", "encrypt_type", "new_klap", "expected_klap_version"),
    [
        pytest.param("IOT.SMARTPLUGSWITCH", "KLAP", 1, 1, id="iot-versioned"),
        pytest.param("IOT.SMARTPLUGSWITCH", "KLAP", 0, None, id="iot-original"),
        pytest.param("IOT.SMARTPLUGSWITCH", "AES", 1, None, id="iot-non-klap"),
        pytest.param("SMART.TAPOPLUG", "KLAP", 1, None, id="smart-klap"),
    ],
)
def test_tdp_klap_version_normalization(
    device_type, encrypt_type, new_klap, expected_klap_version
) -> None:
    """Only a positive IOT KLAP new_klap value selects the handshake variant."""
    result = DiscoveryResult.from_dict(
        {
            "device_type": device_type,
            "device_model": "MODEL(US)",
            "device_id": "device-id",
            "ip": "127.0.0.1",
            "mac": "00-00-00-00-00-00",
            "mgt_encrypt_schm": {
                "is_support_https": False,
                "encrypt_type": encrypt_type,
                "new_klap": new_klap,
            },
        }
    )

    assert result.to_connection_parameters().klap_version == expected_klap_version


@wallswitch_iot
async def test_type_detection_switch(dev: Device):
    d = get_device_class_from_discovery(dev._last_update)("localhost")
    with pytest.deprecated_call(match="use device_type property instead"):
        assert d.is_wallswitch
    assert d.device_type is DeviceType.WallSwitch


@plug_iot
async def test_type_detection_plug(dev: Device):
    d = get_device_class_from_discovery(dev._last_update)("localhost")
    assert d.device_type == DeviceType.Plug


@bulb_iot
async def test_type_detection_bulb(dev: Device):
    d = get_device_class_from_discovery(dev._last_update)("localhost")
    # TODO: light_strip is a special case for now to force bulb tests on it

    if d.device_type is not DeviceType.LightStrip:
        assert d.device_type == DeviceType.Bulb


@strip_iot
async def test_type_detection_strip(dev: Device):
    d = get_device_class_from_discovery(dev._last_update)("localhost")
    assert d.device_type == DeviceType.Strip


@dimmer_iot
async def test_type_detection_dimmer(dev: Device):
    d = get_device_class_from_discovery(dev._last_update)("localhost")
    assert d.device_type == DeviceType.Dimmer


@lightstrip_iot
async def test_type_detection_lightstrip(dev: Device):
    d = get_device_class_from_discovery(dev._last_update)("localhost")
    assert d.device_type == DeviceType.LightStrip


@pytest.mark.xdist_group(name="caplog")
async def test_type_unknown(caplog):
    invalid_info = {"system": {"get_sysinfo": {"type": "nosuchtype"}}}
    with pytest.raises(UnsupportedDeviceError) as exc_info:
        get_device_class_from_discovery(invalid_info)
    assert exc_info.value.discovery_result == invalid_info
    msg = "Unknown IOT device type nosuchtype"
    assert msg in caplog.text


def test_iot_camera_class_is_explicitly_unsupported() -> None:
    """Recognized IOT cameras do not escape class resolution as a KeyError."""
    camera_info = {"system": {"get_sysinfo": {"system": {"model": "NC200"}}}}

    with pytest.raises(UnsupportedDeviceError, match="camera") as exc_info:
        get_device_class_from_discovery(camera_info)

    assert exc_info.value.discovery_result == camera_info


@pytest.mark.parametrize("custom_port", [123, None])
async def test_discover_single(discovery_mock, custom_port, mocker):
    """Make sure that discover_single returns an initialized SmartDevice instance."""
    host = "127.0.0.1"
    discovery_mock.ip = host
    discovery_mock.port_override = custom_port

    disco_data = discovery_mock.discovery_data
    device_class = get_device_class_from_discovery(disco_data)
    http_port = (
        DiscoveryResult.from_dict(disco_data["result"]).mgt_encrypt_schm.http_port
        if "result" in disco_data
        else None
    )

    # discovery_mock patches protocol query methods so use spy here.
    update_mock = mocker.spy(device_class, "update")

    x = await Discover.discover_single(
        host, port=custom_port, credentials=Credentials()
    )
    assert issubclass(x.__class__, Device)
    assert x._discovery_info is not None
    assert (
        x.port == custom_port
        or x.port == discovery_mock.default_port
        or x.port == http_port
    )
    # Make sure discovery does not call update()
    assert update_mock.call_count == 0
    if discovery_mock.default_port != 9999:
        if isinstance(x, IotDevice):
            assert (
                x.alias == discovery_mock.query_data["system"]["get_sysinfo"]["alias"]
            )
        else:
            assert x.alias is None

    ct = DeviceConnectionParameters.from_values(
        discovery_mock.device_type,
        discovery_mock.encrypt_type,
        login_version=discovery_mock.login_version,
        klap_version=discovery_mock.klap_version,
        https=discovery_mock.https,
        http_port=discovery_mock.http_port,
    )
    config = DeviceConfig(
        host=host,
        port_override=custom_port,
        connection_type=ct,
        credentials=Credentials(),
    )
    assert x.config == config


async def test_discover_single_hostname(discovery_mock, mocker):
    """Make sure that discover_single returns an initialized SmartDevice instance."""
    host = "foobar"
    ip = "127.0.0.1"

    discovery_mock.ip = ip
    device_class = get_device_class_from_discovery(
        discovery_mock.discovery_data, discovery_mock.query_data
    )
    update_mock = mocker.patch.object(device_class, "update")

    x = await Discover.discover_single(host, credentials=Credentials())
    assert issubclass(x.__class__, Device)
    assert x._discovery_info is not None
    assert x.host == host
    assert update_mock.call_count == 0

    mocker.patch("socket.getaddrinfo", side_effect=socket.gaierror())
    with pytest.raises(KasaException):
        x = await Discover.discover_single(host, credentials=Credentials())


async def test_discover_credentials(mocker):
    """Make sure that discover gives credentials precedence over un and pw."""
    host = "127.0.0.1"

    async def mock_discover(self, *_, **__):
        self.discovered_devices = {host: MagicMock()}

    mocker.patch.object(_DiscoverProtocol, "do_discover", new=mock_discover)
    dp = mocker.spy(_DiscoverProtocol, "__init__")

    # Only credentials passed
    await Discover.discover(credentials=Credentials(), timeout=0)
    assert dp.mock_calls[0].kwargs["credentials"] == Credentials()
    # Credentials and un/pw passed
    await Discover.discover(
        credentials=Credentials(), username="Foo", password="Bar", timeout=0
    )
    assert dp.mock_calls[1].kwargs["credentials"] == Credentials()
    # Only un/pw passed
    await Discover.discover(username="Foo", password="Bar", timeout=0)
    assert dp.mock_calls[2].kwargs["credentials"] == Credentials("Foo", "Bar")
    # Only un passed, credentials should be None
    await Discover.discover(username="Foo", timeout=0)
    assert dp.mock_calls[3].kwargs["credentials"] is None
    # A credential hash is passed independently to the discovery protocol
    await Discover.discover(credentials_hash="credential-hash", timeout=0)
    assert dp.mock_calls[4].kwargs["credentials_hash"] == "credential-hash"


async def test_discover_single_credentials(mocker):
    """Make sure that discover_single gives credentials precedence over un and pw."""
    host = "127.0.0.1"

    async def mock_discover(self, *_, **__):
        self.discovered_devices = {host: MagicMock()}

    mocker.patch.object(_DiscoverProtocol, "do_discover", new=mock_discover)
    dp = mocker.spy(_DiscoverProtocol, "__init__")

    # Only credentials passed
    await Discover.discover_single(host, credentials=Credentials(), timeout=0)
    assert dp.mock_calls[0].kwargs["credentials"] == Credentials()
    # Credentials and un/pw passed
    await Discover.discover_single(
        host, credentials=Credentials(), username="Foo", password="Bar", timeout=0
    )
    assert dp.mock_calls[1].kwargs["credentials"] == Credentials()
    # Only un/pw passed
    await Discover.discover_single(host, username="Foo", password="Bar", timeout=0)
    assert dp.mock_calls[2].kwargs["credentials"] == Credentials("Foo", "Bar")
    # Only un passed, credentials should be None
    await Discover.discover_single(host, username="Foo", timeout=0)
    assert dp.mock_calls[3].kwargs["credentials"] is None
    # A credential hash is passed independently to the discovery protocol
    await Discover.discover_single(host, credentials_hash="credential-hash", timeout=0)
    assert dp.mock_calls[4].kwargs["credentials_hash"] == "credential-hash"


async def test_discover_single_unsupported(unsupported_device_info, mocker):
    """Make sure that discover_single handles unsupported devices correctly."""
    host = "127.0.0.1"

    # Test with a valid unsupported response
    with pytest.raises(
        UnsupportedDeviceError,
    ):
        await Discover.discover_single(host)


async def test_discover_single_no_response(mocker):
    """Make sure that discover_single handles no response correctly."""
    host = "127.0.0.1"
    mocker.patch.object(_DiscoverProtocol, "do_discover")
    with pytest.raises(
        KasaException, match=f"Timed out getting discovery response for {host}"
    ):
        await Discover.discover_single(host, discovery_timeout=0)


async def test_discover_single_construction_authentication_callback(mocker):
    """Targeted construction authentication can be consumed by a callback."""
    host = "127.0.0.1"
    mocker.patch(
        "kasa.protocols.iotprotocol.IotProtocol.query",
        new=AsyncMock(side_effect=AuthenticationError("Authentication failed")),
    )

    async def mock_discover(self):
        self.datagram_received(
            _tdp_datagram(AUTHENTICATION_DATA_KLAP),
            (host, 20002),
        )

    mocker.patch.object(_DiscoverProtocol, "do_discover", mock_discover)
    on_authentication_error = AsyncMock()

    device = await Discover.discover_single(
        host,
        on_authentication_error=on_authentication_error,
    )

    assert device is None
    error = on_authentication_error.await_args.args[0]
    assert isinstance(error, DiscoveryAuthenticationError)
    assert error.host == host


INVALIDS = [
    ("No 'system' or 'get_sysinfo' in response", {"no": "data"}),
    (
        "Unable to find the device type field",
        {"system": {"get_sysinfo": {"missing_type": 1}}},
    ),
]


@pytest.mark.parametrize(("msg", "data"), INVALIDS)
async def test_discover_invalid_info(msg, data, mocker):
    """Make sure that invalid discovery information raises an exception."""
    host = "127.0.0.1"

    async def mock_discover(self):
        self.datagram_received(
            XorEncryption.encrypt(json_dumps(data))[4:], (host, 9999)
        )

    mocker.patch.object(_DiscoverProtocol, "do_discover", mock_discover)

    with pytest.raises(KasaException, match=msg):
        await Discover.discover_single(host)


async def test_discover_send(mocker):
    """Test discovery parameters."""
    discovery_timeout = 0
    discovery_ports = 3
    proto = _DiscoverProtocol(discovery_timeout=discovery_timeout)
    assert proto.discovery_packets == 3
    assert [
        (discovery.source, discovery.port, discovery.defer_processing)
        for discovery in proto._discoveries
    ] == [
        (_DiscoverySource.Udp, 9999, True),
        (_DiscoverySource.Tdp, 20002, False),
        (_DiscoverySource.Tdp, 20004, False),
    ]
    tdp_discoveries = [
        discovery
        for discovery in proto._discoveries
        if discovery.source is _DiscoverySource.Tdp
    ]
    assert tdp_discoveries[0]._query is not tdp_discoveries[1]._query
    assert tdp_discoveries[0]._query.keypair is not tdp_discoveries[1]._query.keypair
    transport = mocker.patch.object(proto, "transport")
    await proto.do_discover()
    assert transport.sendto.call_count == proto.discovery_packets * discovery_ports


async def test_discover_datagram_received(mocker, discovery_data):
    """Verify that datagram received fills discovered_devices."""
    proto = _DiscoverProtocol()

    mocker.patch.object(_TdpDiscovery, "decrypt_discovery_data")

    addr = "127.0.0.1"
    port = 20002 if "result" in discovery_data else 9999
    datagram = (
        _tdp_datagram(discovery_data)
        if port == 20002
        else XorEncryption.encrypt(json_dumps(discovery_data))[4:]
    )

    proto.datagram_received(datagram, (addr, port))

    addr2 = "127.0.0.2"
    proto.datagram_received(_tdp_datagram(UNSUPPORTED), (addr2, 20002))
    await proto._finalize_discovery()

    # Check that device in discovered_devices is initialized correctly
    assert len(proto.discovered_devices) == 1
    # Check that unsupported device is 1
    assert len(proto.unsupported_device_exceptions) == 1
    dev = proto.discovered_devices[addr]
    assert issubclass(dev.__class__, Device)
    assert dev.host == addr


@pytest.mark.parametrize(("msg", "data"), INVALIDS)
async def test_discover_invalid_responses(msg, data, mocker):
    """Verify that we don't crash whole discovery if some devices in the network are sending unexpected data."""
    proto = _DiscoverProtocol()
    mocker.patch("kasa.discover.json_loads", return_value=data)
    mocker.patch.object(XorEncryption, "encrypt")
    mocker.patch.object(XorEncryption, "decrypt")

    proto.datagram_received(data, ("127.0.0.1", 9999))
    assert len(proto.discovered_devices) == 0


AUTHENTICATION_DATA_KLAP = {
    "result": {
        "device_id": "xx",
        "owner": "xx",
        "device_type": "IOT.SMARTPLUGSWITCH",
        "device_model": "HS100(UK)",
        "ip": "127.0.0.1",
        "mac": "12-34-56-78-90-AB",
        "is_support_iot_cloud": True,
        "obd_src": "tplink",
        "factory_default": False,
        "mgt_encrypt_schm": {
            "is_support_https": False,
            "encrypt_type": "KLAP",
            "http_port": 80,
        },
    },
    "error_code": 0,
}

TDP_DISCOVER_DATA = {
    "result": {
        "device_id": "tdp-device-id",
        "owner": "owner",
        "device_type": "SMART.TAPOPLUG",
        "device_model": "P100(US)",
        "ip": "127.0.0.1",
        "mac": "12-34-56-78-90-AB",
        "factory_default": False,
        "mgt_encrypt_schm": {
            "is_support_https": False,
            "encrypt_type": "AES",
            "http_port": 80,
            "lv": 2,
        },
    },
    "error_code": 0,
}


@new_discovery
async def test_discover_single_authentication(discovery_mock, mocker):
    """Make sure that discover_single handles authenticating devices correctly."""
    host = "127.0.0.1"
    discovery_mock.ip = host
    device_class = get_device_class_from_discovery(
        discovery_mock.discovery_data, discovery_mock.query_data
    )
    mocker.patch.object(
        device_class,
        "update",
        side_effect=AuthenticationError("Failed to authenticate"),
    )

    with pytest.raises(  # noqa: PT012
        AuthenticationError,
        match="Failed to authenticate",
    ):
        device = await Discover.discover_single(
            host, credentials=Credentials("foo", "bar")
        )
        await device.update()

    mocker.patch.object(device_class, "update")
    device = await Discover.discover_single(host, credentials=Credentials("foo", "bar"))
    await device.update()
    assert isinstance(device, device_class)


@new_discovery
async def test_device_update_from_new_discovery_info(discovery_mock):
    """Make sure that new discovery devices update from discovery info correctly."""
    discovery_data = discovery_mock.discovery_data
    device_class = get_device_class_from_discovery(discovery_data)
    device = device_class("127.0.0.1")
    discover_info = DiscoveryResult.from_dict(discovery_data["result"])

    device.update_from_discover_info(discovery_data["result"])

    assert device.mac == discover_info.mac.replace("-", ":")
    no_region_model, _, _ = discover_info.device_model.partition("(")
    assert device.model == no_region_model

    # TODO implement requires_update for SmartDevice
    if isinstance(device, IotDevice):
        with pytest.raises(
            KasaException,
            match=re.escape("You need to await update() to access the data"),
        ):
            assert device.modules


async def test_discover_single_http_client(discovery_mock, mocker):
    """Make sure that discover_single returns an initialized SmartDevice instance."""
    host = "127.0.0.1"
    discovery_mock.ip = host

    http_client = aiohttp.ClientSession()

    x: Device = await Discover.discover_single(host)

    assert x.config.uses_http == (discovery_mock.default_port != 9999)

    if discovery_mock.default_port != 9999:
        assert x.protocol._transport._http_client.client != http_client
        x.config.http_client = http_client
        assert x.protocol._transport._http_client.client == http_client


async def test_discover_http_client(discovery_mock, mocker):
    """Make sure that discover returns an initialized SmartDevice instance."""
    host = "127.0.0.1"
    discovery_mock.ip = host

    http_client = aiohttp.ClientSession()

    devices = await Discover.discover(discovery_timeout=0)
    x: Device = devices[host]
    assert x.config.uses_http == (discovery_mock.default_port != 9999)

    if discovery_mock.default_port != 9999:
        assert x.protocol._transport._http_client.client != http_client
        x.config.http_client = http_client
        assert x.protocol._transport._http_client.client == http_client


UDP_DISCOVER_DATA = {
    "system": {
        "get_sysinfo": {
            "alias": "#MASKED_NAME#",
            "dev_name": "Smart Wi-Fi Plug",
            "deviceId": "0000000000000000000000000000000000000000",
            "err_code": 0,
            "hwId": "00000000000000000000000000000000",
            "hw_ver": "0.0",
            "mac": "00:00:00:00:00:00",
            "mic_type": "IOT.SMARTPLUGSWITCH",
            "model": "HS100(UK)",
            "sw_ver": "1.1.0 Build 201016 Rel.175121",
            "updating": 0,
        }
    }
}


def _tdp_datagram(info: dict) -> bytes:
    return (
        b"\x02\x00\x00\x01\x01[\x00\x00\x00\x00\x00\x00W\xcev\xf8"
        + json_dumps(info).encode()
    )


@pytest.mark.parametrize(
    "ports",
    [
        (9999, 20002),
        (20002, 9999),
        (9999, 20004),
        (20004, 9999),
    ],
)
async def test_tdp_discovery_takes_precedence(ports):
    """A TDP response is authoritative regardless of response order or port."""
    host = "127.0.0.1"
    raw_responses = []
    on_discovered = AsyncMock()
    proto = _DiscoverProtocol(
        on_discovered=on_discovered,
        on_discovered_raw=raw_responses.append,
    )
    datagrams = {
        9999: XorEncryption.encrypt(json_dumps(UDP_DISCOVER_DATA))[4:],
        20002: _tdp_datagram(TDP_DISCOVER_DATA),
        20004: _tdp_datagram(TDP_DISCOVER_DATA),
    }

    for port in ports:
        proto.datagram_received(datagrams[port], (host, port))
    await proto._finalize_discovery()
    await asyncio.gather(*proto.callback_tasks)

    device = proto.discovered_devices[host]
    assert device.config.connection_type.device_family is DeviceFamily.SmartTapoPlug
    assert [response["meta"]["source"] for response in raw_responses] == [
        _DiscoverySource.Tdp.value
    ]
    on_discovered.assert_called_once_with(device)


async def test_invalid_udp_response_does_not_hide_tdp() -> None:
    """An invalid UDP response does not prevent a valid TDP result from winning."""
    host = "127.0.0.1"
    proto = _DiscoverProtocol()
    invalid_udp = XorEncryption.encrypt(json_dumps({"invalid": "response"}))[4:]

    proto.datagram_received(invalid_udp, (host, 9999))
    proto.datagram_received(_tdp_datagram(TDP_DISCOVER_DATA), (host, 20002))
    await proto._finalize_discovery()

    assert host in proto.discovered_devices
    assert host not in proto.invalid_device_exceptions


async def test_authoritative_unsupported_tdp_does_not_fall_back_to_udp() -> None:
    """A decoded unsupported TDP response remains authoritative over UDP."""
    host = "127.0.0.1"
    proto = _DiscoverProtocol()
    udp_datagram = XorEncryption.encrypt(json_dumps(UDP_DISCOVER_DATA))[4:]

    proto.datagram_received(udp_datagram, (host, 9999))
    proto.datagram_received(_tdp_datagram(UNSUPPORTED), (host, 20002))
    await proto._finalize_discovery()

    assert host in proto.unsupported_device_exceptions
    assert host not in proto.discovered_devices


async def test_undecodable_tdp_discards_udp() -> None:
    """Any TDP datagram suppresses UDP even when TDP decoding fails."""
    host = "127.0.0.1"
    proto = _DiscoverProtocol(target=host)
    udp_datagram = XorEncryption.encrypt(json_dumps(UDP_DISCOVER_DATA))[4:]

    proto.datagram_received(udp_datagram, (host, 9999))
    proto.datagram_received(b"invalid tdp", (host, 20002))
    await proto._wait_for_processing()
    proto.datagram_received(udp_datagram, (host, 9999))

    assert host not in proto.discovered_devices
    assert host not in proto.invalid_device_exceptions
    assert not proto._hosts[host].endpoints[9999].deferred_datagrams
    assert not proto._target_complete.is_set()

    await proto._finalize_discovery()

    assert host in proto.invalid_device_exceptions
    assert not proto._hosts[host].endpoints[9999].deferred_datagrams
    assert proto._target_complete.is_set()


async def test_non_device_tdp_json_discards_udp() -> None:
    """Decoded non-device TDP JSON remains authoritative over UDP."""
    host = "127.0.0.1"
    proto = _DiscoverProtocol()
    udp_datagram = XorEncryption.encrypt(json_dumps(UDP_DISCOVER_DATA))[4:]

    proto.datagram_received(udp_datagram, (host, 9999))
    proto.datagram_received(_tdp_datagram({"not": "a device"}), (host, 20002))
    await proto._wait_for_processing()

    assert host not in proto.discovered_devices
    assert host not in proto.invalid_device_exceptions
    await proto._finalize_discovery()
    assert host in proto.invalid_device_exceptions
    assert not proto._hosts[host].endpoints[9999].deferred_datagrams


async def test_unusable_endpoint_emits_first_decoded_diagnostic() -> None:
    """Raw discovery retains a decoded diagnostic when no response is usable."""
    host = "127.0.0.1"
    response = {"not": "a device"}
    raw_responses = []
    proto = _DiscoverProtocol(on_discovered_raw=raw_responses.append)

    proto.datagram_received(_tdp_datagram(response), (host, 20004))
    await proto._finalize_discovery()

    assert raw_responses == [
        {
            "discovery_response": response,
            "meta": {"ip": host, "port": 20004, "source": "tdp"},
        }
    ]


@pytest.mark.parametrize(
    ("discovery", "datagram", "message"),
    [
        (
            _UdpDiscovery(9999),
            XorEncryption.encrypt(json_dumps([]))[4:],
            "UDP discovery response.*did not contain a JSON object",
        ),
        (
            _TdpDiscovery(20002),
            _tdp_datagram([]),
            "TDP discovery response.*did not contain a JSON object",
        ),
    ],
)
def test_discovery_response_must_be_json_object(
    discovery, datagram: bytes, message: str
) -> None:
    """Valid non-object JSON is rejected by the endpoint parser."""
    with pytest.raises(KasaException, match=message):
        discovery.parse_response(datagram, "127.0.0.1")


async def test_tdp_endpoints_handle_separate_device_populations() -> None:
    """Ports 20002 and 20004 independently discover devices at different IPs."""
    regular_host = "127.0.0.1"
    low_energy_host = "127.0.0.2"
    proto = _DiscoverProtocol()

    proto.datagram_received(_tdp_datagram(TDP_DISCOVER_DATA), (regular_host, 20002))
    proto.datagram_received(_tdp_datagram(TDP_DISCOVER_DATA), (low_energy_host, 20004))
    await proto._wait_for_processing()

    assert set(proto.discovered_devices) == {regular_host, low_energy_host}
    assert proto._hosts[regular_host].tdp_port == 20002
    assert proto._hosts[low_energy_host].tdp_port == 20004


@pytest.mark.xdist_group(name="caplog")
async def test_unexpected_second_tdp_endpoint_is_ignored(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """A same-IP response on both TDP ports is an invariant violation."""
    host = "127.0.0.1"
    raw_responses = []
    proto = _DiscoverProtocol(on_discovered_raw=raw_responses.append)

    proto.datagram_received(_tdp_datagram(TDP_DISCOVER_DATA), (host, 20002))
    proto.datagram_received(_tdp_datagram(TDP_DISCOVER_DATA), (host, 20004))
    await proto._wait_for_processing()

    assert proto._hosts[host].tdp_port == 20002
    assert [response["meta"]["port"] for response in raw_responses] == [20002]
    assert "unexpectedly responded on TDP ports 20002 and 20004" in caplog.text
    assert "tdp-device-id" not in caplog.text


async def test_invalid_tdp_schema_is_not_unsupported() -> None:
    """A structurally invalid TDP result is a malformed response."""
    host = "127.0.0.1"
    invalid_result = {
        "result": {
            "device_type": "SMART.TAPOPLUG",
            "ip": host,
        }
    }
    proto = _DiscoverProtocol()

    proto.datagram_received(_tdp_datagram(invalid_result), (host, 20002))
    await proto._finalize_discovery()

    assert host in proto.invalid_device_exceptions
    assert host not in proto.unsupported_device_exceptions


async def test_tdp_device_is_emitted_before_finalization() -> None:
    """A supported TDP response is emitted as soon as it is verified."""
    host = "127.0.0.1"
    on_discovered = AsyncMock()
    proto = _DiscoverProtocol(on_discovered=on_discovered)

    proto.datagram_received(_tdp_datagram(TDP_DISCOVER_DATA), (host, 20002))
    await proto._wait_for_processing()
    await asyncio.gather(*proto.callback_tasks)

    device = proto.discovered_devices[host]
    on_discovered.assert_awaited_once_with(device)


async def test_udp_device_is_held_until_finalization() -> None:
    """A UDP-only datagram is not processed before the receive window closes."""
    host = "127.0.0.1"
    raw_responses = []
    proto = _DiscoverProtocol(on_discovered_raw=raw_responses.append)
    udp_datagram = XorEncryption.encrypt(json_dumps(UDP_DISCOVER_DATA))[4:]

    proto.datagram_received(udp_datagram, (host, 9999))
    await asyncio.sleep(0)

    assert host not in proto.discovered_devices
    assert proto._hosts[host].endpoints[9999].candidate is None
    assert len(proto._hosts[host].endpoints[9999].deferred_datagrams) == 1
    assert not raw_responses
    await proto._finalize_discovery()
    assert host in proto.discovered_devices
    assert len(raw_responses) == 1


async def test_duplicate_raw_response_is_emitted_once_per_source_port() -> None:
    """Repeated discovery rounds do not duplicate raw callback output."""
    host = "127.0.0.1"
    raw_responses = []
    proto = _DiscoverProtocol(on_discovered_raw=raw_responses.append)
    udp_datagram = XorEncryption.encrypt(json_dumps(UDP_DISCOVER_DATA))[4:]

    proto.datagram_received(udp_datagram, (host, 9999))
    proto.datagram_received(udp_datagram, (host, 9999))

    assert not raw_responses
    await proto._finalize_discovery()
    assert len(raw_responses) == 1


async def test_raw_callback_cannot_mutate_device_candidate() -> None:
    """Raw callback changes do not alter factory initialization data."""
    host = "127.0.0.1"

    def mutate_raw(response) -> None:
        response["discovery_response"].clear()

    proto = _DiscoverProtocol(on_discovered_raw=mutate_raw)
    udp_datagram = XorEncryption.encrypt(json_dumps(UDP_DISCOVER_DATA))[4:]

    proto.datagram_received(udp_datagram, (host, 9999))
    await proto._finalize_discovery()

    assert host in proto.discovered_devices
    assert proto.discovered_devices[host].model


@pytest.mark.parametrize("valid_first", [True, False])
async def test_udp_uses_first_usable_repeated_response(valid_first: bool) -> None:
    """UDP finalization scans repeated responses until the first usable one."""
    host = "127.0.0.1"
    raw_responses = []
    proto = _DiscoverProtocol(on_discovered_raw=raw_responses.append)
    valid = XorEncryption.encrypt(json_dumps(UDP_DISCOVER_DATA))[4:]
    invalid = XorEncryption.encrypt(json_dumps({"invalid": "response"}))[4:]

    datagrams = (valid, invalid) if valid_first else (invalid, valid)
    for datagram in datagrams:
        proto.datagram_received(datagram, (host, 9999))
    await proto._finalize_discovery()

    assert host in proto.discovered_devices
    assert raw_responses == [
        {
            "discovery_response": UDP_DISCOVER_DATA,
            "meta": {"ip": host, "port": 9999, "source": "udp"},
        }
    ]


@pytest.mark.parametrize("valid_first", [True, False])
async def test_tdp_uses_first_usable_repeated_response(valid_first: bool) -> None:
    """A TDP endpoint accepts its first usable repeated response."""
    host = "127.0.0.1"
    raw_responses = []
    proto = _DiscoverProtocol(on_discovered_raw=raw_responses.append)
    valid = _tdp_datagram(TDP_DISCOVER_DATA)
    invalid = _tdp_datagram({"not": "a device"})

    datagrams = (valid, invalid) if valid_first else (invalid, valid)
    for datagram in datagrams:
        proto.datagram_received(datagram, (host, 20002))
    await proto._wait_for_processing()

    assert host in proto.discovered_devices
    assert raw_responses == [
        {
            "discovery_response": TDP_DISCOVER_DATA,
            "meta": {"ip": host, "port": 20002, "source": "tdp"},
        }
    ]


async def test_tdp_endpoint_error_allows_later_usable_response() -> None:
    """A response-normalization error does not finalize its TDP endpoint."""
    host = "127.0.0.1"
    incomplete = json.loads(json.dumps(TDP_DISCOVER_DATA))
    del incomplete["result"]["mgt_encrypt_schm"]
    raw_responses = []
    proto = _DiscoverProtocol(on_discovered_raw=raw_responses.append)

    proto.datagram_received(_tdp_datagram(incomplete), (host, 20002))
    proto.datagram_received(_tdp_datagram(TDP_DISCOVER_DATA), (host, 20002))
    await proto._wait_for_processing()

    assert host in proto.discovered_devices
    assert host not in proto.unsupported_device_exceptions
    assert raw_responses[0]["discovery_response"] == TDP_DISCOVER_DATA


async def test_tdp_uses_normalized_source_ip_without_mutating_raw() -> None:
    """Connections use the source IP while raw data retains the advertised IP."""
    source_ip = "127.0.0.2"
    advertised_ip = TDP_DISCOVER_DATA["result"]["ip"]
    raw_responses = []
    proto = _DiscoverProtocol(on_discovered_raw=raw_responses.append)

    proto.datagram_received(_tdp_datagram(TDP_DISCOVER_DATA), (source_ip, 20002))
    await proto._wait_for_processing()

    device = proto.discovered_devices[source_ip]
    assert device.host == source_ip
    assert device._discovery_info["ip"] == source_ip
    assert raw_responses[0]["discovery_response"]["result"]["ip"] == advertised_ip


@pytest.mark.parametrize("port", [20002, 20004])
def test_tdp_ports_cannot_override_udp_discovery(port: int) -> None:
    """The UDP override cannot collide with a fixed TDP endpoint."""
    with pytest.raises(KasaException, match="reserved for TDP discovery"):
        _DiscoverProtocol(port=port)


async def test_finalization_ignores_late_datagrams(mocker) -> None:
    """The candidate set is frozen before final device creation awaits."""
    host = "127.0.0.1"
    late_host = "127.0.0.2"
    proto = _DiscoverProtocol()
    udp_datagram = XorEncryption.encrypt(json_dumps(UDP_DISCOVER_DATA))[4:]
    proto.datagram_received(udp_datagram, (host, 9999))
    device = MagicMock(spec=Device)
    device.host = host

    async def create_device(*args, **kwargs):
        proto.datagram_received(udp_datagram, (late_host, 9999))
        return device

    mocker.patch.object(proto, "_create_device", side_effect=create_device)
    await proto._finalize_discovery()

    assert set(proto.discovered_devices) == {host}
    assert late_host not in proto._hosts


async def test_tdp_discards_held_and_future_udp() -> None:
    """TDP erases held UDP and ignores every later UDP datagram."""
    host = "127.0.0.1"
    raw_responses = []
    proto = _DiscoverProtocol(on_discovered_raw=raw_responses.append)
    udp_datagram = XorEncryption.encrypt(json_dumps(UDP_DISCOVER_DATA))[4:]

    proto.datagram_received(udp_datagram, (host, 9999))
    assert len(proto._hosts[host].endpoints[9999].deferred_datagrams) == 1

    proto.datagram_received(_tdp_datagram(TDP_DISCOVER_DATA), (host, 20002))
    await proto._wait_for_processing()
    device = proto.discovered_devices[host]

    proto.datagram_received(udp_datagram, (host, 9999))

    assert proto.discovered_devices[host] is device
    assert device.config.connection_type.device_family is DeviceFamily.SmartTapoPlug
    assert proto._hosts[host].endpoints[20002].candidate.source is _DiscoverySource.Tdp
    assert not proto._hosts[host].endpoints[9999].deferred_datagrams
    assert [response["meta"]["source"] for response in raw_responses] == [
        _DiscoverySource.Tdp.value
    ]


async def test_unsupported_tdp_is_emitted_at_finalization() -> None:
    """An unsupported TDP result allows repeated responses before reporting."""
    host = "127.0.0.1"
    on_unsupported = AsyncMock()
    proto = _DiscoverProtocol(on_unsupported=on_unsupported)

    proto.datagram_received(_tdp_datagram(UNSUPPORTED), (host, 20002))
    await proto._finalize_discovery()
    await asyncio.gather(*proto.callback_tasks)

    error = proto.unsupported_device_exceptions[host]
    on_unsupported.assert_awaited_once_with(error)


async def test_tdp_iot_family_resolves_concrete_device_class(mocker) -> None:
    """A broad IOT TDP family is resolved from get_sysinfo before creation."""
    host = "127.0.0.1"
    strip_sysinfo = {
        "system": {
            "get_sysinfo": {
                **UDP_DISCOVER_DATA["system"]["get_sysinfo"],
                "children": [{"id": "socket-1"}],
                "model": "HS300(US)",
            }
        }
    }
    query = mocker.patch(
        "kasa.protocols.iotprotocol.IotProtocol.query",
        new=AsyncMock(return_value=strip_sysinfo),
    )
    proto = _DiscoverProtocol()

    proto.datagram_received(
        _tdp_datagram(AUTHENTICATION_DATA_KLAP),
        (host, 20002),
    )
    await proto._finalize_discovery()

    device = proto.discovered_devices[host]
    assert isinstance(device, IotStrip)
    assert device._last_update == strip_sysinfo
    assert device._discovery_info["device_type"] == "IOT.SMARTPLUGSWITCH"
    query.assert_awaited_once_with({"system": {"get_sysinfo": {}}})


async def test_tdp_iot_discards_held_udp_sysinfo(mocker) -> None:
    """A TDP IOT candidate erases held UDP before class resolution."""
    host = "127.0.0.1"
    strip_sysinfo = {
        "system": {
            "get_sysinfo": {
                **UDP_DISCOVER_DATA["system"]["get_sysinfo"],
                "children": [{"id": "socket-1"}],
                "model": "HS300(US)",
            }
        }
    }
    query = mocker.patch(
        "kasa.protocols.iotprotocol.IotProtocol.query",
        new=AsyncMock(side_effect=AuthenticationError("Authentication failed")),
    )
    on_authentication_error = AsyncMock()
    proto = _DiscoverProtocol(on_authentication_error=on_authentication_error)

    udp_datagram = XorEncryption.encrypt(json_dumps(strip_sysinfo))[4:]
    proto.datagram_received(udp_datagram, (host, 9999))
    proto.datagram_received(
        _tdp_datagram(AUTHENTICATION_DATA_KLAP),
        (host, 20002),
    )
    await proto._wait_for_processing()
    await asyncio.gather(*proto.callback_tasks)

    assert host not in proto.discovered_devices
    error = proto.authentication_exceptions[host]
    assert error.discovery_result == AUTHENTICATION_DATA_KLAP
    on_authentication_error.assert_awaited_once_with(error)
    assert proto._hosts[host].endpoints[20002].candidate.source is _DiscoverySource.Tdp
    assert not proto._hosts[host].endpoints[9999].deferred_datagrams
    query.assert_awaited_once_with({"system": {"get_sysinfo": {}}})


def test_select_discovery_response_uses_source_authority() -> None:
    """Shared raw-response selection uses source authority, not input order."""
    udp_response = {
        "discovery_response": UDP_DISCOVER_DATA,
        "meta": {"ip": "127.0.0.1", "port": 9999, "source": "udp"},
    }
    tdp_response = {
        "discovery_response": TDP_DISCOVER_DATA,
        "meta": {"ip": "127.0.0.1", "port": 20002, "source": "tdp"},
    }

    assert select_discovery_response([tdp_response, udp_response]) is tdp_response
    assert select_discovery_response([udp_response, tdp_response]) is tdp_response

    invalid_tdp_response = {
        "discovery_response": {"not": "a device"},
        "meta": {"ip": "127.0.0.1", "port": 20002, "source": "tdp"},
    }
    assert (
        select_discovery_response([invalid_tdp_response, udp_response])
        is invalid_tdp_response
    )

    tdp_20004_response = {
        "discovery_response": TDP_DISCOVER_DATA,
        "meta": {"ip": "127.0.0.2", "port": 20004, "source": "tdp"},
    }
    assert select_discovery_response([tdp_20004_response]) is tdp_20004_response


async def test_tdp_iot_auth_failure_is_emitted_immediately(mocker) -> None:
    """TDP-only IOT authentication is reported before finalization."""
    host = "127.0.0.1"
    query = mocker.patch(
        "kasa.protocols.iotprotocol.IotProtocol.query",
        new=AsyncMock(side_effect=AuthenticationError("Authentication failed")),
    )
    on_authentication_error = AsyncMock()
    proto = _DiscoverProtocol(on_authentication_error=on_authentication_error)

    proto.datagram_received(
        _tdp_datagram(AUTHENTICATION_DATA_KLAP),
        (host, 20002),
    )
    await proto._wait_for_processing()
    await asyncio.gather(*proto.callback_tasks)

    error = proto.authentication_exceptions[host]
    assert isinstance(error, DiscoveryAuthenticationError)
    assert error.host == host
    assert error.discovery_result == AUTHENTICATION_DATA_KLAP
    assert host not in proto.invalid_device_exceptions
    on_authentication_error.assert_awaited_once_with(error)
    assert query.await_count == 1


async def test_tdp_iot_unsupported_authentication_is_reported(mocker) -> None:
    """IOT class resolution classifies unsupported onboarding after auth fails."""
    host = "127.0.0.1"
    discovery_data = json.loads(json.dumps(AUTHENTICATION_DATA_KLAP))
    discovery_data["result"]["obd_src"] = "amazon"
    mocker.patch(
        "kasa.protocols.iotprotocol.IotProtocol.query",
        new=AsyncMock(side_effect=AuthenticationError("Authentication failed")),
    )
    on_unsupported = AsyncMock()
    proto = _DiscoverProtocol(on_unsupported=on_unsupported)

    proto.datagram_received(_tdp_datagram(discovery_data), (host, 20002))
    await proto._wait_for_processing()
    await asyncio.gather(*proto.callback_tasks)

    error = proto.unsupported_device_exceptions[host]
    assert isinstance(error, UnsupportedAuthenticationError)
    assert error.onboarding_source == "amazon"
    assert error.host == host
    on_unsupported.assert_awaited_once_with(error)


async def test_callback_unsupported_keeps_constructed_device() -> None:
    """An unsupported update outcome does not remove a constructed device."""
    host = "127.0.0.1"
    on_unsupported = AsyncMock()

    async def on_discovered(device: Device) -> None:
        raise UnsupportedDeviceError("Unsupported after creation", host=device.host)

    proto = _DiscoverProtocol(
        on_discovered=on_discovered,
        on_unsupported=on_unsupported,
    )
    proto.datagram_received(_tdp_datagram(TDP_DISCOVER_DATA), (host, 20002))
    await proto._wait_for_processing()
    await asyncio.gather(*proto.callback_tasks)

    assert host in proto.discovered_devices
    error = proto.unsupported_device_exceptions[host]
    on_unsupported.assert_awaited_once_with(error)


async def test_discover_single_uses_callback_error_pipeline(mocker) -> None:
    """Targeted discovery uses the same callback classification as broadcast."""
    host = "127.0.0.1"

    async def mock_discover(self) -> None:
        self.datagram_received(_tdp_datagram(TDP_DISCOVER_DATA), (host, 20002))

    async def on_discovered(device: Device) -> None:
        raise UnsupportedDeviceError("Unsupported after creation", host=device.host)

    mocker.patch.object(_DiscoverProtocol, "do_discover", mock_discover)
    on_unsupported = AsyncMock()

    device = await Discover.discover_single(
        host,
        on_discovered=on_discovered,
        on_unsupported=on_unsupported,
    )

    assert device is not None
    assert device.host == host
    error = on_unsupported.await_args.args[0]
    assert error.discovery_result["device_id"] == "tdp-device-id"
    await device.disconnect()


class FakeDatagramTransport(asyncio.DatagramTransport):
    GHOST_PORT = 8888

    def __init__(self, dp, port, do_not_reply_count, unsupported=False):
        self.dp = dp
        self.port = port
        self.do_not_reply_count = do_not_reply_count
        self.send_count = 0
        if port == 9999:
            self.datagram = XorEncryption.encrypt(json_dumps(UDP_DISCOVER_DATA))[4:]
        elif port == 20002:
            discovery_data = UNSUPPORTED if unsupported else TDP_DISCOVER_DATA
            self.datagram = (
                b"\x02\x00\x00\x01\x01[\x00\x00\x00\x00\x00\x00W\xcev\xf8"
                + json_dumps(discovery_data).encode()
            )
        else:
            self.datagram = {"foo": "bar"}

    def get_extra_info(self, name, default=None):
        return MagicMock()

    def sendto(self, data, addr=None):
        ip, port = addr
        if port == self.port or self.port == self.GHOST_PORT:
            self.send_count += 1
            if self.send_count > self.do_not_reply_count:
                self.dp.datagram_received(self.datagram, (ip, self.port))


@pytest.mark.parametrize("port", [9999, 20002])
@pytest.mark.parametrize("do_not_reply_count", [0, 1, 2, 3, 4])
async def test_do_discover_drop_packets(mocker, port, do_not_reply_count):
    """Make sure that _DiscoverProtocol handles authenticating devices correctly."""
    host = "127.0.0.1"
    discovery_timeout = 0

    dp = _DiscoverProtocol(
        target=host,
        discovery_timeout=discovery_timeout,
        discovery_packets=5,
    )
    ft = FakeDatagramTransport(dp, port, do_not_reply_count)
    dp.connection_made(ft)

    await dp.wait_for_discovery_to_complete()

    await asyncio.sleep(0)
    expected_sends = do_not_reply_count + 1 if port == 20002 else dp.discovery_packets
    assert ft.send_count == expected_sends
    assert dp.discover_task.done()
    assert not dp.discover_task.cancelled()


@pytest.mark.parametrize(
    ("port", "will_timeout"),
    [(FakeDatagramTransport.GHOST_PORT, True), (20002, False)],
    ids=["unknownport", "unsupporteddevice"],
)
async def test_do_discover_invalid(mocker, port, will_timeout):
    """Make sure that _DiscoverProtocol handles invalid devices correctly."""
    host = "127.0.0.1"
    discovery_timeout = 0

    dp = _DiscoverProtocol(
        target=host,
        discovery_timeout=discovery_timeout,
        discovery_packets=5,
    )
    ft = FakeDatagramTransport(dp, port, 0, unsupported=True)
    dp.connection_made(ft)

    await dp.wait_for_discovery_to_complete()
    await asyncio.sleep(0)
    assert dp.discover_task.done()
    assert not dp.discover_task.cancelled()
    if will_timeout:
        assert not dp._hosts
    else:
        assert host in dp.unsupported_device_exceptions


async def test_discover_propogates_task_exceptions(discovery_mock):
    """Make sure that discover propogates callback exceptions."""
    discovery_timeout = 0

    async def on_discovered(dev):
        raise KasaException("Dummy exception")

    with pytest.raises(KasaException):
        await Discover.discover(
            discovery_timeout=discovery_timeout, on_discovered=on_discovered
        )


async def test_completed_processing_task_exception_is_propagated(mocker) -> None:
    """A processing task that already failed is still consumed by the drain."""
    proto = _DiscoverProtocol()
    mocker.patch.object(
        proto,
        "_process_candidate",
        new=AsyncMock(side_effect=KasaException("processing failed")),
    )

    proto._run_processing_task("127.0.0.1", 20002)
    await asyncio.sleep(0)
    assert proto._processing_tasks[0].done()

    with pytest.raises(KasaException, match="processing failed"):
        await proto._wait_for_processing()


async def test_completed_callback_task_exception_is_propagated() -> None:
    """A callback that already failed is still consumed by the callback drain."""
    proto = _DiscoverProtocol()

    async def fail() -> None:
        raise KasaException("callback failed")

    proto._run_callback_task(fail())
    await asyncio.sleep(0)
    assert proto.callback_tasks[0].done()

    with pytest.raises(KasaException, match="callback failed"):
        await proto._wait_for_callbacks()


async def test_do_discover_no_connection(mocker):
    """Make sure that if the datagram connection doesnt start a TimeoutError is raised."""
    host = "127.0.0.1"
    discovery_timeout = 0
    mocker.patch.object(_DiscoverProtocol, "DISCOVERY_START_TIMEOUT", 0)
    dp = _DiscoverProtocol(
        target=host,
        discovery_timeout=discovery_timeout,
        discovery_packets=5,
    )
    # Normally tests would simulate connection as per below
    # ft = FakeDatagramTransport(dp, port, 0, unsupported=True)
    # dp.connection_made(ft)

    with pytest.raises(asyncio.TimeoutError):
        await dp.wait_for_discovery_to_complete()


async def test_do_discover_external_cancel(mocker):
    """Make sure that a cancel other than when target is discovered propogates."""
    host = "127.0.0.1"
    discovery_timeout = 1

    dp = _DiscoverProtocol(
        target=host,
        discovery_timeout=discovery_timeout,
        discovery_packets=1,
    )
    # Normally tests would simulate connection as per below
    ft = FakeDatagramTransport(dp, 9999, 1, unsupported=True)
    dp.connection_made(ft)

    with pytest.raises(asyncio.TimeoutError):
        async with asyncio_timeout(0):
            await dp.wait_for_discovery_to_complete()


@pytest.mark.xdist_group(name="caplog")
async def test_discovery_redaction(discovery_mock, caplog: pytest.LogCaptureFixture):
    """Test query sensitive info redaction."""
    mac = "12:34:56:78:9A:BC"

    if discovery_mock.default_port == 9999:
        sysinfo = discovery_mock.discovery_data["system"]["get_sysinfo"]
        if "mac" in sysinfo:
            sysinfo["mac"] = mac
        elif "mic_mac" in sysinfo:
            sysinfo["mic_mac"] = mac
    else:
        discovery_mock.discovery_data["result"]["mac"] = mac

    # Info no message logging
    caplog.set_level(logging.INFO)
    await Discover.discover()

    assert mac not in caplog.text

    caplog.set_level(logging.DEBUG)

    # Debug no redaction
    caplog.clear()
    Discover._redact_data = False
    await Discover.discover()
    assert mac in caplog.text

    # Debug redaction
    caplog.clear()
    Discover._redact_data = True
    await Discover.discover()
    assert mac not in caplog.text
    assert "12:34:56:00:00:00" in caplog.text


async def test_discovery_decryption():
    """Test discovery decryption."""
    key = b"8\x89\x02\xfa\xf5Xs\x1c\xa1 H\x9a\x82\xc7\xd9\t"
    iv = b"9=\xf8\x1bS\xcd0\xb5\x89i\xba\xfd^9\x9f\xfa"
    key_iv = key + iv

    query = _AesDiscoveryQuery()
    query.generate_query()
    keypair = query.keypair

    padding = asymmetric_padding.OAEP(
        mgf=asymmetric_padding.MGF1(algorithm=hashes.SHA1()),  # noqa: S303
        algorithm=hashes.SHA1(),  # noqa: S303
        label=None,
    )
    encrypted_key_iv = keypair.public_key.encrypt(key_iv, padding)
    encrypted_key_iv_b4 = base64.b64encode(encrypted_key_iv)
    encryption_session = AesEncyptionSession(key_iv[:16], key_iv[16:])

    data_dict = {"foo": 1, "bar": 2}
    data = json.dumps(data_dict)
    encypted_data = encryption_session.encrypt(data.encode())

    encrypt_info = {
        "data": encypted_data.decode(),
        "key": encrypted_key_iv_b4.decode(),
        "sym_schm": "AES",
    }
    info = {**UNSUPPORTED["result"], "encrypt_info": encrypt_info}
    dr = DiscoveryResult.from_dict(info)
    _TdpDiscovery.decrypt_discovery_data(dr, keypair=keypair)
    assert dr.decrypted_data == data_dict


async def test_discover_try_connect_all(discovery_mock, mocker):
    """Test that device update is called on main."""
    if "result" in discovery_mock.discovery_data:
        dev_class = get_device_class_from_discovery(
            discovery_mock.discovery_data, discovery_mock.query_data
        )
        cparams = DeviceConnectionParameters.from_values(
            discovery_mock.device_type,
            discovery_mock.encrypt_type,
            login_version=discovery_mock.login_version,
            klap_version=discovery_mock.klap_version,
            https=discovery_mock.https,
            http_port=discovery_mock.http_port,
        )
        protocol = get_protocol(
            DeviceConfig(discovery_mock.ip, connection_type=cparams)
        )
        protocol_class = protocol.__class__
        transport_class = protocol._transport.__class__
    else:
        dev_class = get_device_class_from_sys_info(discovery_mock.discovery_data)
        protocol_class = IotProtocol
        transport_class = XorTransport

    default_port = discovery_mock.default_port

    async def _query(self, *args, **kwargs):
        if (
            self.__class__ is protocol_class
            and self._transport.__class__ is transport_class
            and self._transport._port == default_port
        ):
            return discovery_mock.query_data
        raise KasaException("Unable to execute query")

    async def _update(self, *args, **kwargs):
        if (
            self.protocol.__class__ is protocol_class
            and self.protocol._transport.__class__ is transport_class
            and self.protocol._transport._port == default_port
        ):
            return

        raise KasaException("Unable to execute update")

    mocker.patch("kasa.IotProtocol.query", new=_query)
    mocker.patch("kasa.SmartProtocol.query", new=_query)
    mocker.patch.object(dev_class, "update", new=_update)

    session = aiohttp.ClientSession()
    dev = await Discover.try_connect_all(discovery_mock.ip, http_client=session)

    assert dev
    assert isinstance(dev, dev_class)
    assert isinstance(dev.protocol, protocol_class)
    assert isinstance(dev.protocol._transport, transport_class)
    assert dev.config.uses_http is (transport_class != XorTransport)
    if transport_class != XorTransport:
        assert dev.protocol._transport._http_client.client == session


async def test_discovery_device_repr(discovery_mock, mocker):
    """Test that repr works when only discovery data is available."""
    host = "foobar"
    ip = "127.0.0.1"

    discovery_mock.ip = ip
    device_class = get_device_class_from_discovery(
        discovery_mock.discovery_data, discovery_mock.query_data
    )
    update_mock = mocker.patch.object(device_class, "update")

    dev = await Discover.discover_single(host, credentials=Credentials())
    assert update_mock.call_count == 0

    repr_ = repr(dev)
    assert dev.host in repr_
    assert str(dev.device_type) in repr_
    assert dev.model in repr_

    # For IOT devices, _last_update is filled from the discovery data
    if dev._last_update:
        assert "update() needed" not in repr_
    else:
        assert "update() needed" in repr_
