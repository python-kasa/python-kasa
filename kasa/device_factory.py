"""Device creation via DeviceConfig."""

from __future__ import annotations

import logging
import time
from typing import Any
from warnings import warn

from .device import Device
from .device_type import DeviceType
from .deviceconfig import DeviceConfig
from .exceptions import KasaException, UnsupportedDeviceError
from .iot import (
    IotBulb,
    IotDevice,
    IotDimmer,
    IotLightStrip,
    IotPlug,
    IotStrip,
    IotWallSwitch,
)
from .protocols import BaseProtocol, IotProtocol
from .registry import REGISTRY

_LOGGER = logging.getLogger(__name__)

GET_SYSINFO_QUERY: dict[str, dict[str, dict]] = {
    "system": {"get_sysinfo": {}},
}


async def connect(*, host: str | None = None, config: DeviceConfig) -> Device:
    """Connect to a single device by the given hostname or device configuration.

    This method avoids the UDP based discovery process and
    will connect directly to the device.

    It is generally preferred to avoid :func:`discover_single()` and
    use this function instead as it should perform better when
    the WiFi network is congested or the device is not responding
    to discovery requests.

    Do not use this function directly, use SmartDevice.connect()

    :param host: Hostname of device to query
    :param config: Connection parameters to ensure the correct protocol
        and connection options are used.
    :rtype: SmartDevice
    :return: Object for querying/controlling found device.
    """
    if host and config or (not host and not config):
        raise KasaException("One of host or config must be provded and not both")
    if host:
        config = DeviceConfig(host=host)

    if (protocol := REGISTRY.get_protocol(config)) is None:
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

    device_class: type[Device] | None
    device: Device | None = None

    # For IOT devices, we need to obtain the initial sysinfo in order decide
    # on the device class to initialize.
    if isinstance(protocol, IotProtocol):
        info = await protocol.query(GET_SYSINFO_QUERY)
        _perf_log(True, "get_sysinfo")
        device_class = get_device_class_from_sys_info(info)
        device = device_class(config.host, protocol=protocol)
        device.update_from_discover_info(info)
        await device.update()
        _perf_log(True, "update")
        return device
    elif device_class := REGISTRY.get_device_class(config.connection_type):
        device = device_class(host=config.host, protocol=protocol)
        await device.update()
        _perf_log(True, "update")
        return device
    else:
        raise UnsupportedDeviceError(
            f"Unsupported device for {config.host}: "
            + f"{config.connection_type.device_family.value}",
            host=config.host,
        )


def get_device_class_from_sys_info(sysinfo: dict[str, Any]) -> type[IotDevice]:
    """Find SmartDevice subclass for device described by passed data."""
    TYPE_TO_CLASS = {
        DeviceType.Bulb: IotBulb,
        DeviceType.Plug: IotPlug,
        DeviceType.Dimmer: IotDimmer,
        DeviceType.Strip: IotStrip,
        DeviceType.WallSwitch: IotWallSwitch,
        DeviceType.LightStrip: IotLightStrip,
        # Disabled until properly implemented
        # DeviceType.Camera: IotCamera,
    }
    device_type = IotDevice._get_device_type_from_sys_info(sysinfo)
    if (cls := TYPE_TO_CLASS.get(device_type)) is None:
        raise UnsupportedDeviceError(
            f"Unsupported device type: {device_type}",
            discovery_result=sysinfo,
        )
    return cls


def get_protocol(config: DeviceConfig) -> BaseProtocol | None:
    """Return the protocol from the device config."""
    msg = "get_protocol is deprecated, use kasa.registry.REGISTRY.get_protocol instead"
    warn(msg, DeprecationWarning, stacklevel=2)
    return REGISTRY.get_protocol(config)
