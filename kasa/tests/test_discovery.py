# type: ignore
import sys

import pytest  # type: ignore # https://github.com/pytest-dev/pytest/issues/3342

from kasa import DeviceType, Discover, SmartDevice, UnauthenticatedDevice, SmartDeviceException, protocol, klapprotocol, protocolconfig, auth
from kasa.discover import _DiscoverProtocol
from kasa.json import dumps as json_dumps
from kasa.json import loads as json_loads

from .conftest import bulb, dimmer, lightstrip, plug, strip
import asyncio



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

    
    # Succesful klap discovery
    mocker.patch("kasa.TPLinkSmartHomeProtocol.try_query_discovery_info", return_value=None)
    mocker.patch("kasa.klapprotocol.TPLinkKlap.query", return_value=discovery_data)
    x = await Discover.discover_single("127.0.0.1")
    assert issubclass(x.__class__, SmartDevice)
    assert x._sys_info is not None
    
    #  Unauthenticated klap discovery
    klap_result = get_klap_datagram_data("127.0.0.1")
    found_devs = {"127.0.0.1": UnauthenticatedDevice("127.0.0.1", klapprotocol.TPLinkKlap(host="127.0.0.1"), klap_result)}
    mocker.patch("kasa.TPLinkSmartHomeProtocol.try_query_discovery_info", return_value=None)
    mocker.patch("kasa.TPLinkKlap.query", return_value=None)
    mocker.patch("kasa.TPLinkKlap.authentication_failed", return_value=True)
    mocker.patch("kasa.Discover.discover", return_value=found_devs)
    x = await Discover.discover_single("127.0.0.1")
    assert isinstance(x, UnauthenticatedDevice)
    assert x.unauthenticated_info is not None


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
    assert protocolconfig.TPLinkProtocolConfig.enabled_protocols()[0] == protocol.TPLinkSmartHomeProtocol
    assert protocolconfig.TPLinkProtocolConfig.enabled_protocols()[1] == klapprotocol.TPLinkKlap
    assert protocol.TPLinkSmartHomeProtocol.get_discovery_targets() == [("255.255.255.255", 9999)]
    assert klapprotocol.TPLinkKlap.get_discovery_targets() == [("255.255.255.255", 20002)]
    assert protocol.TPLinkSmartHomeProtocol.get_discovery_targets("192.168.255.255") == [("192.168.255.255", 9999)]
    assert klapprotocol.TPLinkKlap.get_discovery_targets("192.168.255.255") == [("192.168.255.255", 20002)]

    transport = mocker.patch.object(proto, "transport")

    proto.do_discover()
    
    assert transport.sendto.call_count == proto.discovery_packets * 2


def get_klap_datagram_data(host):
    klap_result = {"result": {"ip": host, 
                "mac": "12-34-56-78-9A-BC", 
                "device_id": "00000000000000000000000000000000", 
                "owner": "11111111111111111111111111111111", 
                "device_type": "IOT.SMARTPLUGSWITCH", 
                "device_model": "HS100(UK)", 
                "hw_ver": "4.1", 
                "factory_default": True, 
                "mgt_encrypt_schm": {"is_support_https": False, "encrypt_type": "KLAP", "http_port": 80}, 
                "error_code": 0}
    }
    klap_result = b'0123456789ABCDEF' + json_dumps(klap_result).encode()
    return klap_result

async def test_discover_datagram_received(mocker, discovery_data):
    """Verify that datagram received fills discovered_devices."""

    addr1 = "127.0.0.1"
    addr2 = "127.0.0.2"
    addr3 = "127.0.0.3"
    
    proto = _DiscoverProtocol()
    mocker.patch("kasa.protocol.json_loads", return_value=discovery_data)
    mocker.patch.object(protocol.TPLinkSmartHomeProtocol, "encrypt")
    mocker.patch.object(protocol.TPLinkSmartHomeProtocol, "decrypt")
    mocker.patch("kasa.klapprotocol.TPLinkKlap.try_query_discovery_info", return_value=discovery_data)

    # TPLinkSmartHomeProtocol received
    proto.datagram_received("<Placeholder data>", (addr1, protocol.TPLinkSmartHomeProtocol.DEFAULT_PORT))

    # Succesful TPLinkKlap received
    proto.datagram_received(get_klap_datagram_data(addr2), (addr2, klapprotocol.TPLinkKlap.DISCOVERY_PORT))
    # Let the authentication callback run
    await asyncio.sleep(0.01)

    # Simulate TPLinkKlap unable to authenticate
    mocker.patch("kasa.klapprotocol.TPLinkKlap.try_query_discovery_info", return_value=None)
    proto.datagram_received(get_klap_datagram_data(addr3), (addr3, klapprotocol.TPLinkKlap.DISCOVERY_PORT))
    # Let the authentication callback run
    await asyncio.sleep(0.01)

    # Check that device in discovered_devices is initialized correctly
    assert len(proto.discovered_devices) == 3
    dev = proto.discovered_devices[addr1]
    assert issubclass(dev.__class__, SmartDevice)
    assert dev.host == addr1

    dev = proto.discovered_devices[addr2]
    assert issubclass(dev.__class__, SmartDevice) and not isinstance(dev, UnauthenticatedDevice)
    assert dev.host == addr2

    dev = proto.discovered_devices[addr3]
    assert isinstance(dev, UnauthenticatedDevice)
    assert dev.host == addr3


@pytest.mark.parametrize("msg, data", INVALIDS)
async def test_discover_invalid_responses(msg, data, mocker):
    """Verify that we don't crash whole discovery if some devices in the network are sending unexpected data."""
    proto = _DiscoverProtocol()
    mocker.patch("kasa.discover.json_loads", return_value=data)
    mocker.patch.object(protocol.TPLinkSmartHomeProtocol, "encrypt")
    mocker.patch.object(protocol.TPLinkSmartHomeProtocol, "decrypt")

    proto.datagram_received(data, ("127.0.0.1", 1234))
    assert len(proto.discovered_devices) == 0
