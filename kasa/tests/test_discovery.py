# type: ignore
import re
import sys

import pytest  # type: ignore # https://github.com/pytest-dev/pytest/issues/3342

from kasa import DeviceType, Discover, SmartDevice, SmartDeviceException, protocol
from kasa.discover import _DiscoverProtocol, json_dumps
from kasa.exceptions import UnsupportedDeviceException

from .conftest import bulb, dimmer, lightstrip, plug, strip


@plug
async def test_type_detection_plug(dev: SmartDevice):
    d = Discover._get_device_class(dev._last_update)("localhost")
    assert d.is_plug
    assert d.device_type == DeviceType.Plug


@bulb
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
    with pytest.raises(SmartDeviceException):
        Discover._get_device_class(invalid_info)


@pytest.mark.parametrize("custom_port", [123, None])
async def test_discover_single(discovery_data: dict, mocker, custom_port):
    """Make sure that discover_single returns an initialized SmartDevice instance."""
    host = "127.0.0.1"

    def mock_discover(self):
        self.datagram_received(
            protocol.TPLinkSmartHomeProtocol.encrypt(json_dumps(discovery_data))[4:],
            (host, custom_port or 9999),
        )

    mocker.patch.object(_DiscoverProtocol, "do_discover", mock_discover)
    mocker.patch("kasa.TPLinkSmartHomeProtocol.query", return_value=discovery_data)

    x = await Discover.discover_single(host, port=custom_port)
    assert issubclass(x.__class__, SmartDevice)
    assert x._sys_info is not None
    assert x.port == custom_port or x.port == 9999


@pytest.mark.parametrize("custom_port", [123, None])
async def test_connect_single(discovery_data: dict, mocker, custom_port):
    """Make sure that connect_single returns an initialized SmartDevice instance."""
    host = "127.0.0.1"
    mocker.patch("kasa.TPLinkSmartHomeProtocol.query", return_value=discovery_data)

    dev = await Discover.connect_single(host, port=custom_port)
    assert issubclass(dev.__class__, SmartDevice)
    assert dev.port == custom_port or dev.port == 9999


async def test_connect_single_query_fails(discovery_data: dict, mocker):
    """Make sure that connect_single fails when query fails."""
    host = "127.0.0.1"
    mocker.patch("kasa.TPLinkSmartHomeProtocol.query", side_effect=SmartDeviceException)

    with pytest.raises(SmartDeviceException):
        await Discover.connect_single(host)


UNSUPPORTED = {
    "result": {
        "device_id": "xx",
        "owner": "xx",
        "device_type": "SMART.TAPOPLUG",
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
        match=f"Unsupported device {host}: {re.escape(str(UNSUPPORTED))}",
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
    mocker.patch("kasa.discover.json_loads", return_value=discovery_data)
    mocker.patch.object(protocol.TPLinkSmartHomeProtocol, "encrypt")
    mocker.patch.object(protocol.TPLinkSmartHomeProtocol, "decrypt")

    addr = "127.0.0.1"
    proto.datagram_received("<placeholder data>", (addr, 9999))
    addr2 = "127.0.0.2"
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
