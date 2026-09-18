"""Device creation via DeviceConfig."""

from __future__ import annotations

import logging
import time
from collections.abc import AsyncIterator, Callable
from dataclasses import dataclass, replace
from enum import Enum
from typing import Any, NamedTuple

from aiohttp import ClientSession

from .credentials import Credentials
from .device import Device, get_unsupported_authentication_error
from .device_type import DeviceType
from .deviceconfig import (
    DeviceConfig,
    DeviceConnectionParameters,
    DeviceEncryptionType,
    DeviceFamily,
)
from .exceptions import AuthenticationError, KasaException, UnsupportedDeviceError
from .iot import (
    IotBulb,
    IotDevice,
    IotDimmer,
    IotLightStrip,
    IotPlug,
    IotStrip,
    IotWallSwitch,
)
from .protocols import (
    BaseProtocol,
    IotProtocol,
    SmartProtocol,
)
from .protocols.smartcamprotocol import SmartCamProtocol
from .smart import SmartDevice
from .smartcam import SmartCamDevice
from .transports import (
    AesTransport,
    BaseTransport,
    KlapTransport,
    KlapTransportV2,
    LinkieTransportV2,
    SslTransport,
    XorTransport,
)
from .transports.sslaestransport import SslAesTransport

_LOGGER = logging.getLogger(__name__)

_GET_SYSINFO_QUERY: dict[str, dict[str, dict]] = {
    "system": {"get_sysinfo": {}},
}

_IOT_DEVICE_CLASSES: dict[DeviceType, type[IotDevice]] = {
    DeviceType.Bulb: IotBulb,
    DeviceType.Plug: IotPlug,
    DeviceType.Dimmer: IotDimmer,
    DeviceType.Strip: IotStrip,
    DeviceType.WallSwitch: IotWallSwitch,
    DeviceType.LightStrip: IotLightStrip,
}


class ConnectAttempt(NamedTuple):
    """Describe one direct connection attempt."""

    protocol: type[BaseProtocol]
    transport: type[BaseTransport]
    device: type[Device]
    https: bool
    connection_type: DeviceConnectionParameters


OnConnectAttemptCallable = Callable[[ConnectAttempt, bool], None]


class _ProtocolType(Enum):
    """Internal protocol types used to resolve protocol and transport classes."""

    Iot = "IOT"
    Smart = "SMART"
    SmartCam = "SMARTCAM"


@dataclass(frozen=True)
class _DeviceFamilyInfo:
    """Describe how an advertised device family is represented by the library."""

    device_class: type[Device] | None
    protocol_type: _ProtocolType
    requires_iot_sysinfo: bool = False
    https_device_class: type[Device] | None = None
    https_protocol_type: _ProtocolType | None = None
    probe: bool = False

    def for_connection(self, *, https: bool) -> _DeviceFamilyInfo:
        """Resolve connection-specific class and protocol overrides."""
        if not https:
            return self
        return _DeviceFamilyInfo(
            device_class=self.https_device_class or self.device_class,
            protocol_type=self.https_protocol_type or self.protocol_type,
            requires_iot_sysinfo=self.requires_iot_sysinfo,
            probe=self.probe,
        )


_DEVICE_FAMILIES: dict[DeviceFamily, _DeviceFamilyInfo] = {
    # IOT.SMARTPLUGSWITCH and IOT.SMARTBULB are advertised family buckets,
    # not concrete Python device classes.  The default classes preserve the
    # synchronous family lookup API, while every construction path resolves
    # the final class from get_sysinfo when requires_iot_sysinfo is true.
    DeviceFamily.IotSmartPlugSwitch: _DeviceFamilyInfo(
        IotPlug,
        _ProtocolType.Iot,
        requires_iot_sysinfo=True,
        probe=True,
    ),
    DeviceFamily.IotSmartBulb: _DeviceFamilyInfo(
        IotBulb, _ProtocolType.Iot, requires_iot_sysinfo=True
    ),
    # IOT cameras are recognized for routing but remain disabled as a concrete
    # device class until their API implementation is complete.
    DeviceFamily.IotIpCamera: _DeviceFamilyInfo(None, _ProtocolType.Iot),
    DeviceFamily.SmartTapoPlug: _DeviceFamilyInfo(
        SmartDevice, _ProtocolType.Smart, probe=True
    ),
    DeviceFamily.SmartTapoBulb: _DeviceFamilyInfo(SmartDevice, _ProtocolType.Smart),
    DeviceFamily.SmartTapoSwitch: _DeviceFamilyInfo(SmartDevice, _ProtocolType.Smart),
    DeviceFamily.SmartKasaPlug: _DeviceFamilyInfo(SmartDevice, _ProtocolType.Smart),
    DeviceFamily.SmartTapoHub: _DeviceFamilyInfo(
        SmartDevice,
        _ProtocolType.Smart,
        https_device_class=SmartCamDevice,
        https_protocol_type=_ProtocolType.SmartCam,
    ),
    DeviceFamily.SmartKasaHub: _DeviceFamilyInfo(SmartDevice, _ProtocolType.Smart),
    DeviceFamily.SmartKasaSwitch: _DeviceFamilyInfo(SmartDevice, _ProtocolType.Smart),
    DeviceFamily.SmartTapoChime: _DeviceFamilyInfo(SmartDevice, _ProtocolType.Smart),
    DeviceFamily.SmartIpCamera: _DeviceFamilyInfo(
        None,
        _ProtocolType.SmartCam,
        https_device_class=SmartCamDevice,
        probe=True,
    ),
    DeviceFamily.SmartTapoDoorbell: _DeviceFamilyInfo(
        None,
        _ProtocolType.SmartCam,
        https_device_class=SmartCamDevice,
    ),
    DeviceFamily.SmartTapoRobovac: _DeviceFamilyInfo(
        None,
        _ProtocolType.Smart,
        https_device_class=SmartDevice,
        probe=True,
    ),
}


@dataclass(frozen=True)
class _ConnectionRoute:
    """Map normalized connection parameters to protocol and transport classes.

    New transport variants should first be represented by
    :class:`DeviceConnectionParameters`, then added here as a route. Discovery,
    direct connection, and protocol creation all consume this same table.
    """

    protocol_type: _ProtocolType
    encryption_type: DeviceEncryptionType
    https: bool
    protocol: type[BaseProtocol]
    transport: type[BaseTransport]
    device_family: DeviceFamily | None = None
    fixed_encryption: bool = False
    match_https: bool = True
    login_version: int | None = None
    klap_version: int | None = None
    match_klap_version: bool = False

    def create_connection_parameters(
        self,
        device_family: DeviceFamily,
    ) -> DeviceConnectionParameters:
        """Create complete parameters for a direct connection attempt."""
        return DeviceConnectionParameters(
            device_family=device_family,
            encryption_type=self.encryption_type,
            login_version=self.login_version,
            https=self.https,
            klap_version=self.klap_version,
        )

    def matches_identity(
        self,
        connection_type: DeviceConnectionParameters,
        family_info: _DeviceFamilyInfo,
    ) -> bool:
        """Return whether this route applies apart from encryption."""
        if self.device_family is not None:
            if self.device_family is not connection_type.device_family:
                return False
        elif self.protocol_type is not family_info.protocol_type:
            return False
        if self.match_https and self.https is not connection_type.https:
            return False
        return not self.match_klap_version or bool(self.klap_version) == bool(
            connection_type.klap_version
        )

    def matches(
        self,
        connection_type: DeviceConnectionParameters,
        family_info: _DeviceFamilyInfo,
        *,
        strict: bool,
    ) -> bool:
        """Return whether this route supports the connection parameters."""
        if not self.matches_identity(connection_type, family_info):
            return False
        return self.encryption_type is connection_type.encryption_type or (
            self.fixed_encryption and not strict
        )


_CONNECTION_ROUTES: tuple[_ConnectionRoute, ...] = (
    # Exact family routes are listed before generic protocol routes.
    _ConnectionRoute(
        _ProtocolType.SmartCam,
        DeviceEncryptionType.Aes,
        True,
        SmartCamProtocol,
        SslAesTransport,
        device_family=DeviceFamily.SmartIpCamera,
        fixed_encryption=True,
        match_https=False,
        login_version=2,
    ),
    _ConnectionRoute(
        _ProtocolType.SmartCam,
        DeviceEncryptionType.Aes,
        True,
        SmartCamProtocol,
        SslAesTransport,
        device_family=DeviceFamily.SmartTapoDoorbell,
        fixed_encryption=True,
        match_https=False,
        login_version=2,
    ),
    _ConnectionRoute(
        _ProtocolType.Iot,
        DeviceEncryptionType.Xor,
        True,
        IotProtocol,
        LinkieTransportV2,
        device_family=DeviceFamily.IotIpCamera,
        fixed_encryption=True,
        match_https=False,
    ),
    _ConnectionRoute(
        _ProtocolType.Smart,
        DeviceEncryptionType.Aes,
        True,
        SmartProtocol,
        SslTransport,
        device_family=DeviceFamily.SmartTapoRobovac,
        match_https=False,
        login_version=2,
    ),
    # SMART.TAPOHUB with KLAP and HTTPS used SmartProtocol on master even
    # though AES/HTTPS hubs use SmartCamProtocol. Keep this exact route before
    # the generic SmartCam routes so stored DeviceConfigs retain that behavior.
    _ConnectionRoute(
        _ProtocolType.Smart,
        DeviceEncryptionType.Klap,
        True,
        SmartProtocol,
        KlapTransportV2,
        device_family=DeviceFamily.SmartTapoHub,
        login_version=2,
    ),
    _ConnectionRoute(
        _ProtocolType.Iot,
        DeviceEncryptionType.Xor,
        False,
        IotProtocol,
        XorTransport,
    ),
    # IOT new_klap is independent from login_version. Its presence selects
    # the versioned handshake; an absent value retains the original handshake.
    _ConnectionRoute(
        _ProtocolType.Iot,
        DeviceEncryptionType.Klap,
        False,
        IotProtocol,
        KlapTransport,
        match_klap_version=True,
    ),
    _ConnectionRoute(
        _ProtocolType.Iot,
        DeviceEncryptionType.Klap,
        False,
        IotProtocol,
        KlapTransportV2,
        login_version=2,
        klap_version=1,
        match_klap_version=True,
    ),
    _ConnectionRoute(
        _ProtocolType.Smart,
        DeviceEncryptionType.Aes,
        False,
        SmartProtocol,
        AesTransport,
        login_version=2,
    ),
    _ConnectionRoute(
        _ProtocolType.Smart,
        DeviceEncryptionType.Aes,
        True,
        SmartCamProtocol,
        SslAesTransport,
        login_version=2,
    ),
    _ConnectionRoute(
        _ProtocolType.Smart,
        DeviceEncryptionType.Klap,
        False,
        SmartProtocol,
        KlapTransportV2,
        login_version=2,
    ),
    _ConnectionRoute(
        _ProtocolType.Smart,
        DeviceEncryptionType.Klap,
        True,
        SmartProtocol,
        KlapTransportV2,
        login_version=2,
    ),
    _ConnectionRoute(
        _ProtocolType.SmartCam,
        DeviceEncryptionType.Aes,
        True,
        SmartCamProtocol,
        SslAesTransport,
        login_version=2,
    ),
)


async def connect(*, host: str | None = None, config: DeviceConfig) -> Device:
    """Connect to a single device by the given hostname or device configuration.

    This method avoids broadcast discovery and connects directly to the device.

    It is generally preferred to avoid :func:`discover_single()` and
    use this function instead as it should perform better when
    the WiFi network is congested or the device is not responding
    to discovery requests.

    Do not use this function directly; use :meth:`Device.connect`.

    :param host: Hostname of device to query
    :param config: Connection parameters to ensure the correct protocol
        and connection options are used.
    :rtype: Device
    :return: Object for querying/controlling found device.
    """
    if host and config or (not host and not config):
        raise KasaException("One of host or config must be provided, but not both")
    if host:
        config = DeviceConfig(host=host)

    if (protocol := get_protocol(config=config)) is None:
        raise UnsupportedDeviceError(
            f"Unsupported device for {config.host}: "
            + f"{config.connection_type.device_family.value}",
            host=config.host,
        )

    try:
        return await _connect(config, protocol)
    except:
        await protocol.close()
        raise


async def _connect(config: DeviceConfig, protocol: BaseProtocol) -> Device:
    debug_enabled = _LOGGER.isEnabledFor(logging.DEBUG)
    if debug_enabled:
        start_time = time.perf_counter()

    def _perf_log(has_params: bool, perf_type: str) -> None:
        nonlocal start_time
        if debug_enabled:
            end_time = time.perf_counter()
            _LOGGER.debug(
                "Device %s with connection params %s took %.2f seconds to %s",
                config.host,
                has_params,
                end_time - start_time,
                perf_type,
            )
            start_time = time.perf_counter()

    device = await create_device(config, protocol=protocol)
    await device.update()
    _perf_log(True, "update")
    return device


async def create_device(
    config: DeviceConfig,
    *,
    protocol: BaseProtocol | None = None,
    device_info: dict[str, Any] | None = None,
    discovery_info: dict[str, Any] | None = None,
) -> Device:
    """Create and initialize a device without performing a full update.

    The factory owns protocols it creates and closes them if initialization
    fails. A caller-supplied protocol remains owned by the caller.

    :param config: Complete connection configuration for the device.
    :param protocol: Optional pre-created protocol for connection attempts.
    :param device_info: Optional full device information supplied by the
        selected discovery method, such as an IOT ``get_sysinfo`` response
        contained in UDP discovery.
    :param discovery_info: Optional source discovery information used to
        initialize devices when full device information is not available.
    """
    owns_protocol = protocol is None
    if protocol is None:
        protocol = get_protocol(config)
        if protocol is None:
            raise UnsupportedDeviceError(
                f"Unsupported device for {config.host}: "
                f"{config.connection_type.to_dict()}",
                discovery_result=discovery_info,
                host=config.host,
            )

    try:
        device_class, resolved_device_info = await _resolve_device_class(
            config.connection_type.device_family.value,
            https=config.connection_type.https,
            protocol=protocol,
            device_info=device_info,
        )
        config = _normalize_iot_connection_type(
            config, device_class, resolved_device_info
        )
        device = device_class(config.host, config=config, protocol=protocol)
        if discovery_info is not None:
            device.update_from_discover_info(
                discovery_info,
                device_info=resolved_device_info,
            )
        elif resolved_device_info is not None:
            device.update_from_discover_info(resolved_device_info)
        return device
    except UnsupportedDeviceError as ex:
        if ex.discovery_result is None:
            ex.discovery_result = discovery_info
        if ex.host is None:
            ex.host = config.host
        if owns_protocol:
            await protocol.close()
        raise
    except AuthenticationError as ex:
        unsupported_error = get_unsupported_authentication_error(
            config.host, discovery_info, ex
        )
        if owns_protocol:
            await protocol.close()
        if unsupported_error is not None:
            raise unsupported_error from ex
        raise
    except BaseException:
        if owns_protocol:
            await protocol.close()
        raise


def get_device_class_from_sys_info(sysinfo: dict[str, Any]) -> type[IotDevice]:
    """Return the concrete IOT class described by a sysinfo response."""
    device_type = IotDevice._get_device_type_from_sys_info(sysinfo)
    if device_class := _IOT_DEVICE_CLASSES.get(device_type):
        return device_class
    raise UnsupportedDeviceError(
        f"Unsupported IOT device type: {device_type.value}",
        discovery_result=sysinfo,
    )


def _normalize_iot_connection_type(
    config: DeviceConfig,
    device_class: type[Device],
    device_info: dict[str, Any] | None,
) -> DeviceConfig:
    """Return a config whose broad IOT family matches its concrete class."""
    if device_info is None or not issubclass(device_class, IotDevice):
        return config

    advertised_family = config.connection_type.device_family
    if advertised_family not in {
        DeviceFamily.IotSmartPlugSwitch,
        DeviceFamily.IotSmartBulb,
    }:
        return config

    device_type = IotDevice._get_device_type_from_sys_info(device_info)
    resolved_family = (
        DeviceFamily.IotSmartBulb
        if device_type in {DeviceType.Bulb, DeviceType.LightStrip}
        else DeviceFamily.IotSmartPlugSwitch
    )
    if resolved_family is advertised_family:
        return config

    return replace(
        config,
        connection_type=replace(
            config.connection_type,
            device_family=resolved_family,
        ),
    )


def get_device_class_from_family(
    device_type: str, *, https: bool, require_exact: bool = False
) -> type[Device] | None:
    """Return the device class from the type name."""
    family_info = _get_device_family_info(device_type, https=https)
    if family_info is not None and family_info.device_class is not None:
        cls: type[Device] | None = family_info.device_class
    elif device_type.startswith("SMART.") and not require_exact:
        _LOGGER.debug("Unknown SMART device with %s, using SmartDevice", device_type)
        cls = SmartDevice
    else:
        cls = None

    if cls is not None:
        _LOGGER.debug("Using %s for %s", cls.__name__, device_type)

    return cls


def _get_device_family_info(
    device_type: str,
    *,
    https: bool,
) -> _DeviceFamilyInfo | None:
    """Return internal device and protocol information for an advertised family."""
    try:
        family = DeviceFamily(device_type)
    except ValueError:
        return None
    if family_info := _DEVICE_FAMILIES.get(family):
        return family_info.for_connection(https=https)
    return None


async def _resolve_device_class(
    device_type: str,
    *,
    https: bool,
    protocol: BaseProtocol,
    device_info: dict[str, Any] | None = None,
) -> tuple[type[Device], dict[str, Any] | None]:
    """Resolve the concrete device class and any required system information.

    IOT family names group several concrete device types.  They must always be
    resolved from get_sysinfo instead of using the family mapping's default
    class.  UDP discovery supplies that response as part of its own candidate;
    discovery methods without system information query it through their
    selected protocol.
    """
    family_info = _get_device_family_info(device_type, https=https)
    if family_info is None:
        if device_class := get_device_class_from_family(device_type, https=https):
            return device_class, device_info
        raise UnsupportedDeviceError(f"Unsupported device family: {device_type}")
    if family_info.device_class is None:
        if device_class := get_device_class_from_family(device_type, https=https):
            return device_class, device_info
        raise UnsupportedDeviceError(f"Unsupported device family: {device_type}")

    if not family_info.requires_iot_sysinfo:
        return family_info.device_class, device_info

    if device_info is None:
        device_info = await protocol.query(_GET_SYSINFO_QUERY)
    return get_device_class_from_sys_info(device_info), device_info


def get_protocol(config: DeviceConfig, *, strict: bool = False) -> BaseProtocol | None:
    """Return the protocol from the device config.

    For cameras and vacuums the device family is a simple mapping to
    the protocol/transport. For other device types the transport varies
    based on the discovery information.

    :param config: Device config to derive protocol
    :param strict: Require exact match on encrypt type
    """
    _LOGGER.debug("Finding protocol for %s", config.host)
    ctype = config.connection_type
    _LOGGER.debug("Finding protocol for %s", ctype.device_family)

    family_info = _get_device_family_info(ctype.device_family.value, https=ctype.https)
    if family_info is None:
        return None
    if route := _get_connection_route(ctype, family_info, strict=strict):
        _LOGGER.debug("Using connection route %s", route)
        return route.protocol(transport=route.transport(config=config))
    return None


def _get_connection_route(
    connection_type: DeviceConnectionParameters,
    family_info: _DeviceFamilyInfo,
    *,
    strict: bool,
) -> _ConnectionRoute | None:
    """Return the single route selected for normalized parameters."""
    fixed_route_mismatch = False
    for route in _CONNECTION_ROUTES:
        if route.device_family is not connection_type.device_family:
            continue
        if not route.matches_identity(connection_type, family_info):
            continue
        if route.matches(connection_type, family_info, strict=strict):
            return route
        fixed_route_mismatch |= route.fixed_encryption

    # A fixed-encryption family route is authoritative. In strict mode a
    # mismatch is invalid instead of falling through to a generic transport.
    if strict and fixed_route_mismatch:
        return None

    for route in _CONNECTION_ROUTES:
        if route.device_family is None and route.matches(
            connection_type, family_info, strict=strict
        ):
            return route
    return None


def is_connection_type_supported(
    connection_type: DeviceConnectionParameters,
    *,
    strict: bool = False,
) -> bool:
    """Return whether parameters select a constructible device and route."""
    family_info = _get_device_family_info(
        connection_type.device_family.value,
        https=connection_type.https,
    )
    return (
        family_info is not None
        and family_info.device_class is not None
        and _get_connection_route(connection_type, family_info, strict=strict)
        is not None
    )


def _get_connection_type_candidates() -> list[DeviceConnectionParameters]:
    """Return direct-connect candidates from the supported connection routes."""
    candidates: list[DeviceConnectionParameters] = []

    for family, family_definition in sorted(
        _DEVICE_FAMILIES.items(), key=lambda item: item[0].value
    ):
        if not family_definition.probe:
            continue
        for route in _CONNECTION_ROUTES:
            family_info = family_definition.for_connection(https=route.https)
            if family_info.device_class is None:
                continue
            if route.device_family is not None:
                if route.device_family is not family:
                    continue
            elif route.protocol_type is not family_info.protocol_type:
                continue
            connection_type = route.create_connection_parameters(family)
            if connection_type not in candidates:
                candidates.append(connection_type)

    return candidates


async def _iter_connection_attempts(
    host: str,
    *,
    port: int | None,
    timeout: int | None,
    credentials: Credentials | None,
    credentials_hash: str | None,
    http_client: ClientSession | None,
) -> AsyncIterator[tuple[ConnectAttempt, BaseProtocol, DeviceConfig]]:
    """Yield each supported direct connection attempt lazily."""
    for connection_type in _get_connection_type_candidates():
        config = DeviceConfig(
            host=host,
            connection_type=connection_type,
            timeout=timeout,
            port_override=port,
            credentials=credentials,
            credentials_hash=credentials_hash,
            http_client=http_client,
        )
        device_class = get_device_class_from_family(
            connection_type.device_family.value,
            https=connection_type.https,
            require_exact=True,
        )
        if device_class is None:
            continue
        protocol = get_protocol(config, strict=True)
        if protocol is None:
            continue

        attempt = ConnectAttempt(
            type(protocol),
            type(protocol._transport),
            device_class,
            connection_type.https,
            connection_type,
        )
        yield attempt, protocol, config


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
    """Try each distinct supported connection route for a known host."""
    async for attempt, protocol, config in _iter_connection_attempts(
        host,
        port=port,
        timeout=timeout,
        credentials=credentials,
        credentials_hash=credentials_hash,
        http_client=http_client,
    ):
        try:
            _LOGGER.debug("Trying to connect with %s", protocol.__class__.__name__)
            device = await _connect(config, protocol)
        except Exception as ex:
            _LOGGER.debug(
                "Unable to connect with %s: %s",
                protocol.__class__.__name__,
                ex,
            )
            try:
                if on_attempt is not None:
                    on_attempt(attempt, False)
            finally:
                await protocol.close()
        except BaseException:
            await protocol.close()
            raise
        else:
            try:
                if on_attempt is not None:
                    on_attempt(attempt._replace(device=type(device)), True)
            except BaseException:
                await protocol.close()
                raise
            _LOGGER.debug("Found working protocol %s", protocol.__class__.__name__)
            return device
    return None
