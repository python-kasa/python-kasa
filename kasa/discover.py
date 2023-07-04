"""Discovery module for TP-Link Smart Home devices."""
import asyncio
import logging
import socket
from typing import Awaitable, Callable, Dict, Optional, Type, cast

from kasa.json import dumps as json_dumps
from kasa.json import loads as json_loads
from kasa.protocolconfig import TPLinkProtocolConfig
from kasa.protocol import TPLinkProtocol
from kasa.auth import AuthCredentials, TPLinkAuthProtocol
from kasa.smartbulb import SmartBulb
from kasa.smartdevice import SmartDevice, SmartDeviceException
from kasa.smartdimmer import SmartDimmer
from kasa.smartlightstrip import SmartLightStrip
from kasa.smartplug import SmartPlug
from kasa.smartstrip import SmartStrip
from kasa.unauthenticateddevice import UnauthenticatedDevice

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
        on_discovered: Optional[OnDiscoveredCallable] = None,
        targetip: str = "255.255.255.255",
        discovery_packets: int = 3,
        interface: Optional[str] = None,
        auth_credentials: Optional[AuthCredentials] = None,
        protocol: Optional[TPLinkProtocol] = None,
    ):
        self.transport = None
        self.protocol = protocol
        self.targetip = targetip
        self.discovery_packets = discovery_packets
        self.interface = interface
        self.on_discovered = on_discovered

        self.auth_credentials = auth_credentials

        self.discovered_devices = {}

    def connection_made(self, transport) -> None:
        """Set socket options for broadcasting."""
        self.transport = transport

        sock = transport.get_extra_info("socket")
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        try:
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        except OSError as ex:  # WSL does not support SO_REUSEADDR, see #246
            _LOGGER.debug("Unable to set SO_REUSEADDR: %s", ex)

        if self.interface is not None:
            sock.setsockopt(
                socket.SOL_SOCKET, socket.SO_BINDTODEVICE, self.interface.encode()
            )

        self.do_discover()

    def do_discover(self) -> None:
        """Send number of discovery datagrams."""

        for proto_class in TPLinkProtocolConfig.enabled_protocols():
            # If a discover_single is attempted for an device requiring authentication and authentication fails
            # then it will set self.protocol and trigger a datagram discovery to get other useful info
            if self.protocol is None or isinstance(self.protocol, proto_class):
                for target in proto_class.get_discovery_targets(self.targetip):
                    payload = proto_class.get_discovery_payload()
                    _LOGGER.debug("[DISCOVERY] %s >> %s", target, payload)
                    for i in range(self.discovery_packets):
                        self.transport.sendto(payload, target)

    def datagram_received(self, data, addr) -> None:
        """Handle discovery responses."""
        ip, port = addr

        # Devices can respond multiple times due to multiple packets sent
        if ip in self.discovered_devices:
            return

        proto = info = None
        for proto_class in TPLinkProtocolConfig.enabled_protocols():
            # If a discover_single is attempted for an device requiring authentication and authentication fails
            # then it will set self.protocol and trigger a datagram discovery to get other useful info
            if self.protocol is None or isinstance(self.protocol, proto_class):
                info = proto_class.try_get_discovery_info(port, data)
                if info is not None:
                    if issubclass(proto_class, TPLinkAuthProtocol):
                        if self.protocol is None:
                            proto = proto_class(ip, self.auth_credentials)
                        else:
                            proto = self.protocol
                        proto = cast(TPLinkAuthProtocol, proto)
                        unauthenticated_device = UnauthenticatedDevice(ip, proto, info)
                        self.discovered_devices[ip] = unauthenticated_device
                        if not proto.authentication_failed:
                            unauthenticated_device.try_authenticate(
                                self._authentication_attempted_callback
                            )
                    else:
                        proto = proto_class(ip)
                        self._get_device_and_add_to_list(ip, info, proto)
                    break

    async def _authentication_attempted_callback(
        self, unauthenticated_device: UnauthenticatedDevice
    ):
        """Callback used for updating the device list once the authentication attempt is complete"""
        if unauthenticated_device.isauthenticated:
            self._get_device_and_add_to_list(
                unauthenticated_device.host,
                unauthenticated_device.wrapped_sys_info,
                unauthenticated_device.protocol,
            )
        else:
            if self.on_discovered is not None:
                asyncio.ensure_future(self.on_discovered(unauthenticated_device))

    def _get_device_and_add_to_list(self, ip, info, protocol=None):
        """Instantiates the class and adds to discovered devices"""
        try:
            device_class = Discover._get_device_class(info)
        except SmartDeviceException as ex:
            _LOGGER.debug("Unable to find device type from %s: %s", info, ex)
            return

        device = device_class(ip, protocol)
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

    The protocol uses UDP broadcast datagrams on ports configured in the protocol class (currently 9999 and 20002) for discovery.

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

    @staticmethod
    async def discover(
        *,
        targetip="255.255.255.255",
        on_discovered=None,
        timeout=5,
        discovery_packets=3,
        interface=None,
        auth_credentials=None,
        protocol=None,
    ) -> DeviceDict:
        """Discover supported devices.

        Sends discovery message to 255.255.255.255:9999 in order
        to detect available supported devices in the local network,
        and waits for given timeout for answers from devices.
        If you have multiple interfaces, you can use target parameter to specify the network for discovery.

        If given, `on_discovered` coroutine will get awaited with a :class:`SmartDevice`-derived object as parameter.

        The results of the discovery are returned as a dict of :class:`SmartDevice`-derived objects keyed with IP addresses.
        The devices are already initialized and all but emeter-related properties can be accessed directly.

        :param targetip: The target address where to send the broadcast discovery queries if multi-homing (e.g. 192.168.xxx.255).
        :param on_discovered: coroutine to execute on discovery
        :param timeout: How long to wait for responses, defaults to 5
        :param discovery_packets: Number of discovery packets to broadcast
        :param interface: Bind to specific interface
        :param protocol: Use a specific TPLinkProtol instance.  Intended to be used for getting unauthenticated device info in the case where discover_single couldn't authenticate
        :return: dictionary with discovered devices
        """
        loop = asyncio.get_event_loop()
        transport, datagram_protocol = await loop.create_datagram_endpoint(
            lambda: _DiscoverProtocol(
                targetip=targetip,
                on_discovered=on_discovered,
                discovery_packets=discovery_packets,
                interface=interface,
                auth_credentials=auth_credentials,
                protocol=protocol,
            ),
            local_addr=("0.0.0.0", 0),
        )
        datagram_protocol = cast(_DiscoverProtocol, datagram_protocol)

        try:
            _LOGGER.debug("Waiting %s seconds for responses...", timeout)
            await asyncio.sleep(timeout)
        finally:
            transport.close()

        _LOGGER.debug(
            "Discovered %s devices", len(datagram_protocol.discovered_devices)
        )

        return datagram_protocol.discovered_devices

    @staticmethod
    async def discover_single(
        host: str, auth_credentials: AuthCredentials = AuthCredentials()
    ) -> SmartDevice:
        """Discover a single device by the given IP address.

        :param host: Hostname of device to query
        :rtype: SmartDevice
        :return: Object for querying/controlling found device.
        """

        # Iterate over the enabled protocols and return a device for that protocol
        for proto_class in TPLinkProtocolConfig.enabled_protocols():
            is_auth_proto = issubclass(proto_class, TPLinkAuthProtocol)
            if is_auth_proto:
                proto = proto_class(host, auth_credentials)
            else:
                proto = proto_class(host)

            # try and do a discovery query starting with the older protocol.  None is returned if not succesful
            info = await proto.try_query_discovery_info()

            if info is not None:
                device_class = Discover._get_device_class(info)
                dev = device_class(host, proto)
                await dev.update()

                return dev
            elif is_auth_proto and proto.authentication_failed:
                found_devs = await Discover.discover(targetip=host, protocol=proto)
                if host in found_devs:
                    return found_devs[host]

        _LOGGER.info("Unable to query discovery info for host %s", host)

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
