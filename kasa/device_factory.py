"""Device creation by type."""

import logging
import time
from typing import Any, Dict, Optional, Type

from .credentials import Credentials
from .device_type import DeviceType
from .exceptions import UnsupportedDeviceException
from .smartbulb import SmartBulb
from .smartdevice import SmartDevice, SmartDeviceException
from .smartdimmer import SmartDimmer
from .smartlightstrip import SmartLightStrip
from .smartplug import SmartPlug
from .smartstrip import SmartStrip

DEVICE_TYPE_TO_CLASS = {
    DeviceType.Plug: SmartPlug,
    DeviceType.Bulb: SmartBulb,
    DeviceType.Strip: SmartStrip,
    DeviceType.Dimmer: SmartDimmer,
    DeviceType.LightStrip: SmartLightStrip,
}

_LOGGER = logging.getLogger(__name__)


async def connect(
    host: str,
    *,
    port: Optional[int] = None,
    timeout=5,
    credentials: Optional[Credentials] = None,
    device_type: Optional[DeviceType] = None,
) -> "SmartDevice":
    """Connect to a single device by the given IP address.

    This method avoids the UDP based discovery process and
    will connect directly to the device to query its type.

    It is generally preferred to avoid :func:`discover_single()` and
    use this function instead as it should perform better when
    the WiFi network is congested or the device is not responding
    to discovery requests.

    The device type is discovered by querying the device.

    :param host: Hostname of device to query
    :param device_type: Device type to use for the device.
        If not given, the device type is discovered by querying the device.
        If the device type is already known, it is preferred to pass it
        to avoid the extra query to the device to discover its type.
    :rtype: SmartDevice
    :return: Object for querying/controlling found device.
    """
    debug_enabled = _LOGGER.isEnabledFor(logging.DEBUG)

    if debug_enabled:
        start_time = time.perf_counter()

    if device_type and (klass := DEVICE_TYPE_TO_CLASS.get(device_type)):
        dev: SmartDevice = klass(
            host=host, port=port, credentials=credentials, timeout=timeout
        )
        await dev.update()
        if debug_enabled:
            end_time = time.perf_counter()
            _LOGGER.debug(
                "Device %s with known type (%s) took %.2f seconds to connect",
                host,
                device_type.value,
                end_time - start_time,
            )
        return dev

    unknown_dev = SmartDevice(
        host=host, port=port, credentials=credentials, timeout=timeout
    )
    await unknown_dev.update()
    device_class = get_device_class_from_info(unknown_dev.internal_state)
    dev = device_class(host=host, port=port, credentials=credentials, timeout=timeout)
    # Reuse the connection from the unknown device
    # so we don't have to reconnect
    dev.protocol = unknown_dev.protocol
    await dev.update()
    if debug_enabled:
        end_time = time.perf_counter()
        _LOGGER.debug(
            "Device %s with unknown type (%s) took %.2f seconds to connect",
            host,
            dev.device_type.value,
            end_time - start_time,
        )
    return dev


def get_device_class_from_info(info: Dict[str, Any]) -> Type[SmartDevice]:
    """Find SmartDevice subclass for device described by passed data."""
    if "system" not in info or "get_sysinfo" not in info["system"]:
        raise SmartDeviceException("No 'system' or 'get_sysinfo' in response")

    sysinfo: Dict[str, Any] = info["system"]["get_sysinfo"]
    type_: Optional[str] = sysinfo.get("type", sysinfo.get("mic_type"))
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
    raise UnsupportedDeviceException("Unknown device type: %s" % type_)
