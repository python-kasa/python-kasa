"""Discovery module for TP-Link Smart Home devices."""
import asyncio
import json
import logging
import socket
from typing import Awaitable, Callable, Dict, Optional, Type, cast

from kasa.protocol import TPLinkSmartHomeProtocol
from kasa.smartbulb import SmartBulb
from kasa.smartdevice import SmartDevice, SmartDeviceException
from kasa.smartdimmer import SmartDimmer
from kasa.smartlightstrip import SmartLightStrip
from kasa.smartplug import SmartPlug
from kasa.smartstrip import SmartStrip

_LOGGER = logging.getLogger(__name__)


OnDiscoveredCallable = Callable[[SmartDevice], Awaitable[None]]
DeviceDict = Dict[str, SmartDevice]


class _DiscoverProtocol(asyncio.DatagramProtocol):
    """Implementation of the discovery protocol handler.

    This is internal class, use :func:`Discover.discover`: instead.
    """

    discovered_devices: DeviceDict

    def __init__(
        self,
        *,
        on_discovered: OnDiscoveredCallable = None,
        target: str = "255.255.255.255",
        discovery_packets: int = 3,
        interface: Optional[str] = None,
    ):
        self.transport = None
        self.discovery_packets = discovery_packets
        self.interface = interface
        self.on_discovered = on_discovered
        self.target = (target, Discover.DISCOVERY_PORT)
        self.discovered_devices = {}

    def connection_made(self, transport) -> None:
        """Set socket options for broadcasting."""
        self.transport = transport
        sock = transport.get_extra_info("socket")
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        if self.interface is not None:
            sock.setsockopt(
                socket.SOL_SOCKET, socket.SO_BINDTODEVICE, self.interface.encode()
            )

        self.do_discover()

    def do_discover(self) -> None:
        """Send number of discovery datagrams."""
        req = json.dumps(Discover.DISCOVERY_QUERY)
        _LOGGER.debug("[DISCOVERY] %s >> %s", self.target, Discover.DISCOVERY_QUERY)
        encrypted_req = TPLinkSmartHomeProtocol.encrypt(req)
        for i in range(self.discovery_packets):
            self.transport.sendto(encrypted_req[4:], self.target)  # type: ignore

    def datagram_received(self, data, addr) -> None:
        """Handle discovery responses."""
        ip, port = addr
        if ip in self.discovered_devices:
            return

        info = json.loads(TPLinkSmartHomeProtocol.decrypt(data))
        _LOGGER.debug("[DISCOVERY] %s << %s", ip, info)

        device_class = Discover._get_device_class(info)
        device = device_class(ip)
        device.update_from_discover_info(info)

        self.discovered_devices[ip] = device

        if self.on_discovered is not None:
            asyncio.ensure_future(self.on_discovered(device))

    def error_received(self, ex):
        """Handle asyncio.Protocol errors."""
        _LOGGER.error("Got error: %s", ex)

    def connection_lost(self, ex):
        """NOP implementation of connection lost."""


class Discover:
    """Discover TPLink Smart Home devices.

    The main entry point for this library is :func:`Discover.discover()`,
    which returns a dictionary of the found devices. The key is the IP address
    of the device and the value contains ready-to-use, SmartDevice-derived
    device object.

    :func:`discover_single()` can be used to initialize a single device given its
    IP address. If the type of the device and its IP address is already known,
    you can initialize the corresponding device class directly without this.

    The protocol uses UDP broadcast datagrams on port 9999 for discovery.

    Examples:
        Discovery returns a list of discovered devices:

        >>> import asyncio
        >>> found_devices = asyncio.run(Discover.discover())
        >>> [dev.alias for dev in found_devices]
        ['TP-LINK_Power Strip_CF69']

        Discovery can also be targeted to a specific broadcast address instead of the 255.255.255.255:

        >>> asyncio.run(Discover.discover(target="192.168.8.255"))

        It is also possible to pass a coroutine to be executed for each found device:

        >>> async def print_alias(dev):
        >>>    print(f"Discovered {dev.alias}")
        >>> devices = asyncio.run(Discover.discover(on_discovered=print_alias))


    """

    DISCOVERY_PORT = 9999

    DISCOVERY_QUERY = {
        "system": {"get_sysinfo": None},
    }

    @staticmethod
    async def discover(
        *,
        target="255.255.255.255",
        on_discovered=None,
        timeout=5,
        discovery_packets=3,
        interface=None,
    ) -> DeviceDict:
        """Discover supported devices.

        Sends discovery message to 255.255.255.255:9999 in order
        to detect available supported devices in the local network,
        and waits for given timeout for answers from devices.
        If you have multiple interfaces, you can use target parameter to specify the network for discovery.

        If given, `on_discovered` coroutine will get awaited with a :class:`SmartDevice`-derived object as parameter.

        The results of the discovery are returned as a dict of :class:`SmartDevice`-derived objects keyed with IP addresses.
        The devices are already initialized and all but emeter-related properties can be accessed directly.

        :param target: The target address where to send the broadcast discovery queries if multi-homing (e.g. 192.168.xxx.255).
        :param on_discovered: coroutine to execute on discovery
        :param timeout: How long to wait for responses, defaults to 5
        :param discovery_packets: Number of discovery packets to broadcast
        :param interface: Bind to specific interface
        :return: dictionary with discovered devices
        """
        loop = asyncio.get_event_loop()
        transport, protocol = await loop.create_datagram_endpoint(
            lambda: _DiscoverProtocol(
                target=target,
                on_discovered=on_discovered,
                discovery_packets=discovery_packets,
                interface=interface,
            ),
            local_addr=("0.0.0.0", 0),
        )
        protocol = cast(_DiscoverProtocol, protocol)

        try:
            _LOGGER.debug("Waiting %s seconds for responses...", timeout)
            await asyncio.sleep(timeout)
        finally:
            transport.close()

        _LOGGER.debug("Discovered %s devices", len(protocol.discovered_devices))

        return protocol.discovered_devices

    @staticmethod
    async def discover_single(host: str) -> SmartDevice:
        """Discover a single device by the given IP address.

        :param host: Hostname of device to query
        :rtype: SmartDevice
        :return: Object for querying/controlling found device.
        """
        protocol = TPLinkSmartHomeProtocol(host)

        info = await protocol.query(Discover.DISCOVERY_QUERY)

        device_class = Discover._get_device_class(info)
        dev = device_class(host)
        await dev.update()

        return dev

    @staticmethod
    def _get_device_class(info: dict) -> Type[SmartDevice]:
        """Find SmartDevice subclass for device described by passed data."""
        if "system" not in info or "get_sysinfo" not in info["system"]:
            raise SmartDeviceException("No 'system' or 'get_sysinfo' in response")

        sysinfo = info["system"]["get_sysinfo"]
        type_ = sysinfo.get("type", sysinfo.get("mic_type"))
        if type_ is None:
            raise SmartDeviceException("Unable to find the device type field!")

        if "dev_name" in sysinfo and "Dimmer" in sysinfo["dev_name"]:
            return SmartDimmer

        if "smartplug" in type_.lower():
            if "children" in sysinfo:
                return SmartStrip

            return SmartPlug

        if "smartbulb" in type_.lower():
            if "length" in sysinfo:  # strips have length
                return SmartLightStrip

            return SmartBulb

        raise SmartDeviceException("Unknown device type: %s" % type_)
