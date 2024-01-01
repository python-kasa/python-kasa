"""Device creation via DeviceConfig."""
import logging
import time
from typing import Any, Dict, Optional, Tuple, Type

from .aestransport import AesTransport
from .deviceconfig import DeviceConfig
from .exceptions import SmartDeviceException, UnsupportedDeviceException
from .iotprotocol import IotProtocol
from .klaptransport import KlapTransport, KlapTransportV2
from .protocol import (
    BaseTransport,
    TPLinkProtocol,
    TPLinkSmartHomeProtocol,
    _XorTransport,
)
from .smartbulb import SmartBulb
from .smartdevice import SmartDevice
from .smartdimmer import SmartDimmer
from .smartlightstrip import SmartLightStrip
from .smartplug import SmartPlug
from .smartprotocol import SmartProtocol
from .smartstrip import SmartStrip
from .tapo import TapoBulb, TapoPlug

_LOGGER = logging.getLogger(__name__)

GET_SYSINFO_QUERY = {
    "system": {"get_sysinfo": None},
}


async def connect(*, host: Optional[str] = None, config: DeviceConfig) -> "SmartDevice":
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
        raise SmartDeviceException("One of host or config must be provded and not both")
    if host:
        config = DeviceConfig(host=host)

    debug_enabled = _LOGGER.isEnabledFor(logging.DEBUG)
    if debug_enabled:
        start_time = time.perf_counter()

    def _perf_log(has_params, perf_type):
        nonlocal start_time
        if debug_enabled:
            end_time = time.perf_counter()
            _LOGGER.debug(
                f"Device {config.host} with connection params {has_params} "
                + f"took {end_time - start_time:.2f} seconds to {perf_type}",
            )
            start_time = time.perf_counter()

    if (protocol := get_protocol(config=config)) is None:
        raise UnsupportedDeviceException(
            f"Unsupported device for {config.host}: "
            + f"{config.connection_type.device_family.value}"
        )

    device_class: Optional[Type[SmartDevice]]

    if isinstance(protocol, TPLinkSmartHomeProtocol):
        info = await protocol.query(GET_SYSINFO_QUERY)
        _perf_log(True, "get_sysinfo")
        device_class = get_device_class_from_sys_info(info)
        device = device_class(config.host, protocol=protocol)
        device.update_from_discover_info(info)
        await device.update()
        _perf_log(True, "update")
        return device
    elif device_class := get_device_class_from_family(
        config.connection_type.device_family.value
    ):
        device = device_class(host=config.host, protocol=protocol)
        await device.update()
        _perf_log(True, "update")
        return device
    else:
        raise UnsupportedDeviceException(
            f"Unsupported device for {config.host}: "
            + f"{config.connection_type.device_family.value}"
        )


def get_device_class_from_sys_info(info: Dict[str, Any]) -> Type[SmartDevice]:
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


def get_device_class_from_family(device_type: str) -> Optional[Type[SmartDevice]]:
    """Return the device class from the type name."""
    supported_device_types: dict[str, Type[SmartDevice]] = {
        "SMART.TAPOPLUG": TapoPlug,
        "SMART.TAPOBULB": TapoBulb,
        "SMART.KASAPLUG": TapoPlug,
        "SMART.KASASWITCH": TapoBulb,
        "IOT.SMARTPLUGSWITCH": SmartPlug,
        "IOT.SMARTBULB": SmartBulb,
    }
    return supported_device_types.get(device_type)


def get_protocol(
    config: DeviceConfig,
) -> Optional[TPLinkProtocol]:
    """Return the protocol from the connection name."""
    protocol_name = config.connection_type.device_family.value.split(".")[0]
    protocol_transport_key = (
        protocol_name + "." + config.connection_type.encryption_type.value
    )
    supported_device_protocols: dict[
        str, Tuple[Type[TPLinkProtocol], Type[BaseTransport]]
    ] = {
        "IOT.XOR": (TPLinkSmartHomeProtocol, _XorTransport),
        "IOT.KLAP": (IotProtocol, KlapTransport),
        "SMART.AES": (SmartProtocol, AesTransport),
        "SMART.KLAP": (SmartProtocol, KlapTransportV2),
    }
    if protocol_transport_key not in supported_device_protocols:
        return None

    protocol_class, transport_class = supported_device_protocols.get(
        protocol_transport_key
    )  # type: ignore
    return protocol_class(transport=transport_class(config=config))
