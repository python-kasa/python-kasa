"""Discovery module for TP-Link Smart Home devices."""
import asyncio
import binascii
import ipaddress
import logging
import socket
from typing import Awaitable, Callable, Dict, Optional, Set, Type, cast

# When support for cpython older than 3.11 is dropped
# async_timeout can be replaced with asyncio.timeout
from async_timeout import timeout as asyncio_timeout

try:
    from pydantic.v1 import BaseModel, Field
except ImportError:
    from pydantic import BaseModel, Field

from kasa.credentials import Credentials
from kasa.exceptions import UnsupportedDeviceException
from kasa.json import dumps as json_dumps
from kasa.json import loads as json_loads
from kasa.klapprotocol import TPLinkKlap
from kasa.protocol import TPLinkSmartHomeProtocol
from kasa.smartdevice import SmartDevice, SmartDeviceException
from kasa.smartplug import SmartPlug

from .device_factory import get_device_class_from_info

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
        target: str = "255.255.255.255",
        discovery_packets: int = 3,
        interface: Optional[str] = None,
        on_unsupported: Optional[Callable[[str], Awaitable[None]]] = None,
        port: Optional[int] = None,
        discovered_event: Optional[asyncio.Event] = None,
        credentials: Optional[Credentials] = None,
        timeout: Optional[int] = None,
    ) -> None:
        self.transport = None
        self.discovery_packets = discovery_packets
        self.interface = interface
        self.on_discovered = on_discovered
        self.discovery_port = port or Discover.DISCOVERY_PORT
        self.target = (target, self.discovery_port)
        self.target_2 = (target, Discover.DISCOVERY_PORT_2)
        self.discovered_devices = {}
        self.unsupported_devices: Dict = {}
        self.invalid_device_exceptions: Dict = {}
        self.on_unsupported = on_unsupported
        self.discovered_event = discovered_event
        self.credentials = credentials
        self.timeout = timeout
        self.seen_hosts: Set[str] = set()

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
        req = json_dumps(Discover.DISCOVERY_QUERY)
        _LOGGER.debug("[DISCOVERY] %s >> %s", self.target, Discover.DISCOVERY_QUERY)
        encrypted_req = TPLinkSmartHomeProtocol.encrypt(req)
        for _i in range(self.discovery_packets):
            self.transport.sendto(encrypted_req[4:], self.target)  # type: ignore
            self.transport.sendto(Discover.DISCOVERY_QUERY_2, self.target_2)  # type: ignore

    def datagram_received(self, data, addr) -> None:
        """Handle discovery responses."""
        ip, port = addr
        # Prevent multiple entries due multiple broadcasts
        if ip in self.seen_hosts:
            return
        self.seen_hosts.add(ip)

        device = None
        try:
            if port == self.discovery_port:
                device = Discover._get_device_instance_legacy(data, ip, port)
            elif port == Discover.DISCOVERY_PORT_2:
                device = Discover._get_device_instance(
                    data, ip, port, self.credentials or Credentials()
                )
            else:
                return
        except UnsupportedDeviceException as udex:
            _LOGGER.debug("Unsupported device found at %s << %s", ip, udex)
            self.unsupported_devices[ip] = str(udex)
            if self.on_unsupported is not None:
                asyncio.ensure_future(self.on_unsupported(str(udex)))
            if self.discovered_event is not None:
                self.discovered_event.set()
            return
        except SmartDeviceException as ex:
            _LOGGER.debug(f"[DISCOVERY] Unable to find device type for {ip}: {ex}")
            self.invalid_device_exceptions[ip] = ex
            if self.discovered_event is not None:
                self.discovered_event.set()
            return

        self.discovered_devices[ip] = device

        if self.on_discovered is not None:
            asyncio.ensure_future(self.on_discovered(device))

        if self.discovered_event is not None:
            self.discovered_event.set()

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

        Discovery can also be targeted to a specific broadcast address instead of
        the default 255.255.255.255:

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

    DISCOVERY_PORT_2 = 20002
    DISCOVERY_QUERY_2 = binascii.unhexlify("020000010000000000000000463cb5d3")

    @staticmethod
    async def discover(
        *,
        target="255.255.255.255",
        on_discovered=None,
        timeout=5,
        discovery_packets=3,
        interface=None,
        on_unsupported=None,
        credentials=None,
    ) -> DeviceDict:
        """Discover supported devices.

        Sends discovery message to 255.255.255.255:9999 in order
        to detect available supported devices in the local network,
        and waits for given timeout for answers from devices.
        If you have multiple interfaces,
        you can use *target* parameter to specify the network for discovery.

        If given, `on_discovered` coroutine will get awaited with
        a :class:`SmartDevice`-derived object as parameter.

        The results of the discovery are returned as a dict of
        :class:`SmartDevice`-derived objects keyed with IP addresses.
        The devices are already initialized and all but emeter-related properties
        can be accessed directly.

        :param target: The target address where to send the broadcast discovery
         queries if multi-homing (e.g. 192.168.xxx.255).
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
                on_unsupported=on_unsupported,
                credentials=credentials,
                timeout=timeout,
            ),
            local_addr=("0.0.0.0", 0),  # noqa: S104
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
    async def discover_single(
        host: str,
        *,
        port: Optional[int] = None,
        timeout=5,
        credentials: Optional[Credentials] = None,
        update_parent_devices: bool = True,
    ) -> SmartDevice:
        """Discover a single device by the given IP address.

        It is generally preferred to avoid :func:`discover_single()` and
        use :func:`connect_single()` instead as it should perform better when
        the WiFi network is congested or the device is not responding
        to discovery requests.

        :param host: Hostname of device to query
        :param port: Optionally set a different port for the device
        :param timeout: Timeout for discovery
        :param credentials: Credentials for devices that require authentication
        :param update_parent_devices: Automatically call device.update() on
            devices that have children
        :rtype: SmartDevice
        :return: Object for querying/controlling found device.
        """
        loop = asyncio.get_event_loop()
        event = asyncio.Event()

        try:
            ipaddress.ip_address(host)
            ip = host
        except ValueError:
            try:
                adrrinfo = await loop.getaddrinfo(
                    host,
                    0,
                    type=socket.SOCK_DGRAM,
                    family=socket.AF_INET,
                )
                # getaddrinfo returns a list of 5 tuples with the following structure:
                # (family, type, proto, canonname, sockaddr)
                # where sockaddr is 2 tuple (ip, port).
                # hence [0][4][0] is a stable array access because if no socket
                # address matches the host for SOCK_DGRAM AF_INET the gaierror
                # would be raised.
                # https://docs.python.org/3/library/socket.html#socket.getaddrinfo
                ip = adrrinfo[0][4][0]
            except socket.gaierror as gex:
                raise SmartDeviceException(
                    f"Could not resolve hostname {host}"
                ) from gex

        transport, protocol = await loop.create_datagram_endpoint(
            lambda: _DiscoverProtocol(
                target=ip,
                port=port,
                discovered_event=event,
                credentials=credentials,
                timeout=timeout,
            ),
            local_addr=("0.0.0.0", 0),  # noqa: S104
        )
        protocol = cast(_DiscoverProtocol, protocol)

        try:
            _LOGGER.debug("Waiting a total of %s seconds for responses...", timeout)

            async with asyncio_timeout(timeout):
                await event.wait()
        except asyncio.TimeoutError as ex:
            raise SmartDeviceException(
                f"Timed out getting discovery response for {host}"
            ) from ex
        finally:
            transport.close()

        if ip in protocol.discovered_devices:
            dev = protocol.discovered_devices[ip]
            dev.host = host
            # Call device update on devices that have children
            if update_parent_devices and dev.has_children:
                await dev.update()
            return dev
        elif ip in protocol.unsupported_devices:
            raise UnsupportedDeviceException(
                f"Unsupported device {host}: {protocol.unsupported_devices[ip]}"
            )
        elif ip in protocol.invalid_device_exceptions:
            raise protocol.invalid_device_exceptions[ip]
        else:
            raise SmartDeviceException(f"Unable to get discovery response for {host}")

    @staticmethod
    def _get_device_class(info: dict) -> Type[SmartDevice]:
        """Find SmartDevice subclass for device described by passed data."""
        return get_device_class_from_info(info)

    @staticmethod
    def _get_device_instance_legacy(data: bytes, ip: str, port: int) -> SmartDevice:
        """Get SmartDevice from legacy 9999 response."""
        try:
            info = json_loads(TPLinkSmartHomeProtocol.decrypt(data))
        except Exception as ex:
            raise SmartDeviceException(
                f"Unable to read response from device: {ip}: {ex}"
            ) from ex

        _LOGGER.debug("[DISCOVERY] %s << %s", ip, info)

        device_class = Discover._get_device_class(info)
        device = device_class(ip, port=port)
        device.update_from_discover_info(info)
        return device

    @staticmethod
    def _get_device_instance(
        data: bytes, ip: str, port: int, credentials: Credentials
    ) -> SmartDevice:
        """Get SmartDevice from the new 20002 response."""
        try:
            info = json_loads(data[16:])
            discovery_result = DiscoveryResult(**info["result"])
        except Exception as ex:
            raise UnsupportedDeviceException(
                f"Unable to read response from device: {ip}: {ex}"
            ) from ex

        if (
            discovery_result.mgt_encrypt_schm.encrypt_type == "KLAP"
            and discovery_result.mgt_encrypt_schm.lv is None
        ):
            type_ = discovery_result.device_type
            device_class = None
            if type_.upper() == "IOT.SMARTPLUGSWITCH":
                device_class = SmartPlug

            if device_class:
                _LOGGER.debug("[DISCOVERY] %s << %s", ip, info)
                device = device_class(ip, port=port, credentials=credentials)
                device.update_from_discover_info(discovery_result.get_dict())
                device.protocol = TPLinkKlap(ip, credentials=credentials)
                return device
            else:
                raise UnsupportedDeviceException(
                    f"Unsupported device {ip} of type {type_}: {info}"
                )
        else:
            raise UnsupportedDeviceException(f"Unsupported device {ip}: {info}")


class DiscoveryResult(BaseModel):
    """Base model for discovery result."""

    class Config:
        """Class for configuring model behaviour."""

        allow_population_by_field_name = True

    class EncryptionScheme(BaseModel):
        """Base model for encryption scheme of discovery result."""

        is_support_https: Optional[bool] = None
        encrypt_type: Optional[str] = None
        http_port: Optional[int] = None
        lv: Optional[int] = None

    device_type: str = Field(alias="device_type_text")
    device_model: str = Field(alias="model")
    ip: str = Field(alias="alias")
    mac: str
    mgt_encrypt_schm: EncryptionScheme

    device_id: Optional[str] = Field(default=None, alias="device_id_hash")
    owner: Optional[str] = Field(default=None, alias="device_owner_hash")
    hw_ver: Optional[str] = None
    is_support_iot_cloud: Optional[bool] = None
    obd_src: Optional[str] = None
    factory_default: Optional[bool] = None

    def get_dict(self) -> dict:
        """Return a dict for this discovery result.

        containing only the values actually set and with aliases as field names.
        """
        return self.dict(
            by_alias=True, exclude_unset=True, exclude_none=True, exclude_defaults=True
        )
