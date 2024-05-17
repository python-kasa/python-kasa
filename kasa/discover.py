"""Discovery module for TP-Link Smart Home devices."""

from __future__ import annotations

import asyncio
import binascii
import ipaddress
import logging
import socket
from typing import Awaitable, Callable, Dict, Optional, Type, cast

# When support for cpython older than 3.11 is dropped
# async_timeout can be replaced with asyncio.timeout
from async_timeout import timeout as asyncio_timeout
from pydantic.v1 import BaseModel, ValidationError

from kasa import Device
from kasa.credentials import Credentials
from kasa.device_factory import (
    get_device_class_from_family,
    get_device_class_from_sys_info,
    get_protocol,
)
from kasa.deviceconfig import ConnectionType, DeviceConfig, EncryptType
from kasa.exceptions import (
    KasaException,
    TimeoutError,
    UnsupportedDeviceError,
)
from kasa.iot.iotdevice import IotDevice
from kasa.json import dumps as json_dumps
from kasa.json import loads as json_loads
from kasa.xortransport import XorEncryption

_LOGGER = logging.getLogger(__name__)


OnDiscoveredCallable = Callable[[Device], Awaitable[None]]
OnUnsupportedCallable = Callable[[UnsupportedDeviceError], Awaitable[None]]
DeviceDict = Dict[str, Device]


class _DiscoverProtocol(asyncio.DatagramProtocol):
    """Implementation of the discovery protocol handler.

    This is internal class, use :func:`Discover.discover`: instead.
    """

    DISCOVERY_START_TIMEOUT = 1

    discovered_devices: DeviceDict

    def __init__(
        self,
        *,
        on_discovered: OnDiscoveredCallable | None = None,
        target: str = "255.255.255.255",
        discovery_packets: int = 3,
        discovery_timeout: int = 5,
        interface: str | None = None,
        on_unsupported: OnUnsupportedCallable | None = None,
        port: int | None = None,
        credentials: Credentials | None = None,
        timeout: int | None = None,
    ) -> None:
        self.transport = None
        self.discovery_packets = discovery_packets
        self.interface = interface
        self.on_discovered = on_discovered

        self.port = port
        self.discovery_port = port or Discover.DISCOVERY_PORT
        self.target = target
        self.target_1 = (target, self.discovery_port)
        self.target_2 = (target, Discover.DISCOVERY_PORT_2)

        self.discovered_devices = {}
        self.unsupported_device_exceptions: dict = {}
        self.invalid_device_exceptions: dict = {}
        self.on_unsupported = on_unsupported
        self.credentials = credentials
        self.timeout = timeout
        self.discovery_timeout = discovery_timeout
        self.seen_hosts: set[str] = set()
        self.discover_task: asyncio.Task | None = None
        self.callback_tasks: list[asyncio.Task] = []
        self.target_discovered: bool = False
        self._started_event = asyncio.Event()

    def _run_callback_task(self, coro):
        task = asyncio.create_task(coro)
        self.callback_tasks.append(task)

    async def wait_for_discovery_to_complete(self):
        """Wait for the discovery task to complete."""
        # Give some time for connection_made event to be received
        async with asyncio_timeout(self.DISCOVERY_START_TIMEOUT):
            await self._started_event.wait()
        try:
            await self.discover_task
        except asyncio.CancelledError:
            # if target_discovered then cancel was called internally
            if not self.target_discovered:
                raise
        # Wait for any pending callbacks to complete
        await asyncio.gather(*self.callback_tasks)

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

        self.discover_task = asyncio.create_task(self.do_discover())
        self._started_event.set()

    async def do_discover(self) -> None:
        """Send number of discovery datagrams."""
        req = json_dumps(Discover.DISCOVERY_QUERY)
        _LOGGER.debug("[DISCOVERY] %s >> %s", self.target, Discover.DISCOVERY_QUERY)
        encrypted_req = XorEncryption.encrypt(req)
        sleep_between_packets = self.discovery_timeout / self.discovery_packets
        for _ in range(self.discovery_packets):
            if self.target in self.seen_hosts:  # Stop sending for discover_single
                break
            self.transport.sendto(encrypted_req[4:], self.target_1)  # type: ignore
            self.transport.sendto(Discover.DISCOVERY_QUERY_2, self.target_2)  # type: ignore
            await asyncio.sleep(sleep_between_packets)

    def datagram_received(self, data, addr) -> None:
        """Handle discovery responses."""
        ip, port = addr
        # Prevent multiple entries due multiple broadcasts
        if ip in self.seen_hosts:
            return
        self.seen_hosts.add(ip)

        device: Device | None = None

        config = DeviceConfig(host=ip, port_override=self.port)
        if self.credentials:
            config.credentials = self.credentials
        if self.timeout:
            config.timeout = self.timeout
        try:
            if port == self.discovery_port:
                device = Discover._get_device_instance_legacy(data, config)
            elif port == Discover.DISCOVERY_PORT_2:
                config.uses_http = True
                device = Discover._get_device_instance(data, config)
            else:
                return
        except UnsupportedDeviceError as udex:
            _LOGGER.debug("Unsupported device found at %s << %s", ip, udex)
            self.unsupported_device_exceptions[ip] = udex
            if self.on_unsupported is not None:
                self._run_callback_task(self.on_unsupported(udex))
            self._handle_discovered_event()
            return
        except KasaException as ex:
            _LOGGER.debug(f"[DISCOVERY] Unable to find device type for {ip}: {ex}")
            self.invalid_device_exceptions[ip] = ex
            self._handle_discovered_event()
            return

        self.discovered_devices[ip] = device

        if self.on_discovered is not None:
            self._run_callback_task(self.on_discovered(device))

        self._handle_discovered_event()

    def _handle_discovered_event(self):
        """If target is in seen_hosts cancel discover_task."""
        if self.target in self.seen_hosts:
            self.target_discovered = True
            if self.discover_task:
                self.discover_task.cancel()

    def error_received(self, ex):
        """Handle asyncio.Protocol errors."""
        _LOGGER.error("Got error: %s", ex)

    def connection_lost(self, ex):  # pragma: no cover
        """Cancel the discover task if running."""
        if self.discover_task:
            self.discover_task.cancel()


class Discover:
    """Discover TPLink Smart Home devices.

    The main entry point for this library is :func:`Discover.discover()`,
    which returns a dictionary of the found devices. The key is the IP address
    of the device and the value contains ready-to-use, SmartDevice-derived
    device object.

    :func:`discover_single()` can be used to initialize a single device given its
    IP address. If the :class:`DeviceConfig` of the device is already known,
    you can initialize the corresponding device class directly without discovery.

    The protocol uses UDP broadcast datagrams on port 9999 and 20002 for discovery.
    Legacy devices support discovery on port 9999 and newer devices on 20002.

    Newer devices that respond on port 20002 will most likely require TP-Link cloud
    credentials to be passed if queries or updates are to be performed on the returned
    devices.

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
        discovery_timeout=5,
        discovery_packets=3,
        interface=None,
        on_unsupported=None,
        credentials=None,
        port=None,
        timeout=None,
    ) -> DeviceDict:
        """Discover supported devices.

        Sends discovery message to 255.255.255.255:9999 and
        255.255.255.255:20002 in order
        to detect available supported devices in the local network,
        and waits for given timeout for answers from devices.
        If you have multiple interfaces,
        you can use *target* parameter to specify the network for discovery.

        If given, `on_discovered` coroutine will get awaited with
        a :class:`Device`-derived object as parameter.

        The results of the discovery are returned as a dict of
        :class:`Device`-derived objects keyed with IP addresses.
        The devices are already initialized and all but emeter-related properties
        can be accessed directly.

        :param target: The target address where to send the broadcast discovery
         queries if multi-homing (e.g. 192.168.xxx.255).
        :param on_discovered: coroutine to execute on discovery
        :param discovery_timeout: Seconds to wait for responses, defaults to 5
        :param discovery_packets: Number of discovery packets to broadcast
        :param interface: Bind to specific interface
        :param on_unsupported: Optional callback when unsupported devices are discovered
        :param credentials: Credentials for devices requiring authentication
        :param port: Override the discovery port for devices listening on 9999
        :param timeout: Query timeout in seconds for devices returned by discovery
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
                discovery_timeout=discovery_timeout,
                port=port,
            ),
            local_addr=("0.0.0.0", 0),  # noqa: S104
        )
        protocol = cast(_DiscoverProtocol, protocol)

        try:
            _LOGGER.debug("Waiting %s seconds for responses...", discovery_timeout)
            await protocol.wait_for_discovery_to_complete()
        except KasaException as ex:
            for device in protocol.discovered_devices.values():
                await device.protocol.close()
            raise ex
        finally:
            transport.close()

        _LOGGER.debug("Discovered %s devices", len(protocol.discovered_devices))

        return protocol.discovered_devices

    @staticmethod
    async def discover_single(
        host: str,
        *,
        discovery_timeout: int = 5,
        port: int | None = None,
        timeout: int | None = None,
        credentials: Credentials | None = None,
    ) -> Device:
        """Discover a single device by the given IP address.

        It is generally preferred to avoid :func:`discover_single()` and
        use :meth:`Device.connect()` instead as it should perform better when
        the WiFi network is congested or the device is not responding
        to discovery requests.

        :param host: Hostname of device to query
        :param discovery_timeout: Timeout in seconds for discovery
        :param port: Optionally set a different port for legacy devices using port 9999
        :param timeout: Timeout in seconds device for devices queries
        :param credentials: Credentials for devices that require authentication
        :rtype: SmartDevice
        :return: Object for querying/controlling found device.
        """
        loop = asyncio.get_event_loop()

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
                raise KasaException(f"Could not resolve hostname {host}") from gex

        transport, protocol = await loop.create_datagram_endpoint(
            lambda: _DiscoverProtocol(
                target=ip,
                port=port,
                credentials=credentials,
                timeout=timeout,
                discovery_timeout=discovery_timeout,
            ),
            local_addr=("0.0.0.0", 0),  # noqa: S104
        )
        protocol = cast(_DiscoverProtocol, protocol)

        try:
            _LOGGER.debug(
                "Waiting a total of %s seconds for responses...", discovery_timeout
            )
            await protocol.wait_for_discovery_to_complete()
        finally:
            transport.close()

        if ip in protocol.discovered_devices:
            dev = protocol.discovered_devices[ip]
            dev.host = host
            return dev
        elif ip in protocol.unsupported_device_exceptions:
            raise protocol.unsupported_device_exceptions[ip]
        elif ip in protocol.invalid_device_exceptions:
            raise protocol.invalid_device_exceptions[ip]
        else:
            raise TimeoutError(f"Timed out getting discovery response for {host}")

    @staticmethod
    def _get_device_class(info: dict) -> type[Device]:
        """Find SmartDevice subclass for device described by passed data."""
        if "result" in info:
            discovery_result = DiscoveryResult(**info["result"])
            dev_class = get_device_class_from_family(discovery_result.device_type)
            if not dev_class:
                raise UnsupportedDeviceError(
                    "Unknown device type: %s" % discovery_result.device_type,
                    discovery_result=info,
                )
            return dev_class
        else:
            return get_device_class_from_sys_info(info)

    @staticmethod
    def _get_device_instance_legacy(data: bytes, config: DeviceConfig) -> IotDevice:
        """Get SmartDevice from legacy 9999 response."""
        try:
            info = json_loads(XorEncryption.decrypt(data))
        except Exception as ex:
            raise KasaException(
                f"Unable to read response from device: {config.host}: {ex}"
            ) from ex

        _LOGGER.debug("[DISCOVERY] %s << %s", config.host, info)

        device_class = cast(Type[IotDevice], Discover._get_device_class(info))
        device = device_class(config.host, config=config)
        sys_info = info["system"]["get_sysinfo"]
        if device_type := sys_info.get("mic_type", sys_info.get("type")):
            config.connection_type = ConnectionType.from_values(
                device_family=device_type, encryption_type=EncryptType.Xor.value
            )
        device.protocol = get_protocol(config)  # type: ignore[assignment]
        device.update_from_discover_info(info)
        return device

    @staticmethod
    def _get_device_instance(
        data: bytes,
        config: DeviceConfig,
    ) -> Device:
        """Get SmartDevice from the new 20002 response."""
        try:
            info = json_loads(data[16:])
        except Exception as ex:
            _LOGGER.debug("Got invalid response from device %s: %s", config.host, data)
            raise KasaException(
                f"Unable to read response from device: {config.host}: {ex}"
            ) from ex
        try:
            discovery_result = DiscoveryResult(**info["result"])
        except ValidationError as ex:
            _LOGGER.debug(
                "Unable to parse discovery from device %s: %s", config.host, info
            )
            raise UnsupportedDeviceError(
                f"Unable to parse discovery from device: {config.host}: {ex}"
            ) from ex

        type_ = discovery_result.device_type

        try:
            config.connection_type = ConnectionType.from_values(
                type_,
                discovery_result.mgt_encrypt_schm.encrypt_type,
                discovery_result.mgt_encrypt_schm.lv,
            )
        except KasaException as ex:
            raise UnsupportedDeviceError(
                f"Unsupported device {config.host} of type {type_} "
                + f"with encrypt_type {discovery_result.mgt_encrypt_schm.encrypt_type}",
                discovery_result=discovery_result.get_dict(),
            ) from ex
        if (device_class := get_device_class_from_family(type_)) is None:
            _LOGGER.warning("Got unsupported device type: %s", type_)
            raise UnsupportedDeviceError(
                f"Unsupported device {config.host} of type {type_}: {info}",
                discovery_result=discovery_result.get_dict(),
            )
        if (protocol := get_protocol(config)) is None:
            _LOGGER.warning(
                "Got unsupported connection type: %s", config.connection_type.to_dict()
            )
            raise UnsupportedDeviceError(
                f"Unsupported encryption scheme {config.host} of "
                + f"type {config.connection_type.to_dict()}: {info}",
                discovery_result=discovery_result.get_dict(),
            )

        _LOGGER.debug("[DISCOVERY] %s << %s", config.host, info)
        device = device_class(config.host, protocol=protocol)

        di = discovery_result.get_dict()
        di["model"], _, _ = discovery_result.device_model.partition("(")
        device.update_from_discover_info(di)
        return device


class EncryptionScheme(BaseModel):
    """Base model for encryption scheme of discovery result."""

    is_support_https: bool
    encrypt_type: str
    http_port: int
    lv: Optional[int] = None  # noqa: UP007


class DiscoveryResult(BaseModel):
    """Base model for discovery result."""

    device_type: str
    device_model: str
    ip: str
    mac: str
    mgt_encrypt_schm: EncryptionScheme
    device_id: str

    hw_ver: Optional[str] = None  # noqa: UP007
    owner: Optional[str] = None  # noqa: UP007
    is_support_iot_cloud: Optional[bool] = None  # noqa: UP007
    obd_src: Optional[str] = None  # noqa: UP007
    factory_default: Optional[bool] = None  # noqa: UP007

    def get_dict(self) -> dict:
        """Return a dict for this discovery result.

        containing only the values actually set and with aliases as field names.
        """
        return self.dict(
            by_alias=False, exclude_unset=True, exclude_none=True, exclude_defaults=True
        )
