"""Device creation via DeviceConfig."""
import logging
import time
from typing import Any, Dict, Optional, Tuple, Type

from .aestransport import AesTransport
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
    IotSwitch,
)
from .iotprotocol import IotProtocol
from .klaptransport import KlapTransport, KlapTransportV2
from .protocol import (
    BaseProtocol,
    BaseTransport,
)
from .smart import SmartBulb, SmartDevice
from .smartprotocol import SmartProtocol
from .xortransport import XorTransport

_LOGGER = logging.getLogger(__name__)

GET_SYSINFO_QUERY = {
    "system": {"get_sysinfo": None},
}


async def connect(*, host: Optional[str] = None, config: DeviceConfig) -> "Device":
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

    if (protocol := get_protocol(config=config)) is None:
        raise UnsupportedDeviceError(
            f"Unsupported device for {config.host}: "
            + f"{config.connection_type.device_family.value}"
        )

    try:
        return await _connect(config, protocol)
    except:
        await protocol.close()
        raise


async def _connect(config: DeviceConfig, protocol: BaseProtocol) -> "Device":
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

    device_class: Optional[Type[Device]]
    device: Optional[Device] = None

    if isinstance(protocol, IotProtocol) and isinstance(
        protocol._transport, XorTransport
    ):
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
        raise UnsupportedDeviceError(
            f"Unsupported device for {config.host}: "
            + f"{config.connection_type.device_family.value}"
        )


def _get_device_type_from_sys_info(info: Dict[str, Any]) -> DeviceType:
    """Find SmartDevice subclass for device described by passed data."""
    if "system" not in info or "get_sysinfo" not in info["system"]:
        raise KasaException("No 'system' or 'get_sysinfo' in response")

    sysinfo: Dict[str, Any] = info["system"]["get_sysinfo"]
    type_: Optional[str] = sysinfo.get("type", sysinfo.get("mic_type"))
    if type_ is None:
        raise KasaException("Unable to find the device type field!")

    if "dev_name" in sysinfo and "Dimmer" in sysinfo["dev_name"]:
        return DeviceType.Dimmer

    if "smartplug" in type_.lower():
        if "children" in sysinfo:
            return DeviceType.Strip
        if (dev_name := sysinfo.get("dev_name")) and "light" in dev_name.lower():
            return DeviceType.Switch
        return DeviceType.Plug

    if "smartbulb" in type_.lower():
        if "length" in sysinfo:  # strips have length
            return DeviceType.LightStrip

        return DeviceType.Bulb
    raise UnsupportedDeviceError("Unknown device type: %s" % type_)


def get_device_class_from_sys_info(sysinfo: Dict[str, Any]) -> Type[IotDevice]:
    """Find SmartDevice subclass for device described by passed data."""
    TYPE_TO_CLASS = {
        DeviceType.Bulb: IotBulb,
        DeviceType.Plug: IotPlug,
        DeviceType.Dimmer: IotDimmer,
        DeviceType.Strip: IotStrip,
        DeviceType.Switch: IotSwitch,
        DeviceType.LightStrip: IotLightStrip,
    }
    return TYPE_TO_CLASS[_get_device_type_from_sys_info(sysinfo)]


def get_device_class_from_family(device_type: str) -> Optional[Type[Device]]:
    """Return the device class from the type name."""
    supported_device_types: Dict[str, Type[Device]] = {
        "SMART.TAPOPLUG": SmartDevice,
        "SMART.TAPOBULB": SmartBulb,
        "SMART.TAPOSWITCH": SmartBulb,
        "SMART.KASAPLUG": SmartDevice,
        "SMART.TAPOHUB": SmartDevice,
        "SMART.KASASWITCH": SmartBulb,
        "IOT.SMARTPLUGSWITCH": IotPlug,
        "IOT.SMARTBULB": IotBulb,
    }
    return supported_device_types.get(device_type)


def get_protocol(
    config: DeviceConfig,
) -> Optional[BaseProtocol]:
    """Return the protocol from the connection name."""
    protocol_name = config.connection_type.device_family.value.split(".")[0]
    protocol_transport_key = (
        protocol_name + "." + config.connection_type.encryption_type.value
    )
    supported_device_protocols: Dict[
        str, Tuple[Type[BaseProtocol], Type[BaseTransport]]
    ] = {
        "IOT.XOR": (IotProtocol, XorTransport),
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
