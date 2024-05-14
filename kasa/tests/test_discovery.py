# type: ignore
import asyncio
import re
import socket
from unittest.mock import MagicMock

import aiohttp
import pytest  # type: ignore # https://github.com/pytest-dev/pytest/issues/3342
from async_timeout import timeout as asyncio_timeout

from kasa import (
    Credentials,
    Device,
    DeviceType,
    Discover,
    KasaException,
)
from kasa.deviceconfig import (
    ConnectionType,
    DeviceConfig,
)
from kasa.discover import DiscoveryResult, _DiscoverProtocol, json_dumps
from kasa.exceptions import AuthenticationError, UnsupportedDeviceError
from kasa.iot import IotDevice
from kasa.xortransport import XorEncryption

from .conftest import (
    bulb_iot,
    dimmer_iot,
    lightstrip_iot,
    new_discovery,
    plug_iot,
    strip_iot,
    wallswitch_iot,
)

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
    assert d.is_wallswitch
    assert d.device_type == DeviceType.WallSwitch


@plug_iot
async def test_type_detection_plug(dev: Device):
    d = Discover._get_device_class(dev._last_update)("localhost")
    assert d.is_plug
    assert d.device_type == DeviceType.Plug


@bulb_iot
async def test_type_detection_bulb(dev: Device):
    d = Discover._get_device_class(dev._last_update)("localhost")
    # TODO: light_strip is a special case for now to force bulb tests on it
    if not d.is_light_strip:
        assert d.is_bulb
        assert d.device_type == DeviceType.Bulb


@strip_iot
async def test_type_detection_strip(dev: Device):
    d = Discover._get_device_class(dev._last_update)("localhost")
    assert d.is_strip
    assert d.device_type == DeviceType.Strip


@dimmer_iot
async def test_type_detection_dimmer(dev: Device):
    d = Discover._get_device_class(dev._last_update)("localhost")
    assert d.is_dimmer
    assert d.device_type == DeviceType.Dimmer


@lightstrip_iot
async def test_type_detection_lightstrip(dev: Device):
    d = Discover._get_device_class(dev._last_update)("localhost")
    assert d.is_light_strip
    assert d.device_type == DeviceType.LightStrip


async def test_type_unknown():
    invalid_info = {"system": {"get_sysinfo": {"type": "nosuchtype"}}}
    with pytest.raises(UnsupportedDeviceError):
        Discover._get_device_class(invalid_info)


@pytest.mark.parametrize("custom_port", [123, None])
# @pytest.mark.parametrize("discovery_mock", [("127.0.0.1",123), ("127.0.0.1",None)], indirect=True)
async def test_discover_single(discovery_mock, custom_port, mocker):
    """Make sure that discover_single returns an initialized SmartDevice instance."""
    host = "127.0.0.1"
    discovery_mock.ip = host
    discovery_mock.port_override = custom_port

    device_class = Discover._get_device_class(discovery_mock.discovery_data)
    update_mock = mocker.patch.object(device_class, "update")

    x = await Discover.discover_single(
        host, port=custom_port, credentials=Credentials()
    )
    assert issubclass(x.__class__, Device)
    assert x._discovery_info is not None
    assert x.port == custom_port or x.port == discovery_mock.default_port
    assert update_mock.call_count == 0
    if discovery_mock.default_port == 80:
        assert x.alias is None

    ct = ConnectionType.from_values(
        discovery_mock.device_type,
        discovery_mock.encrypt_type,
        discovery_mock.login_version,
    )
    uses_http = discovery_mock.default_port == 80
    config = DeviceConfig(
        host=host,
        port_override=custom_port,
        connection_type=ct,
        uses_http=uses_http,
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
    ("Unknown device type: foo", {"system": {"get_sysinfo": {"type": "foo"}}}),
]


@pytest.mark.parametrize("msg, data", INVALIDS)
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

    # Check that device in discovered_devices is initialized correctly
    assert len(proto.discovered_devices) == 1
    # Check that unsupported device is 1
    assert len(proto.unsupported_device_exceptions) == 1
    dev = proto.discovered_devices[addr]
    assert issubclass(dev.__class__, Device)
    assert dev.host == addr


@pytest.mark.parametrize("msg, data", INVALIDS)
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

    with pytest.raises(
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
    discover_info = DiscoveryResult(**discovery_data["result"])
    discover_dump = discover_info.get_dict()
    model, _, _ = discover_dump["device_model"].partition("(")
    discover_dump["model"] = model
    device.update_from_discover_info(discover_dump)

    assert device.mac == discover_dump["mac"].replace("-", ":")
    assert device.model == model

    # TODO implement requires_update for SmartDevice
    if isinstance(device, IotDevice):
        with pytest.raises(
            KasaException,
            match=re.escape("You need to await update() to access the data"),
        ):
            assert device.supported_modules


async def test_discover_single_http_client(discovery_mock, mocker):
    """Make sure that discover_single returns an initialized SmartDevice instance."""
    host = "127.0.0.1"
    discovery_mock.ip = host

    http_client = aiohttp.ClientSession()

    x: Device = await Discover.discover_single(host)

    assert x.config.uses_http == (discovery_mock.default_port == 80)

    if discovery_mock.default_port == 80:
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
    assert x.config.uses_http == (discovery_mock.default_port == 80)

    if discovery_mock.default_port == 80:
        assert x.protocol._transport._http_client.client != http_client
        x.config.http_client = http_client
        assert x.protocol._transport._http_client.client == http_client


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
    "port, will_timeout",
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
