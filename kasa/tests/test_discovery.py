# type: ignore
import sys

import pytest  # type: ignore # https://github.com/pytest-dev/pytest/issues/3342

from kasa import DeviceType, Discover, SmartDevice, SmartDeviceException, protocol
from kasa.discover import _DiscoverProtocol

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


async def test_discover_single(discovery_data: dict, mocker):
    """Make sure that discover_single returns an initialized SmartDevice instance."""
    mocker.patch("kasa.TPLinkSmartHomeProtocol.query", return_value=discovery_data)
    x = await Discover.discover_single("127.0.0.1")
    assert issubclass(x.__class__, SmartDevice)
    assert x._sys_info is not None


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
    mocker.patch("kasa.TPLinkSmartHomeProtocol.query", return_value=data)
    with pytest.raises(SmartDeviceException, match=msg):
        await Discover.discover_single("127.0.0.1")


async def test_discover_send(mocker):
    """Test discovery parameters."""
    proto = _DiscoverProtocol()
    assert proto.discovery_packets == 3
    assert proto.target == ("255.255.255.255", 9999)
    transport = mocker.patch.object(proto, "transport")
    proto.do_discover()
    assert transport.sendto.call_count == proto.discovery_packets


async def test_discover_datagram_received(mocker, discovery_data):
    """Verify that datagram received fills discovered_devices."""
    proto = _DiscoverProtocol()
    mocker.patch("kasa.json_loads", return_value=discovery_data)
    mocker.patch.object(protocol.TPLinkSmartHomeProtocol, "encrypt")
    mocker.patch.object(protocol.TPLinkSmartHomeProtocol, "decrypt")

    addr = "127.0.0.1"
    proto.datagram_received("<placeholder data>", (addr, 1234))

    # Check that device in discovered_devices is initialized correctly
    assert len(proto.discovered_devices) == 1
    dev = proto.discovered_devices[addr]
    assert issubclass(dev.__class__, SmartDevice)
    assert dev.host == addr


@pytest.mark.parametrize("msg, data", INVALIDS)
async def test_discover_invalid_responses(msg, data, mocker):
    """Verify that we don't crash whole discovery if some devices in the network are sending unexpected data."""
    proto = _DiscoverProtocol()
    mocker.patch("kasa.json_loads", return_value=data)
    mocker.patch.object(protocol.TPLinkSmartHomeProtocol, "encrypt")
    mocker.patch.object(protocol.TPLinkSmartHomeProtocol, "decrypt")

    proto.datagram_received(data, ("127.0.0.1", 1234))
    assert len(proto.discovered_devices) == 0
