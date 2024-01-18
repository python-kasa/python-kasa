# type: ignore
import logging
import re
import socket

import aiohttp
import pytest  # type: ignore # https://github.com/pytest-dev/pytest/issues/3342

from kasa import (
    Credentials,
    DeviceType,
    Discover,
    SmartDevice,
    SmartDeviceException,
    protocol,
)
from kasa.deviceconfig import (
    ConnectionType,
    DeviceConfig,
    DeviceFamilyType,
    EncryptType,
)
from kasa.discover import DiscoveryResult, _DiscoverProtocol, json_dumps
from kasa.exceptions import AuthenticationException, UnsupportedDeviceException

from .conftest import bulb, bulb_iot, dimmer, lightstrip, new_discovery, plug, strip

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


@plug
async def test_type_detection_plug(dev: SmartDevice):
    d = Discover._get_device_class(dev._last_update)("localhost")
    assert d.is_plug
    assert d.device_type == DeviceType.Plug


@bulb_iot
async def test_type_detection_bulb(dev: SmartDevice):
    d = Discover._get_device_class(dev._last_update)("localhost")
    # TODO: light_strip is a special case for now to force bulb tests on it
    if not d.is_light_strip:
        assert d.is_bulb
        assert d.device_type == DeviceType.Bulb


@strip
async def test_type_detection_strip(dev: SmartDevice):
    d = Discover._get_device_class(dev._last_update)("localhost")
    assert d.is_strip
    assert d.device_type == DeviceType.Strip


@dimmer
async def test_type_detection_dimmer(dev: SmartDevice):
    d = Discover._get_device_class(dev._last_update)("localhost")
    assert d.is_dimmer
    assert d.device_type == DeviceType.Dimmer


@lightstrip
async def test_type_detection_lightstrip(dev: SmartDevice):
    d = Discover._get_device_class(dev._last_update)("localhost")
    assert d.is_light_strip
    assert d.device_type == DeviceType.LightStrip


async def test_type_unknown():
    invalid_info = {"system": {"get_sysinfo": {"type": "nosuchtype"}}}
    with pytest.raises(UnsupportedDeviceException):
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
    assert issubclass(x.__class__, SmartDevice)
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
    assert issubclass(x.__class__, SmartDevice)
    assert x._discovery_info is not None
    assert x.host == host
    assert update_mock.call_count == 0

    mocker.patch("socket.getaddrinfo", side_effect=socket.gaierror())
    with pytest.raises(SmartDeviceException):
        x = await Discover.discover_single(host, credentials=Credentials())


async def test_discover_single_unsupported(unsupported_device_info, mocker):
    """Make sure that discover_single handles unsupported devices correctly."""
    host = "127.0.0.1"

    # Test with a valid unsupported response
    with pytest.raises(
        UnsupportedDeviceException,
    ):
        await Discover.discover_single(host)


async def test_discover_single_no_response(mocker):
    """Make sure that discover_single handles no response correctly."""
    host = "127.0.0.1"
    mocker.patch.object(_DiscoverProtocol, "do_discover")
    with pytest.raises(
        SmartDeviceException, match=f"Timed out getting discovery response for {host}"
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

    def mock_discover(self):
        self.datagram_received(
            protocol.TPLinkSmartHomeProtocol.encrypt(json_dumps(data))[4:], (host, 9999)
        )

    mocker.patch.object(_DiscoverProtocol, "do_discover", mock_discover)

    with pytest.raises(SmartDeviceException, match=msg):
        await Discover.discover_single(host)


async def test_discover_send(mocker):
    """Test discovery parameters."""
    proto = _DiscoverProtocol()
    assert proto.discovery_packets == 3
    assert proto.target == ("255.255.255.255", 9999)
    transport = mocker.patch.object(proto, "transport")
    proto.do_discover()
    assert transport.sendto.call_count == proto.discovery_packets * 2


async def test_discover_datagram_received(mocker, discovery_data):
    """Verify that datagram received fills discovered_devices."""
    proto = _DiscoverProtocol()

    mocker.patch.object(protocol.TPLinkSmartHomeProtocol, "decrypt")

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
    assert issubclass(dev.__class__, SmartDevice)
    assert dev.host == addr


@pytest.mark.parametrize("msg, data", INVALIDS)
async def test_discover_invalid_responses(msg, data, mocker):
    """Verify that we don't crash whole discovery if some devices in the network are sending unexpected data."""
    proto = _DiscoverProtocol()
    mocker.patch("kasa.discover.json_loads", return_value=data)
    mocker.patch.object(protocol.TPLinkSmartHomeProtocol, "encrypt")
    mocker.patch.object(protocol.TPLinkSmartHomeProtocol, "decrypt")

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
        side_effect=AuthenticationException("Failed to authenticate"),
    )

    with pytest.raises(
        AuthenticationException,
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
async def test_device_update_from_new_discovery_info(discovery_data):
    device = SmartDevice("127.0.0.7")
    discover_info = DiscoveryResult(**discovery_data["result"])
    discover_dump = discover_info.get_dict()
    discover_dump["alias"] = "foobar"
    discover_dump["model"] = discover_dump["device_model"]
    device.update_from_discover_info(discover_dump)

    assert device.alias == "foobar"
    assert device.mac == discover_dump["mac"].replace("-", ":")
    assert device.model == discover_dump["device_model"]

    with pytest.raises(
        SmartDeviceException,
        match=re.escape("You need to await update() to access the data"),
    ):
        assert device.supported_modules


async def test_discover_single_http_client(discovery_mock, mocker):
    """Make sure that discover_single returns an initialized SmartDevice instance."""
    host = "127.0.0.1"
    discovery_mock.ip = host

    http_client = aiohttp.ClientSession()

    x: SmartDevice = await Discover.discover_single(host)

    assert x.config.uses_http == (discovery_mock.default_port == 80)

    if discovery_mock.default_port == 80:
        assert x.protocol._transport._http_client.client != http_client
        x.config.http_client = http_client
        assert x.protocol._transport._http_client.client == http_client


async def test_discover_http_client(discovery_mock, mocker):
    """Make sure that discover_single returns an initialized SmartDevice instance."""
    host = "127.0.0.1"
    discovery_mock.ip = host

    http_client = aiohttp.ClientSession()

    devices = await Discover.discover(discovery_timeout=0)
    x: SmartDevice = devices[host]
    assert x.config.uses_http == (discovery_mock.default_port == 80)

    if discovery_mock.default_port == 80:
        assert x.protocol._transport._http_client.client != http_client
        x.config.http_client = http_client
        assert x.protocol._transport._http_client.client == http_client
