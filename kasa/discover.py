"""Discover TPLink Smart Home devices.

The main entry point for this library is :meth:`Discover.discover()`,
which returns a dictionary of the found devices. The key is the IP address
of the device and the value is a :class:`Device` instance initialized from
the selected discovery response.

:meth:`discover_single()` can be used to initialize a single device given its
IP address. If the :class:`DeviceConfig` of the device is already known,
you can initialize the corresponding device class directly without discovery.

Discovery queries UDP port 9999 and TDP ports 20002 and 20004. If a host
responds through both UDP and TDP, the TDP response is used.

Devices that respond to TDP discovery will most likely require TP-Link cloud
credentials to be passed if queries or updates are to be performed on the
returned devices.

Discovery returns a dict of {ip: discovered devices}:

>>> from kasa import Discover, Credentials
>>>
>>> found_devices = await Discover.discover()
>>> sorted(dev.model for dev in found_devices.values())
['H200', 'HS110', 'HS220', 'KL430', 'KP303', 'L530E']

You can pass username and password for devices requiring authentication

>>> devices = await Discover.discover(
...     username="user@example.com",
...     password="great_password",
... )
>>> print(len(devices))
6

You can also pass a :class:`kasa.Credentials`

>>> creds = Credentials("user@example.com", "great_password")
>>> devices = await Discover.discover(credentials=creds)
>>> print(len(devices))
6

Discovery can also be targeted to a specific broadcast address instead of
the default 255.255.255.255:

>>> found_devices = await Discover.discover(target="127.0.0.255", credentials=creds)
>>> print(len(found_devices))
6

Basic information is available on the device from the discovery broadcast response
but it is important to call device.update() after discovery if you want to access
all the attributes without getting errors or None.

>>> dev = found_devices["127.0.0.3"]
>>> dev.alias
None
>>> await dev.update()
>>> dev.alias
'Living Room Bulb'

It is also possible to pass a coroutine to be executed for each found device.
Callbacks can complete in any order:

>>> discovered = []
>>> async def collect_dev_info(dev):
...     await dev.update()
...     discovered.append(f"Discovered {dev.alias} (model: {dev.model})")
>>>
>>> devices = await Discover.discover(on_discovered=collect_dev_info, credentials=creds)
>>> for info in sorted(discovered):
...     print(info)
Discovered Bedroom Lamp Plug (model: HS110)
Discovered Bedroom Lightstrip (model: KL430)
Discovered Bedroom Power Strip (model: KP303)
Discovered Living Room Bulb (model: L530)
Discovered Living Room Dimmer Switch (model: HS220)
Discovered Tapo Hub (model: H200)

Discovering a single device returns a kasa.Device object.

>>> device = await Discover.discover_single("127.0.0.1", credentials=creds)
>>> device.model
'KP303'

"""

from __future__ import annotations

import asyncio
import base64
import binascii
import builtins
import ipaddress
import logging
import secrets
import socket
import struct
from asyncio import timeout as asyncio_timeout
from asyncio.transports import DatagramTransport
from collections.abc import Callable, Coroutine
from copy import deepcopy
from dataclasses import dataclass, field
from enum import Enum
from pprint import pformat as pf
from typing import (
    TYPE_CHECKING,
    Annotated,
    Any,
    NotRequired,
    Protocol,
    TypedDict,
    cast,
)

from aiohttp import ClientSession
from mashumaro.config import BaseConfig
from mashumaro.types import Alias

from kasa import Device
from kasa.credentials import Credentials
from kasa.device_factory import (
    OnConnectAttemptCallable,
    create_device,
    try_connect_all,
)
from kasa.deviceconfig import (
    DeviceConfig,
    DeviceConnectionParameters,
    DeviceEncryptionType,
    DeviceFamily,
)
from kasa.exceptions import (
    AuthenticationError,
    DiscoveryAuthenticationError,
    KasaException,
    TimeoutError,
    UnsupportedDeviceError,
)
from kasa.iot.iotdevice import extract_sys_info
from kasa.json import DataClassJSONMixin
from kasa.json import dumps as json_dumps
from kasa.json import loads as json_loads
from kasa.protocols.iotprotocol import REDACTORS as IOT_REDACTORS
from kasa.protocols.protocol import mask_mac, redact_data
from kasa.transports.aestransport import AesEncyptionSession, KeyPair
from kasa.transports.xortransport import XorEncryption

_LOGGER = logging.getLogger(__name__)


class DiscoveredMeta(TypedDict):
    """Identify the address and discovery method that produced a raw response."""

    ip: str
    port: int
    source: NotRequired[str]


class DiscoveredRaw(TypedDict):
    """Decoded response supplied to a raw discovery callback."""

    meta: DiscoveredMeta
    discovery_response: dict


OnDiscoveredCallable = Callable[[Device], Coroutine]
OnDiscoveredRawCallable = Callable[[DiscoveredRaw], None]
OnUnsupportedCallable = Callable[[UnsupportedDeviceError], Coroutine]
OnAuthenticationErrorCallable = Callable[[DiscoveryAuthenticationError], Coroutine]
DeviceDict = dict[str, Device]


class _DiscoverySource(Enum):
    """Discovery methods supported by the library."""

    Udp = "udp"
    Tdp = "tdp"


def select_discovery_response(responses: list[DiscoveredRaw]) -> DiscoveredRaw:
    """Prefer a TDP response, otherwise return the first decoded response."""
    if not responses:
        raise KasaException("No decoded discovery responses available")

    def get_source(response: DiscoveredRaw) -> str:
        meta = response["meta"]
        if source := meta.get("source"):
            return source
        return (
            _DiscoverySource.Tdp.value
            if meta["port"] in (Discover.DISCOVERY_PORT_2, Discover.DISCOVERY_PORT_3)
            else _DiscoverySource.Udp.value
        )

    tdp_responses = [
        response
        for response in responses
        if get_source(response) == _DiscoverySource.Tdp.value
    ]
    if not tdp_responses:
        return responses[0]

    tdp_ports = {response["meta"]["port"] for response in tdp_responses}
    if len(tdp_ports) > 1:
        first = tdp_responses[0]
        _LOGGER.warning(
            "Host %s unexpectedly produced responses on multiple TDP ports; "
            "preserving the first endpoint response",
            first["meta"]["ip"],
        )
    return tdp_responses[0]


@dataclass(frozen=True)
class _DiscoveryConnection:
    """Connection information advertised by a discovery response."""

    device_family: str
    encryption_type: str
    login_version: int | None = None
    klap_version: int | None = None
    https: bool = False
    http_port: int | None = None

    @classmethod
    def from_tdp_result(
        cls,
        discovery_result: DiscoveryResult,
    ) -> _DiscoveryConnection:
        """Extract normalized connection information from a TDP result."""
        if (encrypt_scheme := discovery_result.mgt_encrypt_schm) is None:
            raise UnsupportedDeviceError(
                f"Unsupported device {discovery_result.ip} of type "
                f"{discovery_result.device_type} with no mgt_encrypt_schm",
                discovery_result=discovery_result.to_dict(),
                host=discovery_result.ip,
            )

        encrypt_type = encrypt_scheme.encrypt_type
        if not encrypt_type and (encrypt_info := discovery_result.encrypt_info):
            encrypt_type = encrypt_info.sym_schm

        login_version = encrypt_scheme.lv
        if not login_version and (supported_types := discovery_result.encrypt_type):
            try:
                login_version = max(int(value) for value in supported_types)
            except ValueError as ex:
                raise UnsupportedDeviceError(
                    f"Unsupported login versions for {discovery_result.ip}: "
                    f"{supported_types}",
                    discovery_result=discovery_result.to_dict(),
                    host=discovery_result.ip,
                ) from ex

        if not encrypt_type:
            raise UnsupportedDeviceError(
                f"Unsupported device {discovery_result.ip} of type "
                f"{discovery_result.device_type} with no encryption type",
                discovery_result=discovery_result.to_dict(),
                host=discovery_result.ip,
            )

        # new_klap selects an IOT KLAP handshake variant. It is independent
        # from the advertised login version and is not used to select SMART
        # KLAP, which already has its own family-specific route.
        klap_version = (
            encrypt_scheme.new_klap or None
            if discovery_result.device_type.startswith("IOT.")
            and encrypt_type == DeviceEncryptionType.Klap.value
            else None
        )

        return cls(
            device_family=discovery_result.device_type,
            encryption_type=encrypt_type,
            login_version=login_version,
            klap_version=klap_version,
            https=encrypt_scheme.is_support_https,
            http_port=encrypt_scheme.http_port,
        )

    def to_connection_parameters(self) -> DeviceConnectionParameters:
        """Create public connection parameters from advertised values."""
        return DeviceConnectionParameters.from_values(
            self.device_family,
            self.encryption_type,
            login_version=self.login_version,
            klap_version=self.klap_version,
            https=self.https,
            http_port=self.http_port,
        )


@dataclass(frozen=True)
class _DiscoveryCandidate:
    """Normalized result returned by a discovery method."""

    source: _DiscoverySource
    source_port: int
    ip: str
    device_family: str
    device_model: str | None
    connection: _DiscoveryConnection
    discovery_info: dict[str, Any]
    device_info: dict[str, Any] | None = None
    discovery_result: DiscoveryResult | None = None


@dataclass(frozen=True)
class _DiscoveryResponseError:
    """Error produced while processing one discovery response."""

    source: _DiscoverySource
    source_port: int
    error: KasaException


@dataclass
class _DiscoveryEndpointState:
    """Response collection state for one host and discovery endpoint."""

    deferred_datagrams: list[bytes] = field(default_factory=list)
    response_errors: list[_DiscoveryResponseError] = field(default_factory=list)
    first_decoded_response: dict[str, Any] | None = None
    candidate: _DiscoveryCandidate | None = None
    raw_emitted: bool = False


class _DiscoveryMethod(Protocol):
    """Internal contract implemented by one discovery endpoint."""

    source: _DiscoverySource
    port: int
    defer_processing: bool
    suppresses: frozenset[_DiscoverySource]

    def create_query(self) -> bytes:
        """Create the query sent to this endpoint."""

    def parse_response(self, data: bytes, ip: str) -> dict[str, Any]:
        """Decode a response from this endpoint."""

    def create_candidate(
        self,
        info: dict[str, Any],
        ip: str,
        port: int,
    ) -> _DiscoveryCandidate:
        """Normalize a decoded response."""


@dataclass
class _DiscoveryHostState:
    """Collection, resolution, and publication state for one host."""

    endpoints: dict[int, _DiscoveryEndpointState] = field(default_factory=dict)
    suppressed_sources: set[_DiscoverySource] = field(default_factory=set)
    # Devices belong to one TDP endpoint population. This records that endpoint
    # so an unexpected same-IP response on the other port cannot merge state.
    tdp_port: int | None = None
    ignored_tdp_ports: set[int] = field(default_factory=set)
    processing_lock: asyncio.Lock = field(default_factory=asyncio.Lock)
    device: Device | None = None
    unsupported_error: UnsupportedDeviceError | None = None
    authentication_error: DiscoveryAuthenticationError | None = None
    invalid_error: KasaException | None = None
    outcome_finalized: bool = False


DECRYPTED_REDACTORS: dict[str, Callable[[Any], Any] | None] = {
    "connect_ssid": lambda x: "#MASKED_SSID#" if x else "",
    "device_id": lambda x: "REDACTED_" + x[9::],
    "owner": lambda x: "REDACTED_" + x[9::],
}

TDP_DISCOVERY_REDACTORS: dict[str, Callable[[Any], Any] | None] = {
    "device_id": lambda x: "REDACTED_" + x[9::],
    "device_name": lambda x: "#MASKED_NAME#" if x else "",
    "owner": lambda x: "REDACTED_" + x[9::],
    "mac": mask_mac,
    "master_device_id": lambda x: "REDACTED_" + x[9::],
    "group_id": lambda x: "REDACTED_" + x[9::],
    "group_name": lambda x: "I01BU0tFRF9TU0lEIw==",
    "encrypt_info": lambda x: {**x, "key": "", "data": ""},
    "ip": lambda x: x,  # don't redact but keep listed here for dump_devinfo
    "decrypted_data": lambda x: redact_data(x, DECRYPTED_REDACTORS),
}

# Compatibility name used by devtools and external callers before the source
# was explicitly named TDP discovery.
NEW_DISCOVERY_REDACTORS = TDP_DISCOVERY_REDACTORS


class _AesDiscoveryQuery:
    """Create a TDP discovery query and retain its response keypair."""

    def __init__(self) -> None:
        self.keypair = KeyPair.create_key_pair(key_size=2048)

    def generate_query(self) -> bytearray:
        """Generate a TDP discovery query for this discovery operation."""
        secret = secrets.token_bytes(4)

        key_payload = {"params": {"rsa_key": self.keypair.get_public_pem().decode()}}

        key_payload_bytes = json_dumps(key_payload).encode()
        # https://labs.withsecure.com/advisories/tp-link-ac1750-pwn2own-2019
        version = 2  # version of tdp
        msg_type = 0
        op_code = 1  # probe
        msg_size = len(key_payload_bytes)
        flags = 17
        padding_byte = 0  # blank byte
        device_serial = int.from_bytes(secret, "big")
        initial_crc = 0x5A6B7C8D

        disco_header = struct.pack(
            ">BBHHBBII",
            version,
            msg_type,
            op_code,
            msg_size,
            flags,
            padding_byte,
            device_serial,
            initial_crc,
        )

        query = bytearray(disco_header + key_payload_bytes)
        crc = binascii.crc32(query).to_bytes(length=4, byteorder="big")
        query[12:16] = crc
        return query


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
        on_discovered_raw: OnDiscoveredRawCallable | None = None,
        target: str = "255.255.255.255",
        discovery_packets: int = 3,
        discovery_timeout: int = 5,
        interface: str | None = None,
        on_unsupported: OnUnsupportedCallable | None = None,
        on_authentication_error: OnAuthenticationErrorCallable | None = None,
        port: int | None = None,
        credentials: Credentials | None = None,
        credentials_hash: str | None = None,
        timeout: int | None = None,
    ) -> None:
        self.transport: DatagramTransport | None = None
        self.discovery_packets = discovery_packets
        self.interface = interface
        self.on_discovered = on_discovered

        self.port = port
        self.discovery_port = port or Discover.DISCOVERY_PORT
        if self.discovery_port in {
            Discover.DISCOVERY_PORT_2,
            Discover.DISCOVERY_PORT_3,
        }:
            raise KasaException(
                f"UDP discovery port {self.discovery_port} is reserved for "
                "TDP discovery"
            )
        self.target = target

        self._discoveries: tuple[_DiscoveryMethod, ...] = (
            _UdpDiscovery(self.discovery_port),
            # These are independent endpoints for separate device populations.
            _TdpDiscovery(Discover.DISCOVERY_PORT_2),
            _TdpDiscovery(Discover.DISCOVERY_PORT_3),
        )
        self._discovery_by_port = {
            discovery.port: discovery for discovery in self._discoveries
        }
        self._target_complete = asyncio.Event()

        self.discovered_devices = {}
        self.unsupported_device_exceptions: dict[str, UnsupportedDeviceError] = {}
        self.authentication_exceptions: dict[str, DiscoveryAuthenticationError] = {}
        self.invalid_device_exceptions: dict[str, KasaException] = {}
        self._hosts: dict[str, _DiscoveryHostState] = {}
        self._processing_tasks: list[asyncio.Task] = []
        self._processed_task_count = 0
        self.on_unsupported = on_unsupported
        self.on_authentication_error = on_authentication_error
        self.on_discovered_raw = on_discovered_raw
        self.credentials = credentials
        self.credentials_hash = credentials_hash
        self.timeout = timeout
        self.discovery_timeout = discovery_timeout
        self.discover_task: asyncio.Task | None = None
        self.callback_tasks: list[asyncio.Task] = []
        self._processed_callback_task_count = 0
        self._started_event = asyncio.Event()
        self._accepting_responses = True

    def _run_callback_task(self, coro: Coroutine) -> None:
        task: asyncio.Task = asyncio.create_task(coro)
        self.callback_tasks.append(task)

    def _run_processing_task(self, ip: str, port: int) -> None:
        """Schedule processing for an accepted immediate candidate."""
        task = asyncio.create_task(self._process_candidate(ip, port))
        self._processing_tasks.append(task)

    async def _wait_for_processing(self) -> None:
        """Wait for all candidate-processing tasks scheduled so far."""
        while self._processed_task_count < len(self._processing_tasks):
            tasks = self._processing_tasks[self._processed_task_count :]
            self._processed_task_count = len(self._processing_tasks)
            await asyncio.gather(*tasks)

    async def _wait_for_callbacks(self) -> None:
        """Wait once for every callback task, including completed tasks."""
        while self._processed_callback_task_count < len(self.callback_tasks):
            tasks = self.callback_tasks[self._processed_callback_task_count :]
            self._processed_callback_task_count = len(self.callback_tasks)
            await asyncio.gather(*tasks)

    async def cancel_pending_tasks(self) -> None:
        """Cancel and await discovery-owned processing and callback tasks."""
        tasks = [*self._processing_tasks, *self.callback_tasks]
        if self.discover_task is not None and not self.discover_task.done():
            tasks.append(self.discover_task)
        for task in tasks:
            if not task.done():
                task.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)

    async def close_discovered_devices(self) -> None:
        """Close all device protocols owned by an aborted discovery call."""
        await asyncio.gather(
            *(device.protocol.close() for device in self.discovered_devices.values()),
            return_exceptions=True,
        )

    async def wait_for_discovery_to_complete(self) -> None:
        """Wait for the discovery task to complete."""
        # Give some time for connection_made event to be received
        async with asyncio_timeout(self.DISCOVERY_START_TIMEOUT):
            await self._started_event.wait()
        if TYPE_CHECKING:
            assert isinstance(self.discover_task, asyncio.Task)

        await self.discover_task
        # Freeze the receive set before awaiting any final device creation. A
        # datagram arriving during finalization must not mutate the independent
        # source results or race host-level authority selection.
        self._accepting_responses = False
        await self._finalize_discovery()
        # A callback can synchronously invoke an error callback, so drain until
        # no newly scheduled callback tasks remain.
        await self._wait_for_callbacks()

    def connection_made(self, transport: DatagramTransport) -> None:  # type: ignore[override]
        """Set socket options for broadcasting."""
        self.transport = cast(DatagramTransport, transport)

        sock = self.transport.get_extra_info("socket")
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        try:
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        except OSError as ex:  # WSL does not support SO_REUSEADDR, see #246
            _LOGGER.debug("Unable to set SO_REUSEADDR: %s", ex)

        # windows does not support SO_BINDTODEVICE
        if self.interface is not None and hasattr(socket, "SO_BINDTODEVICE"):
            sock.setsockopt(
                socket.SOL_SOCKET, socket.SO_BINDTODEVICE, self.interface.encode()
            )

        self.discover_task = asyncio.create_task(self.do_discover())
        self._started_event.set()

    async def do_discover(self) -> None:
        """Send number of discovery datagrams."""
        sleep_between_packets = self.discovery_timeout / self.discovery_packets

        queries = [
            (discovery, discovery.create_query()) for discovery in self._discoveries
        ]
        for discovery, _ in queries:
            _LOGGER.debug(
                "[DISCOVERY] %s >> %s/%s",
                self.target,
                discovery.source.value,
                discovery.port,
            )
        for _ in range(self.discovery_packets):
            for discovery, query in queries:
                self.transport.sendto(  # type: ignore[union-attr]
                    query, (self.target, discovery.port)
                )
            # Let immediate TDP processing publish a verified target before
            # another packet round begins, including when the timeout is zero.
            await asyncio.sleep(0)
            if self._target_complete.is_set():
                return
            try:
                async with asyncio_timeout(sleep_between_packets):
                    await self._target_complete.wait()
            except builtins.TimeoutError:
                pass
            else:
                return

    def datagram_received(
        self,
        data: bytes,
        addr: tuple[str, int],
    ) -> None:
        """Handle discovery responses."""
        if not self._accepting_responses:
            return
        source_ip, port = addr
        if (discovery := self._discovery_by_port.get(port)) is None:
            return
        try:
            ip = str(ipaddress.ip_address(source_ip))
        except ValueError:
            _LOGGER.debug(
                "[DISCOVERY] Unable to normalize source address %s", source_ip
            )
            ip = source_ip
        host_state = self._hosts.setdefault(ip, _DiscoveryHostState())

        if discovery.source in host_state.suppressed_sources:
            return

        if discovery.suppresses:
            host_state.suppressed_sources.update(discovery.suppresses)
            for endpoint_port, endpoint_state in host_state.endpoints.items():
                endpoint_method = self._discovery_by_port[endpoint_port]
                if endpoint_method.source in discovery.suppresses:
                    endpoint_state.deferred_datagrams.clear()

        if discovery.source is _DiscoverySource.Tdp:
            if host_state.tdp_port is None:
                host_state.tdp_port = port
            elif host_state.tdp_port != port:
                if port not in host_state.ignored_tdp_ports:
                    _LOGGER.warning(
                        "Host %s unexpectedly responded on TDP ports %s and %s; "
                        "ignoring the second endpoint response",
                        ip,
                        host_state.tdp_port,
                        port,
                    )
                    host_state.ignored_tdp_ports.add(port)
                return

        if host_state.outcome_finalized:
            return

        endpoint_state = host_state.endpoints.setdefault(
            port, _DiscoveryEndpointState()
        )

        if discovery.defer_processing:
            # Deferred datagrams remain opaque until the receive window closes.
            # An immediate method can suppress them without triggering parsing,
            # normalization, callbacks, or device construction.
            endpoint_state.deferred_datagrams.append(data)
            return

        self._process_datagram(data, ip, port, discovery)

    def _process_datagram(
        self,
        data: bytes,
        ip: str,
        port: int,
        discovery: _DiscoveryMethod,
    ) -> None:
        """Decode and normalize one discovery datagram."""
        host_state = self._hosts[ip]
        if host_state.outcome_finalized:
            return
        endpoint_state = host_state.endpoints.setdefault(
            port, _DiscoveryEndpointState()
        )
        if endpoint_state.candidate is not None:
            return
        try:
            info = discovery.parse_response(data, ip)
        except KasaException as ex:
            _LOGGER.debug(
                "[DISCOVERY] Unable to parse response from %s on port %s "
                "(%s bytes): %s",
                ip,
                port,
                len(data),
                ex,
            )
            endpoint_state.response_errors.append(
                _DiscoveryResponseError(
                    source=discovery.source,
                    source_port=port,
                    error=ex,
                )
            )
            return

        if endpoint_state.first_decoded_response is None:
            endpoint_state.first_decoded_response = info

        try:
            candidate = discovery.create_candidate(info, ip, port)
        except UnsupportedDeviceError as ex:
            _LOGGER.debug(
                "[DISCOVERY] Unsupported response from %s on port %s: %s",
                ip,
                port,
                ex,
            )
            endpoint_state.response_errors.append(
                _DiscoveryResponseError(
                    source=discovery.source,
                    source_port=port,
                    error=ex,
                )
            )
            return
        except KasaException as ex:
            _LOGGER.debug(
                "[DISCOVERY] Unable to normalize response from %s on port %s: %s",
                ip,
                port,
                ex,
            )
            endpoint_state.response_errors.append(
                _DiscoveryResponseError(
                    source=discovery.source,
                    source_port=port,
                    error=ex,
                )
            )
            return

        endpoint_state.candidate = candidate
        self._emit_raw_response(ip, discovery, endpoint_state, info)
        if not discovery.defer_processing:
            self._run_processing_task(ip, port)

    def _emit_raw_response(
        self,
        ip: str,
        discovery: _DiscoveryMethod,
        endpoint_state: _DiscoveryEndpointState,
        info: dict[str, Any],
    ) -> None:
        """Emit one representative decoded response for an endpoint."""
        if self.on_discovered_raw is None or endpoint_state.raw_emitted:
            return
        endpoint_state.raw_emitted = True
        self.on_discovered_raw(
            {
                "discovery_response": deepcopy(info),
                "meta": {
                    "ip": ip,
                    "port": discovery.port,
                    "source": discovery.source.value,
                },
            }
        )

    def _emit_diagnostic_raw_response(
        self,
        ip: str,
        discovery: _DiscoveryMethod,
        endpoint_state: _DiscoveryEndpointState,
    ) -> None:
        """Emit the first decoded response when an endpoint had no usable result."""
        if endpoint_state.first_decoded_response is not None:
            self._emit_raw_response(
                ip,
                discovery,
                endpoint_state,
                endpoint_state.first_decoded_response,
            )

    async def _finalize_discovery(self) -> None:
        """Process unsuppressed UDP datagrams and finalize remaining hosts."""
        self._accepting_responses = False
        await self._wait_for_processing()
        # Iterate a stable snapshot. datagram_received is disabled before this
        # method is called, and processing tasks scheduled from accepted
        # datagrams have been drained above.
        for ip, host_state in list(self._hosts.items()):
            if host_state.outcome_finalized:
                continue

            if host_state.tdp_port is not None:
                port = host_state.tdp_port
                discovery = self._discovery_by_port[port]
                endpoint_state = host_state.endpoints[port]
                if endpoint_state.candidate is not None:
                    await self._process_candidate(ip, port)
                else:
                    self._emit_diagnostic_raw_response(ip, discovery, endpoint_state)
                    if response_error := self._select_response_error(endpoint_state):
                        self._record_response_error(ip, response_error.error)
                    else:  # pragma: no cover - every datagram has an outcome
                        self._record_invalid(
                            ip,
                            KasaException(
                                f"No usable TDP discovery response received from {ip}"
                            ),
                        )
                continue

            for port, endpoint_state in host_state.endpoints.items():
                discovery = self._discovery_by_port[port]
                if discovery.source in host_state.suppressed_sources:
                    endpoint_state.deferred_datagrams.clear()
                    continue
                for data in endpoint_state.deferred_datagrams:
                    self._process_datagram(data, ip, port, discovery)
                    if endpoint_state.candidate is not None:
                        break
                endpoint_state.deferred_datagrams.clear()

                if endpoint_state.candidate is not None:
                    await self._process_candidate(ip, port)
                    break

                self._emit_diagnostic_raw_response(ip, discovery, endpoint_state)
                if response_error := self._select_response_error(endpoint_state):
                    self._record_response_error(ip, response_error.error)
                    break

    async def _process_candidate(self, ip: str, port: int) -> None:
        """Create a device from the accepted candidate for one endpoint."""
        host_state = self._hosts[ip]
        async with host_state.processing_lock:
            if host_state.outcome_finalized:
                return

            candidate = host_state.endpoints[port].candidate
            if candidate is None:
                return

            try:
                device = await self._create_device(candidate)
            except UnsupportedDeviceError as ex:
                self._record_unsupported(ip, ex)
            except AuthenticationError as ex:
                self._record_authentication(
                    ip, self._as_discovery_authentication_error(ip, ex, candidate)
                )
            except KasaException as ex:
                self._record_invalid(ip, ex)
            else:
                self._record_device(ip, device)

    @staticmethod
    def _select_response_error(
        endpoint_state: _DiscoveryEndpointState,
    ) -> _DiscoveryResponseError | None:
        """Return the most useful error from repeated endpoint responses."""
        return next(
            (
                response_error
                for response_error in endpoint_state.response_errors
                if isinstance(response_error.error, UnsupportedDeviceError)
            ),
            endpoint_state.response_errors[0]
            if endpoint_state.response_errors
            else None,
        )

    def _record_response_error(self, ip: str, ex: KasaException) -> None:
        """Classify an endpoint error after response collection completes."""
        if isinstance(ex, UnsupportedDeviceError):
            self._record_unsupported(ip, ex)
        else:
            self._record_invalid(ip, ex)

    async def _on_discovered(self, device: Device) -> None:
        """Run the device callback and classify supported callback failures."""
        if TYPE_CHECKING:
            assert self.on_discovered is not None
        try:
            await self.on_discovered(device)
        except UnsupportedDeviceError as ex:
            if ex.host is None:
                ex.host = device.host
            if ex.discovery_result is None:
                ex.discovery_result = device._discovery_info
            self._store_unsupported(device.host, ex, terminal=False)
            if self.on_unsupported is None:
                raise
            await self.on_unsupported(ex)
        except AuthenticationError as ex:
            discovery_error = self._as_discovery_authentication_error(
                device.host,
                ex,
                discovery_info=device._discovery_info,
            )
            self._store_authentication(device.host, discovery_error, terminal=False)
            if self.on_authentication_error is None:
                raise
            await self.on_authentication_error(discovery_error)

    @staticmethod
    def _as_discovery_authentication_error(
        ip: str,
        ex: AuthenticationError,
        candidate: _DiscoveryCandidate | None = None,
        *,
        discovery_info: dict[str, Any] | None = None,
    ) -> DiscoveryAuthenticationError:
        """Add discovery context to an authentication error."""
        if isinstance(ex, DiscoveryAuthenticationError):
            if ex.host is None:
                ex.host = ip
            if ex.discovery_result is None:
                ex.discovery_result = discovery_info or (
                    candidate.discovery_info if candidate is not None else None
                )
            return ex
        if discovery_info is None and candidate is not None:
            discovery_info = candidate.discovery_info
        discovery_error = DiscoveryAuthenticationError(
            *ex.args,
            discovery_result=discovery_info,
            host=ip,
            error_code=ex.error_code,
        )
        discovery_error.__cause__ = ex
        return discovery_error

    def _record_device(self, ip: str, device: Device) -> None:
        """Record and emit one supported device."""
        host_state = self._hosts[ip]
        if host_state.outcome_finalized:
            return
        host_state.outcome_finalized = True
        host_state.device = device
        self.discovered_devices[ip] = device
        if self.on_discovered is not None:
            self._run_callback_task(self._on_discovered(device))
        if ip == self.target:
            self._target_complete.set()

    def _record_unsupported(self, ip: str, ex: UnsupportedDeviceError) -> None:
        """Record and emit one authoritative unsupported response."""
        if not self._store_unsupported(ip, ex, terminal=True):
            return
        if self.on_unsupported is not None:
            self._run_callback_task(self.on_unsupported(ex))

    def _store_unsupported(
        self,
        ip: str,
        ex: UnsupportedDeviceError,
        *,
        terminal: bool,
    ) -> bool:
        """Store an unsupported outcome and optionally finalize discovery."""
        host_state = self._hosts[ip]
        if host_state.unsupported_error is not None:
            return False
        if terminal and host_state.outcome_finalized:
            return False
        _LOGGER.debug("Unsupported device found at %s << %s", ip, ex)
        host_state.unsupported_error = ex
        host_state.outcome_finalized = host_state.outcome_finalized or terminal
        self.unsupported_device_exceptions[ip] = ex
        if terminal and ip == self.target:
            self._target_complete.set()
        return True

    def _record_authentication(self, ip: str, ex: DiscoveryAuthenticationError) -> None:
        """Record and emit an authentication-blocked discovery outcome."""
        if not self._store_authentication(ip, ex, terminal=True):
            return
        if self.on_authentication_error is not None:
            self._run_callback_task(self.on_authentication_error(ex))

    def _store_authentication(
        self,
        ip: str,
        ex: DiscoveryAuthenticationError,
        *,
        terminal: bool,
    ) -> bool:
        """Store an authentication outcome and optionally finalize discovery."""
        host_state = self._hosts[ip]
        if host_state.authentication_error is not None:
            return False
        if terminal and host_state.outcome_finalized:
            return False
        host_state.authentication_error = ex
        host_state.outcome_finalized = host_state.outcome_finalized or terminal
        self.authentication_exceptions[ip] = ex
        if terminal and ip == self.target:
            self._target_complete.set()
        return True

    def _record_invalid(self, ip: str, ex: KasaException) -> None:
        """Record one response that cannot create a device."""
        host_state = self._hosts[ip]
        if host_state.outcome_finalized:
            return
        _LOGGER.debug("[DISCOVERY] Unable to create device for %s: %s", ip, ex)
        host_state.outcome_finalized = True
        host_state.invalid_error = ex
        self.invalid_device_exceptions[ip] = ex
        if ip == self.target:
            self._target_complete.set()

    async def _create_device(
        self,
        candidate: _DiscoveryCandidate,
    ) -> Device:
        """Create a device from the selected normalized discovery response."""
        config = DeviceConfig(host=candidate.ip, port_override=self.port)
        if self.credentials:
            config.credentials = self.credentials
        if self.credentials_hash:
            config.credentials_hash = self.credentials_hash
        if self.timeout:
            config.timeout = self.timeout

        try:
            config.connection_type = candidate.connection.to_connection_parameters()
        except KasaException as ex:
            raise UnsupportedDeviceError(
                f"Unsupported device {candidate.ip} of type "
                f"{candidate.device_family} with connection parameters "
                f"{candidate.connection}",
                discovery_result=candidate.discovery_info,
                host=candidate.ip,
            ) from ex

        if candidate.discovery_result is not None:
            discovery_info = candidate.discovery_result.to_dict()
            discovery_info["model"], _, _ = (
                candidate.discovery_result.device_model.partition("(")
            )
        else:
            discovery_info = candidate.discovery_info

        device = await create_device(
            config,
            device_info=candidate.device_info,
            discovery_info=discovery_info,
        )

        if _LOGGER.isEnabledFor(logging.DEBUG):
            redactors = (
                TDP_DISCOVERY_REDACTORS
                if candidate.source is _DiscoverySource.Tdp
                else IOT_REDACTORS
            )
            data = (
                redact_data(candidate.discovery_info, redactors)
                if Discover._redact_data
                else candidate.discovery_info
            )
            _LOGGER.debug("[DISCOVERY] %s << %s", candidate.ip, pf(data))
        return device

    def error_received(self, ex: Exception) -> None:
        """Handle asyncio.Protocol errors."""
        _LOGGER.error("Got error: %s", ex)

    def connection_lost(self, ex: Exception | None) -> None:  # pragma: no cover
        """Cancel the discover task if running."""
        if self.discover_task:
            self.discover_task.cancel()


class Discover:
    """Class for discovering devices."""

    DISCOVERY_PORT = 9999

    DISCOVERY_QUERY: dict[str, dict[str, dict]] = {
        "system": {"get_sysinfo": {}},
    }

    DISCOVERY_PORT_2 = 20002
    DISCOVERY_PORT_3 = 20004
    DISCOVERY_QUERY_2 = binascii.unhexlify("020000010000000000000000463cb5d3")

    _redact_data = True

    @staticmethod
    async def discover(
        *,
        target: str = "255.255.255.255",
        on_discovered: OnDiscoveredCallable | None = None,
        on_discovered_raw: OnDiscoveredRawCallable | None = None,
        discovery_timeout: int = 5,
        discovery_packets: int = 3,
        interface: str | None = None,
        on_unsupported: OnUnsupportedCallable | None = None,
        on_authentication_error: OnAuthenticationErrorCallable | None = None,
        credentials: Credentials | None = None,
        credentials_hash: str | None = None,
        username: str | None = None,
        password: str | None = None,
        port: int | None = None,
        timeout: int | None = None,
    ) -> DeviceDict:
        """Discover supported devices.

        Sends discovery messages to UDP port 9999 and TDP ports 20002 and
        20004, then waits for responses from supported devices. If a host
        responds through both UDP and TDP, the TDP response is used.
        If you have multiple interfaces,
        you can use *target* parameter to specify the network for discovery.

        If given, `on_discovered` coroutine will get awaited with
        a :class:`Device`-derived object as parameter.

        The results of the discovery are returned as a dict of
        :class:`Device`-derived objects keyed with IP addresses.
        The devices are initialized from discovery information. Call
        :meth:`Device.update` before accessing information not included in the
        discovery response.

        :param target: The target address where to send the broadcast discovery
         queries if multi-homing (e.g. 192.168.xxx.255).
        :param on_discovered: coroutine to execute on discovery
        :param on_discovered_raw: Optional callback for decoded discovery responses.
            At most one response is emitted for each host and endpoint. Callback
            metadata identifies the ``udp`` or ``tdp`` source.
        :param discovery_timeout: Seconds to wait for responses, defaults to 5
        :param discovery_packets: Number of discovery packets to broadcast
        :param interface: Bind to specific interface
        :param on_unsupported: Optional callback when unsupported devices are discovered
        :param on_authentication_error: Optional callback when authentication prevents
            discovery from creating or updating a device
        :param credentials: Credentials for devices that require authentication.
            username and password are ignored if provided.
        :param credentials_hash: Hashed credentials for devices that require
            authentication. Explicit credentials take precedence when both are given.
        :param username: Username for devices that require authentication
        :param password: Password for devices that require authentication
        :param port: Override the UDP discovery and device connection port.
            TDP discovery remains on ports 20002 and 20004.
        :param timeout: Query timeout in seconds for devices returned by discovery
        :return: dictionary with discovered devices
        """
        if not credentials and username and password:
            credentials = Credentials(username, password)
        loop = asyncio.get_event_loop()
        transport, protocol = await loop.create_datagram_endpoint(
            lambda: _DiscoverProtocol(
                target=target,
                on_discovered=on_discovered,
                discovery_packets=discovery_packets,
                interface=interface,
                on_unsupported=on_unsupported,
                on_authentication_error=on_authentication_error,
                on_discovered_raw=on_discovered_raw,
                credentials=credentials,
                credentials_hash=credentials_hash,
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
        except BaseException:
            await protocol.cancel_pending_tasks()
            await protocol.close_discovered_devices()
            raise
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
        credentials_hash: str | None = None,
        username: str | None = None,
        password: str | None = None,
        on_discovered: OnDiscoveredCallable | None = None,
        on_discovered_raw: OnDiscoveredRawCallable | None = None,
        on_unsupported: OnUnsupportedCallable | None = None,
        on_authentication_error: OnAuthenticationErrorCallable | None = None,
    ) -> Device | None:
        """Discover a single device by the given IP address.

        It is generally preferred to avoid :func:`discover_single()` and
        use :meth:`Device.connect()` instead as it should perform better when
        the WiFi network is congested or the device is not responding
        to discovery requests.

        :param host: Hostname of device to query
        :param discovery_timeout: Timeout in seconds for discovery
        :param port: Override the UDP discovery and device connection port.
            TDP discovery remains on ports 20002 and 20004.
        :param timeout: Query timeout in seconds for the constructed device
        :param credentials: Credentials for devices that require authentication.
            username and password are ignored if provided.
        :param credentials_hash: Hashed credentials for devices that require
            authentication. Explicit credentials take precedence when both are given.
        :param username: Username for devices that require authentication
        :param password: Password for devices that require authentication
        :param on_discovered: Optional coroutine to execute for the discovered device
        :param on_discovered_raw: Optional callback for decoded discovery responses.
            At most one response is emitted for each host and endpoint. Callback
            metadata identifies the ``udp`` or ``tdp`` source.
        :param on_unsupported: Optional callback when unsupported devices are discovered
        :param on_authentication_error: Optional callback when authentication prevents
            discovery from creating a device
        :rtype: Device
        :return: Object for querying/controlling found device.
        """
        if not credentials and username and password:
            credentials = Credentials(username, password)
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
                credentials_hash=credentials_hash,
                timeout=timeout,
                discovery_timeout=discovery_timeout,
                on_discovered=on_discovered,
                on_unsupported=on_unsupported,
                on_authentication_error=on_authentication_error,
                on_discovered_raw=on_discovered_raw,
            ),
            local_addr=("0.0.0.0", 0),  # noqa: S104
        )
        protocol = cast(_DiscoverProtocol, protocol)

        try:
            _LOGGER.debug(
                "Waiting a total of %s seconds for responses...", discovery_timeout
            )
            await protocol.wait_for_discovery_to_complete()
        except BaseException:
            await protocol.cancel_pending_tasks()
            await protocol.close_discovered_devices()
            raise
        finally:
            transport.close()

        if ip in protocol.discovered_devices:
            dev = protocol.discovered_devices[ip]
            dev.host = host
            return dev
        elif ip in protocol.unsupported_device_exceptions:
            if on_unsupported:
                return None
            else:
                raise protocol.unsupported_device_exceptions[ip]
        elif ip in protocol.authentication_exceptions:
            if on_authentication_error:
                return None
            raise protocol.authentication_exceptions[ip]
        elif ip in protocol.invalid_device_exceptions:
            raise protocol.invalid_device_exceptions[ip]
        else:
            raise TimeoutError(f"Timed out getting discovery response for {host}")

    @staticmethod
    async def try_connect_all(
        host: str,
        *,
        port: int | None = None,
        timeout: int | None = None,
        credentials: Credentials | None = None,
        credentials_hash: str | None = None,
        http_client: ClientSession | None = None,
        on_attempt: OnConnectAttemptCallable | None = None,
    ) -> Device | None:
        """Try to connect directly to a device with all possible parameters.

        This method can be used when broadcast discovery is unavailable.
        After successfully connecting use the device config and
        :meth:`Device.connect()` for future connections.

        :param host: Hostname of device to query
        :param port: Optionally override the device's connection port
        :param timeout: Query timeout in seconds for each connection attempt
        :param credentials: Credentials for devices that require authentication.
        :param credentials_hash: Hashed credentials for devices that require
            authentication. Explicit credentials take precedence when both are given.
        :param http_client: Optional client session for devices that use HTTP
        :param on_attempt: Optional callback invoked after every attempted route
        """
        return await try_connect_all(
            host,
            port=port,
            timeout=timeout,
            credentials=credentials,
            credentials_hash=credentials_hash,
            http_client=http_client,
            on_attempt=on_attempt,
        )


class _DiscoveryBaseMixin(DataClassJSONMixin):
    """Base class for serialization mixin."""

    class Config(BaseConfig):
        """Serialization config."""

        omit_none = True
        omit_default = True
        serialize_by_alias = True


@dataclass
class EncryptionScheme(_DiscoveryBaseMixin):
    """Connection encryption fields advertised by TDP discovery."""

    is_support_https: bool
    encrypt_type: str | None = None
    http_port: int | None = None
    lv: int | None = None
    new_klap: int | None = None


@dataclass
class EncryptionInfo(_DiscoveryBaseMixin):
    """Encrypted supplemental information in a TDP discovery response."""

    sym_schm: str
    key: str
    data: str


@dataclass
class DiscoveryResult(_DiscoveryBaseMixin):
    """Decoded device information returned by TDP discovery."""

    device_type: str
    device_model: str
    device_id: str
    ip: str
    mac: str
    mgt_encrypt_schm: EncryptionScheme | None = None
    device_name: str | None = None
    encrypt_info: EncryptionInfo | None = None
    encrypt_type: list[str] | None = None
    decrypted_data: dict | None = None
    is_reset_wifi: Annotated[bool | None, Alias("isResetWiFi")] = None

    firmware_version: str | None = None
    hardware_version: str | None = None
    hw_ver: str | None = None
    owner: str | None = None
    is_support_iot_cloud: bool | None = None
    obd_src: str | None = None
    factory_default: bool | None = None

    def to_connection_parameters(self) -> DeviceConnectionParameters:
        """Convert the advertised TDP fields into connection parameters."""
        return _DiscoveryConnection.from_tdp_result(self).to_connection_parameters()


class _UdpDiscovery:
    """XOR-encoded UDP discovery implementation for port 9999."""

    source = _DiscoverySource.Udp
    defer_processing = True
    suppresses: frozenset[_DiscoverySource] = frozenset()

    def __init__(self, port: int) -> None:
        self.port = port

    @staticmethod
    def create_query() -> bytes:
        """Create an XOR-encoded UDP discovery query."""
        request = json_dumps(Discover.DISCOVERY_QUERY)
        return XorEncryption.encrypt(request)[4:]

    @staticmethod
    def parse_response(data: bytes, ip: str) -> dict[str, Any]:
        """Decode an XOR-encoded UDP discovery response."""
        try:
            response = json_loads(XorEncryption.decrypt(data))
        except Exception as ex:
            raise KasaException(
                f"Unable to read UDP discovery response from device: {ip}: {ex}"
            ) from ex
        if not isinstance(response, dict):
            raise KasaException(
                f"UDP discovery response from {ip} did not contain a JSON object"
            )
        return response

    def create_candidate(
        self,
        info: dict[str, Any],
        ip: str,
        port: int,
    ) -> _DiscoveryCandidate:
        """Normalize a decoded UDP discovery response."""
        sys_info = extract_sys_info(info)
        if not sys_info:
            raise KasaException("No 'system' or 'get_sysinfo' in response")
        device_family = sys_info.get("mic_type", sys_info.get("type"))
        if device_family is None:
            raise UnsupportedDeviceError(
                "Unable to find the device type field",
                discovery_result=info,
                host=ip,
            )
        login_version = (
            sys_info.get("stream_version")
            if device_family == DeviceFamily.IotIpCamera.value
            else None
        )
        connection = _DiscoveryConnection(
            device_family=device_family,
            encryption_type=DeviceEncryptionType.Xor.value,
            login_version=login_version,
            https=device_family == DeviceFamily.IotIpCamera.value,
        )
        return _DiscoveryCandidate(
            source=self.source,
            source_port=port,
            ip=ip,
            device_family=device_family,
            device_model=sys_info.get("model"),
            connection=connection,
            discovery_info=info,
            device_info=info,
        )


class _TdpDiscovery:
    """TDP v2 discovery for one independently managed endpoint population."""

    source = _DiscoverySource.Tdp
    defer_processing = False
    suppresses = frozenset({_DiscoverySource.Udp})

    def __init__(self, port: int) -> None:
        self.port = port
        self._query = _AesDiscoveryQuery()

    def create_query(self) -> bytes:
        """Create a TDP discovery query for this discovery operation."""
        return bytes(self._query.generate_query())

    @staticmethod
    def parse_response(data: bytes, ip: str) -> dict[str, Any]:
        """Decode a TDP discovery response."""
        try:
            response = json_loads(data[16:])
        except Exception as ex:
            raise KasaException(
                f"Unable to read TDP discovery response from device: {ip}: {ex}"
            ) from ex
        if not isinstance(response, dict):
            raise KasaException(
                f"TDP discovery response from {ip} did not contain a JSON object"
            )
        return response

    @staticmethod
    def decrypt_discovery_data(
        discovery_result: DiscoveryResult,
        *,
        keypair: KeyPair,
    ) -> None:
        """Decrypt encrypted supplemental information in a TDP response."""
        debug_enabled = _LOGGER.isEnabledFor(logging.DEBUG)
        if TYPE_CHECKING:
            assert discovery_result.encrypt_info
        encrypted_key = discovery_result.encrypt_info.key
        encrypted_data = discovery_result.encrypt_info.data

        key_and_iv = keypair.decrypt_discovery_key(
            base64.b64decode(encrypted_key.encode())
        )
        key, iv = key_and_iv[:16], key_and_iv[16:]
        session = AesEncyptionSession(key, iv)
        decrypted_data = session.decrypt(encrypted_data)
        result = json_loads(decrypted_data)
        if not isinstance(result, dict):
            raise KasaException(
                f"Decrypted TDP discovery data from {discovery_result.ip} "
                "did not contain a JSON object"
            )
        if debug_enabled:
            redacted = (
                redact_data(result, DECRYPTED_REDACTORS)
                if Discover._redact_data
                else result
            )
            _LOGGER.debug(
                "Decrypted encrypt_info for %s: %s",
                discovery_result.ip,
                pf(redacted),
            )
        discovery_result.decrypted_data = result

    def create_candidate(
        self,
        info: dict[str, Any],
        ip: str,
        port: int,
    ) -> _DiscoveryCandidate:
        """Normalize a decoded TDP discovery response."""
        result = info.get("result")
        if not isinstance(result, dict) or not {
            "device_type",
            "ip",
        }.issubset(result):
            raise KasaException(
                f"Response from {ip} is not a recognizable TDP device result"
            )
        try:
            discovery_result = DiscoveryResult.from_dict(result)
        except Exception as ex:
            raise KasaException(
                f"Unable to parse discovery from device: {ip}: {ex}",
            ) from ex

        if discovery_result.ip != ip:
            _LOGGER.debug(
                "TDP response source address differs from its advertised address; "
                "using source address %s",
                ip,
            )
            discovery_result.ip = ip

        if (
            encrypt_info := discovery_result.encrypt_info
        ) and encrypt_info.sym_schm == "AES":
            try:
                self.decrypt_discovery_data(
                    discovery_result,
                    keypair=self._query.keypair,
                )
            except Exception:
                _LOGGER.exception(
                    "Unable to decrypt discovery data %s: %s",
                    ip,
                    redact_data(info, TDP_DISCOVERY_REDACTORS),
                )

        connection = _DiscoveryConnection.from_tdp_result(discovery_result)
        return _DiscoveryCandidate(
            source=self.source,
            source_port=port,
            ip=ip,
            device_family=discovery_result.device_type,
            device_model=discovery_result.device_model,
            connection=connection,
            discovery_info=info,
            discovery_result=discovery_result,
        )
