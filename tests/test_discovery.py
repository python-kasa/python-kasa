# type: ignore
# ruff: noqa: S106

import asyncio
import base64
import json
import logging
import re
import socket
from asyncio import timeout as asyncio_timeout
from unittest.mock import MagicMock

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
from kasa.device_factory import (
    get_device_class_from_family,
    get_device_class_from_sys_info,
    get_protocol,
)
from kasa.deviceconfig import (
    DeviceConfig,
    DeviceConnectionParameters,
)
from kasa.discover import (
    DiscoveryResult,
    _AesDiscoveryQuery,
    _DiscoverProtocol,
    json_dumps,
)
from kasa.exceptions import AuthenticationError, UnsupportedDeviceError
from kasa.iot import IotDevice, IotPlug
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


@wallswitch_iot
async def test_type_detection_switch(dev: Device):
    d = Discover._get_device_class(dev._last_update)("localhost")
    with pytest.deprecated_call(match="use device_type property instead"):
        assert d.is_wallswitch
    assert d.device_type is DeviceType.WallSwitch


@plug_iot
async def test_type_detection_plug(dev: Device):
    d = Discover._get_device_class(dev._last_update)("localhost")
    assert d.device_type == DeviceType.Plug


@bulb_iot
async def test_type_detection_bulb(dev: Device):
    d = Discover._get_device_class(dev._last_update)("localhost")
    # TODO: light_strip is a special case for now to force bulb tests on it

    if d.device_type is not DeviceType.LightStrip:
        assert d.device_type == DeviceType.Bulb


@strip_iot
async def test_type_detection_strip(dev: Device):
    d = Discover._get_device_class(dev._last_update)("localhost")
    assert d.device_type == DeviceType.Strip


@dimmer_iot
async def test_type_detection_dimmer(dev: Device):
    d = Discover._get_device_class(dev._last_update)("localhost")
    assert d.device_type == DeviceType.Dimmer


@lightstrip_iot
async def test_type_detection_lightstrip(dev: Device):
    d = Discover._get_device_class(dev._last_update)("localhost")
    assert d.device_type == DeviceType.LightStrip


@pytest.mark.xdist_group(name="caplog")
async def test_type_unknown(caplog):
    invalid_info = {"system": {"get_sysinfo": {"type": "nosuchtype"}}}
    assert Discover._get_device_class(invalid_info) is IotPlug
    msg = "Unknown device type nosuchtype, falling back to plug"
    assert msg in caplog.text


@pytest.mark.parametrize("custom_port", [123, None])
async def test_discover_single(discovery_mock, custom_port, mocker):
    """Make sure that discover_single returns an initialized SmartDevice instance."""
    host = "127.0.0.1"
    discovery_mock.ip = host
    discovery_mock.port_override = custom_port

    disco_data = discovery_mock.discovery_data
    device_class = Discover._get_device_class(disco_data)
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
        assert x.alias is None

    ct = DeviceConnectionParameters.from_values(
        discovery_mock.device_type,
        discovery_mock.encrypt_type,
        login_version=discovery_mock.login_version,
        https=discovery_mock.https,
        http_port=discovery_mock.http_port,
        new_klap=discovery_mock.new_klap,
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
    device_class = Discover._get_device_class(discovery_mock.discovery_data)
    update_mock = mocker.patch.object(device_class, "update")

    x = await Discover.discover_single(host, credentials=Credentials())
    assert issubclass(x.__class__, Device)
    assert x._discovery_info is not None
    assert x.host == host
    assert update_mock.call_count == 0

    mocker.patch("socket.getaddrinfo", side_effect=socket.gaierror())
    with pytest.raises(KasaException):
        x = await Discover.discover_single(host, credentials=Credentials())


@pytest.mark.parametrize("entrypoint", ["discover", "discover_single"])
async def test_credentials_precedence(entrypoint, mocker):
    """Ensure credentials precedence logic is identical for discover and discover_single."""
    host = "127.0.0.1"

    async def mock_discover(self, *_, **__):
        self.discovered_devices = {host: MagicMock()}
        self.seen_hosts.add(host)
        self._handle_discovered_event()

    mocker.patch.object(_DiscoverProtocol, "do_discover", new=mock_discover)
    dp = mocker.spy(_DiscoverProtocol, "__init__")

    # Only credentials passed
    if entrypoint == "discover":
        await Discover.discover(credentials=Credentials(), timeout=0)
    else:
        await Discover.discover_single(host, credentials=Credentials(), timeout=0)
    assert dp.mock_calls[0].kwargs["credentials"] == Credentials()

    # Credentials and un/pw passed
    if entrypoint == "discover":
        await Discover.discover(
            credentials=Credentials(), username="Foo", password="Bar", timeout=0
        )
    else:
        await Discover.discover_single(
            host, credentials=Credentials(), username="Foo", password="Bar", timeout=0
        )
    assert dp.mock_calls[1].kwargs["credentials"] == Credentials()

    # Only un/pw passed
    if entrypoint == "discover":
        await Discover.discover(username="Foo", password="Bar", timeout=0)
    else:
        await Discover.discover_single(host, username="Foo", password="Bar", timeout=0)
    assert dp.mock_calls[2].kwargs["credentials"] == Credentials("Foo", "Bar")

    # Only un passed, credentials should be None
    if entrypoint == "discover":
        await Discover.discover(username="Foo", timeout=0)
    else:
        await Discover.discover_single(host, username="Foo", timeout=0)
    assert dp.mock_calls[3].kwargs["credentials"] is None


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
    proto = _DiscoverProtocol(discovery_timeout=discovery_timeout)
    assert proto.discovery_packets == 3
    assert proto.target_1 == ("255.255.255.255", 9999)
    transport = mocker.patch.object(proto, "transport")
    await proto.do_discover()
    assert transport.sendto.call_count == proto.discovery_packets * 2


async def test_discover_datagram_received(mocker, discovery_data):
    """Verify that datagram received fills discovered_devices."""
    proto = _DiscoverProtocol()

    mocker.patch.object(XorEncryption, "decrypt")

    addr = "127.0.0.1"
    port = 20002 if "result" in discovery_data else 9999

    mocker.patch("kasa.discover.json_loads", return_value=discovery_data)
    proto.datagram_received("<placeholder data>", (addr, port))

    addr2 = "127.0.0.2"
    mocker.patch("kasa.discover.json_loads", return_value=UNSUPPORTED)
    proto.datagram_received("<placeholder data>", (addr2, 20002))

    # Wait for async processing of the discovery callbacks to finish
    if proto.callback_tasks:
        await asyncio.gather(*proto.callback_tasks, return_exceptions=True)

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


@new_discovery
async def test_discover_single_authentication(discovery_mock, mocker):
    """Make sure that discover_single handles authenticating devices correctly."""
    host = "127.0.0.1"
    discovery_mock.ip = host
    device_class = Discover._get_device_class(discovery_mock.discovery_data)
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
    device_class = Discover._get_device_class(discovery_data)
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
            assert device.supported_modules


@pytest.mark.parametrize("entrypoint", ["discover_single", "discover"])
async def test_http_client_passthrough(discovery_mock, mocker, entrypoint):
    """Ensure HTTP client handling is consistent for discover and discover_single."""
    host = "127.0.0.1"
    discovery_mock.ip = host

    http_client = aiohttp.ClientSession()
    try:
        if entrypoint == "discover_single":
            dev: Device = await Discover.discover_single(host)
        else:
            devices = await Discover.discover(discovery_timeout=0)
            dev: Device = devices[host]

        assert dev.config.uses_http == (discovery_mock.default_port != 9999)

        if discovery_mock.default_port != 9999:
            assert dev.protocol._transport._http_client.client != http_client
            dev.config.http_client = http_client
            assert dev.protocol._transport._http_client.client == http_client
    finally:
        await http_client.close()


LEGACY_DISCOVER_DATA = {
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


class FakeDatagramTransport(asyncio.DatagramTransport):
    GHOST_PORT = 8888

    def __init__(self, dp, port, do_not_reply_count, unsupported=False):
        self.dp = dp
        self.port = port
        self.do_not_reply_count = do_not_reply_count
        self.send_count = 0
        if port == 9999:
            self.datagram = XorEncryption.encrypt(json_dumps(LEGACY_DISCOVER_DATA))[4:]
        elif port == 20002:
            discovery_data = UNSUPPORTED if unsupported else AUTHENTICATION_DATA_KLAP
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
    assert ft.send_count == do_not_reply_count + 1
    assert dp.discover_task.done()
    assert dp.discover_task.cancelled()


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
    assert dp.discover_task.cancelled() != will_timeout


async def test_discover_propogates_task_exceptions(discovery_mock):
    """Make sure that discover propogates callback exceptions."""
    discovery_timeout = 0

    async def on_discovered(dev):
        raise KasaException("Dummy exception")

    with pytest.raises(KasaException):
        await Discover.discover(
            discovery_timeout=discovery_timeout, on_discovered=on_discovered
        )


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

    _AesDiscoveryQuery.generate_query()
    keypair = _AesDiscoveryQuery.keypair

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
    Discover._decrypt_discovery_data(dr)
    assert dr.decrypted_data == data_dict


async def test_discover_try_connect_all(discovery_mock, mocker):
    """Test that device update is called on main."""
    if "result" in discovery_mock.discovery_data:
        dev_class = get_device_class_from_family(
            discovery_mock.device_type, https=discovery_mock.https
        )
        cparams = DeviceConnectionParameters.from_values(
            discovery_mock.device_type,
            discovery_mock.encrypt_type,
            login_version=discovery_mock.login_version,
            https=discovery_mock.https,
            http_port=discovery_mock.http_port,
            new_klap=discovery_mock.new_klap,
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
    device_class = Discover._get_device_class(discovery_mock.discovery_data)
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


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "info",
    "needs_query",
    "host",
    [
        (
            {
                "result": {
                    "device_type": "IOT.SMARTPLUGSWITCH",
                    "device_model": "HS100(UK)",
                    "device_id": "id",
                    "ip": "127.0.0.1",
                    "mac": "00-00-00-00-00-00",
                    "mgt_encrypt_schm": {
                        "is_support_https": False,
                        "encrypt_type": "KLAP",
                        "http_port": 9999,
                        "lv": 1,
                        "new_klap": 1,
                    },
                    # Force decrypt attempt to run and be logged (will fail harmlessly and be caught/logged)
                    "encrypt_info": {"sym_schm": "AES", "key": "", "data": ""},
                }
            },
            True,
            "127.0.0.1",
        ),
        (
            {
                "result": {
                    "device_type": "SMART.IPCAMERA",
                    "device_model": "C100(US)",
                    "device_id": "id",
                    "ip": "127.0.0.2",
                    "mac": "00-00-00-00-00-01",
                    "mgt_encrypt_schm": {
                        "is_support_https": True,
                        "encrypt_type": "AES",
                        "http_port": 443,
                        "lv": 3,
                    },
                    "encrypt_type": ["3"],
                }
            },
            False,
            "127.0.0.2",
        ),
    ],
    ids=["new_klap_unsupported", "non_iot_unsupported"],
)
async def test_get_device_instance_unsupported_logs(
    mocker, caplog, info, needs_query, host
):
    caplog.set_level(logging.DEBUG)

    class DummyProt:
        def __init__(self):
            self._transport = MagicMock()

        async def close(self):
            return None

        # Only needed for the new_klap case to drive get_device_class(sysinfo)
        if needs_query:

            async def query(self, req):
                return {"system": {"get_sysinfo": {"mic_type": "IOT.SMARTPLUGSWITCH"}}}

    mocker.patch("kasa.discover.get_protocol", return_value=DummyProt())
    # Force device_class resolution to fail to trigger the debug log and UnsupportedDeviceError
    mocker.patch("kasa.discover.Discover._get_device_class", return_value=None)

    with pytest.raises(UnsupportedDeviceError):
        await Discover._get_device_instance(info, DeviceConfig(host=host))

    # Validate the debug log was emitted
    assert "Got unsupported device type" in caplog.text


def test_datagram_received_logs_for_exceptions(caplog, mocker):
    proto = _DiscoverProtocol()
    caplog.set_level(logging.DEBUG)

    ip1 = "127.0.0.10"
    ip2 = "127.0.0.11"

    # First call raises UnsupportedDeviceError -> goes to unsupported_device_exceptions and logs
    mocker.patch(
        "kasa.discover.Discover._get_discovery_json",
        side_effect=[UnsupportedDeviceError("boom"), KasaException("bad")],
    )

    proto.datagram_received(b"x", (ip1, Discover.DISCOVERY_PORT_2))
    proto.datagram_received(b"x", (ip2, Discover.DISCOVERY_PORT_2))

    # Bookkeeping recorded correctly
    assert ip1 in proto.unsupported_device_exceptions
    assert ip2 in proto.invalid_device_exceptions

    # Logs were written
    assert f"Unsupported device found at {ip1} << boom" in caplog.text
    assert f"[DISCOVERY] Unable to find device type for {ip2}: bad" in caplog.text
