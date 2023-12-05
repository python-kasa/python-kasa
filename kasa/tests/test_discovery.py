# type: ignore
import re
import socket

import pytest  # type: ignore # https://github.com/pytest-dev/pytest/issues/3342

from kasa import (
    DeviceType,
    Discover,
    SmartDevice,
    SmartDeviceException,
    SmartStrip,
    protocol,
)
from kasa.discover import DiscoveryResult, _DiscoverProtocol, json_dumps
from kasa.exceptions import AuthenticationException, UnsupportedDeviceException

from .conftest import bulb, bulb_iot, dimmer, lightstrip, plug, strip

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
    update_mock = mocker.patch.object(SmartStrip, "update")

    x = await Discover.discover_single(host, port=custom_port)
    assert issubclass(x.__class__, SmartDevice)
    assert x._discovery_info is not None
    assert x.port == custom_port or x.port == discovery_mock.default_port
    assert (update_mock.call_count > 0) == isinstance(x, SmartStrip)


async def test_discover_single_hostname(discovery_mock, mocker):
    """Make sure that discover_single returns an initialized SmartDevice instance."""
    host = "foobar"
    ip = "127.0.0.1"

    discovery_mock.ip = ip
    update_mock = mocker.patch.object(SmartStrip, "update")

    x = await Discover.discover_single(host)
    assert issubclass(x.__class__, SmartDevice)
    assert x._discovery_info is not None
    assert x.host == host
    assert (update_mock.call_count > 0) == isinstance(x, SmartStrip)

    mocker.patch("socket.getaddrinfo", side_effect=socket.gaierror())
    with pytest.raises(SmartDeviceException):
        x = await Discover.discover_single(host)


async def test_discover_single_unsupported(mocker):
    """Make sure that discover_single handles unsupported devices correctly."""
    host = "127.0.0.1"

    def mock_discover(self):
        if discovery_data:
            data = (
                b"\x02\x00\x00\x01\x01[\x00\x00\x00\x00\x00\x00W\xcev\xf8"
                + json_dumps(discovery_data).encode()
            )
            self.datagram_received(data, (host, 20002))

    mocker.patch.object(_DiscoverProtocol, "do_discover", mock_discover)

    # Test with a valid unsupported response
    discovery_data = UNSUPPORTED
    with pytest.raises(
        UnsupportedDeviceException,
        match=f"Unsupported device {host} of type SMART.TAPOXMASTREE: {re.escape(str(UNSUPPORTED))}",
    ):
        await Discover.discover_single(host)

    # Test with no response
    discovery_data = None
    with pytest.raises(
        SmartDeviceException, match=f"Timed out getting discovery response for {host}"
    ):
        await Discover.discover_single(host, timeout=0.001)


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
    assert len(proto.unsupported_devices) == 1
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


async def test_discover_single_authentication(mocker):
    """Make sure that discover_single handles authenticating devices correctly."""
    host = "127.0.0.1"

    def mock_discover(self):
        if discovery_data:
            data = (
                b"\x02\x00\x00\x01\x01[\x00\x00\x00\x00\x00\x00W\xcev\xf8"
                + json_dumps(discovery_data).encode()
            )
            self.datagram_received(data, (host, 20002))

    mocker.patch.object(_DiscoverProtocol, "do_discover", mock_discover)
    mocker.patch.object(
        SmartDevice,
        "update",
        side_effect=AuthenticationException("Failed to authenticate"),
    )

    # Test with a valid unsupported response
    discovery_data = AUTHENTICATION_DATA_KLAP
    with pytest.raises(
        AuthenticationException,
        match="Failed to authenticate",
    ):
        device = await Discover.discover_single(host)
        await device.update()

    mocker.patch.object(SmartDevice, "update")
    device = await Discover.discover_single(host)
    await device.update()
    assert device.device_type == DeviceType.Plug


async def test_device_update_from_new_discovery_info():
    device = SmartDevice("127.0.0.7")
    discover_info = DiscoveryResult(**AUTHENTICATION_DATA_KLAP["result"])
    discover_dump = discover_info.get_dict()
    device.update_from_discover_info(discover_dump)

    assert device.alias == discover_dump["alias"]
    assert device.mac == discover_dump["mac"].replace("-", ":")
    assert device.model == discover_dump["model"]

    with pytest.raises(
        SmartDeviceException,
        match=re.escape("You need to await update() to access the data"),
    ):
        assert device.supported_modules
