"""Device creation via DeviceConfig."""
import logging
import time
from typing import Any, Dict, Optional, Type

from kasa.deviceconfig import DeviceConfig
from kasa.protocol import TPLinkSmartHomeProtocol
from kasa.smartbulb import SmartBulb
from kasa.smartdevice import SmartDevice
from kasa.smartdimmer import SmartDimmer
from kasa.smartlightstrip import SmartLightStrip
from kasa.smartplug import SmartPlug
from kasa.smartstrip import SmartStrip
from kasa.tapo import TapoBulb, TapoPlug

from .exceptions import SmartDeviceException, UnsupportedDeviceException
from .protocolfactory import get_protocol

_LOGGER = logging.getLogger(__name__)

GET_SYSINFO_QUERY = {
    "system": {"get_sysinfo": None},
}


async def connect(*, config: DeviceConfig) -> "SmartDevice":
    """Connect to a single device by the given connection parameters.

    Do not use this function directly, use SmartDevice.Connect()
    """
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
        "IOT.SMARTPLUGSWITCH": SmartPlug,
        "IOT.SMARTBULB": SmartBulb,
    }
    return supported_device_types.get(device_type)
